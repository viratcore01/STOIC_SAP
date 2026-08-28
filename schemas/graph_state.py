"""CCROGraphState — canonical shared state object passed between LangGraph nodes.

This is the single source of truth for the entire orchestrator. Every agent reads
from and writes deltas to this state. The LangGraph checkpointer persists this
across the human-approval boundary.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from schemas import (
    AllocationPlan,
    ApprovalDecision,
    PolicyWeights,
    ResilienceState,
    SenseEvent,
    ShelfLifeProjection,
    WritebackConfirmation,
    WritebackStatus,
)
from schemas import RecoveryOption


class SiteCapacityInfo(BaseModel):
    """Vehicle/site capacity snapshot."""

    site_id: str
    available_capacity_kg: float = 0.0
    demand_kg: float = 0.0
    available_vehicles: list[str] = Field(default_factory=list)


class VehicleInfo(BaseModel):
    """Vehicle information for the solver."""

    vehicle_id: str
    max_payload_kg: float = 0.0
    current_location: str = ""
    available_site_ids: list[str] = Field(default_factory=list)
    transit_times: dict[str, float] = Field(default_factory=dict)  # site_id -> hours


class CCROGraphState(BaseModel):
    """LangGraph checkpointed state — the single source of truth.

    Fields are organized by owner (writer). All agents consume the shared state
    but only write to their designated fields.
    """

    # --- Orchestrator-owned fields ---
    resilience_state: ResilienceState = ResilienceState.S1_STABLE
    capacity_margin: float = 1.0  # (ΣC_available − ΣDemand) / ΣDemand
    thread_id: str = ""
    tick_count: int = 0

    # --- Sensing Agent outputs ---
    telemetry_buffer: list[SenseEvent] = Field(default_factory=list)

    # --- Impact Agent outputs ---
    shelf_life_projections: dict[str, ShelfLifeProjection] = Field(
        default_factory=dict
    )  # site_id -> projection

    # --- Recovery Agent outputs ---
    recovery_options: list[RecoveryOption] = Field(default_factory=list)
    residual_capacity_after_recovery: float = 0.0

    # --- Policy Agent outputs (with TTL for speculative prefetch) ---
    policy_weights: Optional[PolicyWeights] = None
    policy_weights_prefetched: bool = False
    policy_weights_ttl_remaining_seconds: float = 0.0

    # --- Scarcity Engine outputs ---
    priority_scores: dict[str, float] = Field(default_factory=dict)  # site_id -> P_i
    proposed_allocation: Optional[AllocationPlan] = None

    # --- Governance UI outputs ---
    approval_record: Optional[ApprovalDecision] = None

    # --- Execution Agent outputs ---
    writeback_status: WritebackStatus = WritebackStatus.PENDING
    writeback_confirmation: Optional[WritebackConfirmation] = None

    # --- Live data snapshots (read from SAP, refreshed per episode) ---
    site_capacities: dict[str, SiteCapacityInfo] = Field(default_factory=dict)
    vehicles: dict[str, VehicleInfo] = Field(default_factory=dict)
    total_demand: float = 0.0
    total_available_capacity: float = 0.0

    def compute_capacity_margin(self) -> float:
        """Recompute capacity margin from live data."""
        if self.total_demand <= 0:
            self.capacity_margin = 1.0
        else:
            self.capacity_margin = (
                self.total_available_capacity - self.total_demand
            ) / self.total_demand
        return self.capacity_margin

    def add_sense_event(self, event: SenseEvent) -> None:
        """Append a new telemetry event to the buffer."""
        self.telemetry_buffer.append(event)
