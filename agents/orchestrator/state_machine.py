"""Resilience State Machine — Formal state transition logic (S1-S5).

Evaluates four measurable network-health metrics on every tick:
  1. Inventory coverage ratio
  2. Remaining thermal stability window
  3. Capacity-to-demand ratio
  4. Shipment latency

Drives deterministic state transitions rather than reacting to a single alarm.
"""

from __future__ import annotations

import structlog

from schemas import ResilienceState
from schemas.graph_state import CCROGraphState

logger = structlog.get_logger(__name__)

# Thresholds from the architecture spec
CAPACITY_MARGIN_S2_S3_THRESHOLD = 0.15  # S2 -> S3 when < 15%
CAPACITY_MARGIN_S3_S4_THRESHOLD = 0.0   # S3 -> S4 when < 0% (recovery exhausted)


class ResilienceStateMachine:
    """Evaluates state transitions based on network-health metrics.

    The Orchestrator calls evaluate() on every tick to determine the
    current resilience state.
    """

    def evaluate(self, state: CCROGraphState) -> ResilienceState:
        """Evaluate and return the correct resilience state based on current metrics.

        Priority order (most severe first):
          S4: capacity < demand (recovery exhausted)
          S3: capacity margin < 15%
          S2: disruption detected, recovery possible
          S1: nominal operations
        """
        state.compute_capacity_margin()
        margin = state.capacity_margin
        has_disruption = len(state.telemetry_buffer) > 0

        # S4: Recovery Insufficient — ΣC_available < ΣDemand
        # This is checked AFTER recovery options are applied (only from S3+)
        if (
            state.resilience_state in (
                ResilienceState.S3_RECOVERY_CONSTRAINED,
                ResilienceState.S4_RECOVERY_INSUFFICIENT,
            )
            and state.residual_capacity_after_recovery < state.total_demand
            and has_disruption
            and state.resilience_state != ResilienceState.S5_SCARCITY_ALLOCATION
        ):
            return ResilienceState.S4_RECOVERY_INSUFFICIENT

        # S3: Recovery Constrained — capacity margin < 15%
        if margin < CAPACITY_MARGIN_S2_S3_THRESHOLD and has_disruption:
            return ResilienceState.S3_RECOVERY_CONSTRAINED

        # S2: Absorbing Disruption — disruption detected, recovery capacity exceeds demand
        if has_disruption and margin >= CAPACITY_MARGIN_S2_S3_THRESHOLD:
            return ResilienceState.S2_ABSORBING

        # S1: Stable
        return ResilienceState.S1_STABLE

    def can_transition(self, current: ResilienceState, target: ResilienceState) -> bool:
        """Check if a state transition is valid.

        Valid transitions:
          S1 -> S2 (disruption detected)
          S2 -> S3 (capacity margin drops)
          S2 -> S1 (disruption resolved)
          S3 -> S4 (recovery exhausted)
          S3 -> S2 (capacity restored)
          S4 -> S5 (human approved)
          S4 -> S3 (recovery options found)
          S5 -> S3/S2 (post-execution re-measurement)
        """
        valid_transitions = {
            ResilienceState.S1_STABLE: {
                ResilienceState.S2_ABSORBING,
            },
            ResilienceState.S2_ABSORBING: {
                ResilienceState.S1_STABLE,
                ResilienceState.S3_RECOVERY_CONSTRAINED,
            },
            ResilienceState.S3_RECOVERY_CONSTRAINED: {
                ResilienceState.S2_ABSORBING,
                ResilienceState.S4_RECOVERY_INSUFFICIENT,
            },
            ResilienceState.S4_RECOVERY_INSUFFICIENT: {
                ResilienceState.S3_RECOVERY_CONSTRAINED,
                ResilienceState.S5_SCARCITY_ALLOCATION,
            },
            ResilienceState.S5_SCARCITY_ALLOCATION: {
                ResilienceState.S3_RECOVERY_CONSTRAINED,
                ResilienceState.S2_ABSORBING,
            },
        }

        allowed = valid_transitions.get(current, set())
        return target in allowed
