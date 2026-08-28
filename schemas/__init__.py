"""Core data contracts shared across all CCRO modules."""

from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ResilienceState(str, enum.Enum):
    """Resilience State Machine states (S1-S5)."""

    S1_STABLE = "S1_STABLE"
    S2_ABSORBING = "S2_ABSORBING_DISRUPTION"
    S3_RECOVERY_CONSTRAINED = "S3_RECOVERY_CONSTRAINED"
    S4_RECOVERY_INSUFFICIENT = "S4_RECOVERY_INSUFFICIENT"
    S5_SCARCITY_ALLOCATION = "S5_SCARCITY_ALLOCATION"


class DisruptionType(str, enum.Enum):
    THERMAL_DRIFT = "thermal_drift"
    WEATHER = "weather"
    PORT_DISRUPTION = "port_disruption"
    CARRIER_DELAY = "carrier_delay"
    INFRASTRUCTURE = "infrastructure"


class Severity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RecoveryOptionType(str, enum.Enum):
    ROUTE = "route"
    WAREHOUSE = "warehouse"
    FLEET = "fleet"


class WritebackStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL_FAILURE = "partial_failure"


# ---------------------------------------------------------------------------
# Telemetry & Events
# ---------------------------------------------------------------------------


class SenseEvent(BaseModel):
    """Inbound telemetry/disruption event from Sensing Agent."""

    event_id: str = Field(default_factory=lambda: uuid4().hex)
    site_id: Optional[str] = None
    route_id: Optional[str] = None
    drift_delta_celsius: float = 0.0
    disruption_type: DisruptionType
    severity: Severity
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    geo_lat: Optional[float] = None
    geo_lon: Optional[float] = None
    metadata: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Impact & Recovery
# ---------------------------------------------------------------------------


class ShelfLifeProjection(BaseModel):
    """Per-site shelf-life projection from Impact Agent."""

    site_id: str
    remaining_shelf_life_hours: float
    projected_stockout_date: Optional[datetime] = None
    demand_units: int = 0
    batch_ids: list[str] = Field(default_factory=list)


class RecoveryOption(BaseModel):
    """Single recovery option from Recovery Agent Cluster."""

    option_id: str = Field(default_factory=lambda: uuid4().hex)
    option_type: RecoveryOptionType
    delta_capacity: float = 0.0
    cost_estimate: float = 0.0
    feasibility_score: float = 0.0
    description: str = ""
    affected_site_ids: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Policy & Allocation
# ---------------------------------------------------------------------------


class CitedClause(BaseModel):
    """A cited SOP clause from RAG retrieval."""

    clause_id: str
    source_doc: str
    doc_version: str = ""
    similarity_score: float = 0.0
    text_excerpt: str = ""


class PolicyWeights(BaseModel):
    """Policy weight coefficients from Policy Agent.

    w1 + w2 + w3 = 1 enforced by Pydantic validator.
    """

    w1: float = Field(ge=0.0, le=1.0, description="Clinical Urgency weight")
    w2: float = Field(ge=0.0, le=1.0, description="Operational Simplicity weight")
    w3: float = Field(ge=0.0, le=1.0, description="Value Preservation Index weight")

    cited_clauses: list[CitedClause] = Field(default_factory=list)
    confidence_score: float = Field(ge=0.0, le=1.0, default=0.5)

    def model_post_init(self, __context: object) -> None:
        if abs(self.w1 + self.w2 + self.w3 - 1.0) > 1e-6:
            raise ValueError(
                f"Weights must sum to 1.0, got {self.w1 + self.w2 + self.w3}"
            )


class SiteAllocation(BaseModel):
    """Single site allocation assignment."""

    site_id: str
    allocated_units: int = 0
    vehicle_id: str = ""
    priority_score: float = 0.0
    payload_mass_kg: float = 0.0


class DroppedSite(BaseModel):
    """A site that could not be allocated."""

    site_id: str
    reason: str  # e.g. "unreachable_within_shelf_life"
    priority_score: float = 0.0


class AllocationPlan(BaseModel):
    """Output of Scarcity Allocation Engine / Solver."""

    plan_id: str = Field(default_factory=lambda: uuid4().hex)
    assignments: list[SiteAllocation] = Field(default_factory=list)
    dropped_sites: list[DroppedSite] = Field(default_factory=list)
    objective_value: float = 0.0
    solver_version: str = ""
    input_snapshot_hash: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Governance & Approval
# ---------------------------------------------------------------------------


class ApprovalDecision(BaseModel):
    """Human approval decision from Governance UI."""

    plan_id: str
    approver_id: str  # SAP-authenticated user ID
    decision: str  # "approved", "modified", "rejected"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    modifications: list[SiteAllocation] = Field(default_factory=list)
    comments: str = ""


class WritebackConfirmation(BaseModel):
    """Confirmation from SAP writeback."""

    freight_order_ids: list[str] = Field(default_factory=list)
    sap_response_codes: list[str] = Field(default_factory=list)
    writeback_status: WritebackStatus = WritebackStatus.PENDING
    error_message: str = ""


class WritebackConflict(Exception):
    """Raised when SAP returns 412 Precondition Failed."""

    def __init__(self, freight_order_id: str, message: str = "") -> None:
        self.freight_order_id = freight_order_id
        super().__init__(f"Writeback conflict for {freight_order_id}: {message}")
