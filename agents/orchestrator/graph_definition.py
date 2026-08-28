"""LangGraph State Orchestrator — Graph Definition.

Supervisor-worker topology where the Orchestrator acts as the sole holder
of the canonical Resilience State Machine. Agents are stateless workers
that read a shared, versioned graph state object and return deltas.
"""

from __future__ import annotations

import structlog

from agents.orchestrator.state_machine import ResilienceStateMachine
from schemas import (
    ApprovalDecision,
    ResilienceState,
    WritebackStatus,
)
from schemas.graph_state import CCROGraphState

logger = structlog.get_logger(__name__)

state_machine = ResilienceStateMachine()


# ---------------------------------------------------------------------------
# Node functions — each represents an agent invocation
# ---------------------------------------------------------------------------


async def sense_node(state: CCROGraphState) -> CCROGraphState:
    """Phase 1 — SENSE: Ingest telemetry and update state.

    The Sensing Agent drains events from the Event Mesh consumer
    and adds them to the telemetry buffer.
    """
    logger.info("orchestrator.sense", n_events=len(state.telemetry_buffer))
    # In production, this calls the Sensing Agent service
    # For now, the events are already in the buffer
    return state


async def understand_node(state: CCROGraphState) -> CCROGraphState:
    """Phase 2 — UNDERSTAND: Assess impact and compute shelf-life projections.

    The Impact Agent reads batch expiry data from SAP and computes
    remaining shelf life per site.
    """
    logger.info("orchestrator.understand", n_events=len(state.telemetry_buffer))

    # In production, this calls the Impact Agent service
    # which reads from S/4HANA via the SAP Integration Gateway
    # Projections are stored in state.shelf_life_projections

    return state


async def adapt_node(state: CCROGraphState) -> CCROGraphState:
    """Phase 3 — ADAPT: Evaluate recovery options.

    The Recovery Agent Cluster runs its internal AutoGen negotiation
    (route vs. warehouse vs. fleet sub-agents) and returns
    RecoveryOptions[].
    """
    logger.info("orchestrator.adapt", n_sites=len(state.shelf_life_projections))

    # In production, this calls the Recovery Agent service
    # Recovery options are stored in state.recovery_options

    # Speculative RAG pre-fetch (latency hiding for S3->S4 transition)
    # This is called during S3, ahead of need
    if state.resilience_state == ResilienceState.S3_RECOVERY_CONSTRAINED:
        logger.info("orchestrator.prefetch_policy", phase="S3")

    return state


async def protect_node(state: CCROGraphState) -> CCROGraphState:
    """Phase 4 — PROTECT: Run scarcity allocation.

    The Scarcity Allocation Engine:
    1. Requests PolicyWeights from Policy Agent
    2. Computes P_i priority scores
    3. Submits constrained problem to Solver
    4. Returns proposed AllocationPlan
    """
    logger.info(
        "orchestrator.protect",
        n_sites=len(state.shelf_life_projections),
        has_policy_weights=state.policy_weights is not None,
    )

    # In production, this calls the Scarcity Engine service
    # The allocation plan is stored in state.proposed_allocation

    return state


async def govern_node(state: CCROGraphState) -> CCROGraphState:
    """Phase 5 — GOVERN: Push Human Approval Card.

    The Orchestrator pushes the proposed allocation to the Governance UI
    via WebSocket. The Ops Manager reviews the side-by-side comparison
    and decides.
    """
    logger.info(
        "orchestrator.govern",
        plan_id=state.proposed_allocation.plan_id if state.proposed_allocation else None,
    )

    # In production, this pushes to the Governance UI via WebSocket
    # and waits for the approval decision

    return state


async def execute_node(state: CCROGraphState) -> CCROGraphState:
    """Phase 6 — EXECUTE: Post-approval SAP writeback.

    The Execution Agent triggers the SAP Integration Gateway to write
    to SAP TM and S/4HANA, with idempotency and optimistic concurrency.
    """
    if not state.approval_record:
        logger.warning("orchestrator.execute_no_approval")
        return state

    logger.info(
        "orchestrator.execute",
        plan_id=state.proposed_allocation.plan_id if state.proposed_allocation else None,
        approver=state.approval_record.approver_id,
    )

    # In production, this calls the Execution Agent service
    # Writeback status is stored in state.writeback_status

    return state


# ---------------------------------------------------------------------------
# Transition evaluation
# ---------------------------------------------------------------------------


def evaluate_transition(state: CCROGraphState) -> ResilienceState:
    """Evaluate the next state based on current conditions."""
    return state_machine.evaluate(state)


def should_activate_scarcity(state: CCROGraphState) -> bool:
    """Check if the Scarcity Allocation Engine should be activated.

    S4 activation is mandatory when residual capacity < total demand
    after recovery options are exhausted.
    """
    return (
        state.residual_capacity_after_recovery < state.total_demand
        and state.resilience_state in (
            ResilienceState.S3_RECOVERY_CONSTRAINED,
            ResilienceState.S4_RECOVERY_INSUFFICIENT,
        )
    )


def validate_manual_override(
    state: CCROGraphState,
    override_allocation: list,
) -> tuple[bool, str]:
    """Validate a manual override against hard constraints.

    Returns (is_valid, violation_message).
    """
    # This calls the constraint builder to re-validate
    # A manager cannot approve an allocation that violates
    # C1 (thermal), C2 (capacity), or C3 (reachability)
    return True, ""  # placeholder
