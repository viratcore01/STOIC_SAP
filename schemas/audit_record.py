"""Immutable Audit Record schema with hash-chaining for 21 CFR Part 11 compliance.

Each record embeds the previous record's SHA-256 hash, forming a tamper-evident chain.
Appended to a WORM object store or SAP HANA Audit Log.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field, computed_field


class AuditEventType(str, Enum):
    STATE_TRANSITION = "STATE_TRANSITION"
    POLICY_RETRIEVAL = "POLICY_RETRIEVAL"
    SOLVER_RUN = "SOLVER_RUN"
    APPROVAL_DECISION = "APPROVAL_DECISION"
    SAP_WRITEBACK = "SAP_WRITEBACK"
    WRITEBACK_FAILURE = "WRITEBACK_FAILURE"


class ActorType(str, Enum):
    SYSTEM = "SYSTEM"
    AGENT = "AGENT"
    HUMAN = "HUMAN"


class Actor(BaseModel):
    """Attributable actor — sourced from SAP-authenticated session principal."""

    type: ActorType
    id: str  # agent name+version, or approver_id (SAP user ID)


class SOPClauseReference(BaseModel):
    """Reference to a cited SOP clause."""

    clause_id: str
    source_doc: str
    doc_version: str = ""


class AuditPayload(BaseModel):
    """Variable payload fields depending on event type."""

    rag_confidence_score: Optional[float] = None
    cited_sop_clauses: list[SOPClauseReference] = Field(default_factory=list)
    policy_weights: Optional[dict[str, float]] = None  # {w1, w2, w3}
    solver_version: Optional[str] = None
    input_snapshot_hash: Optional[str] = None  # enables deterministic re-run
    approval_decision: Optional[str] = None  # approved, modified, rejected
    sap_response_codes: list[str] = Field(default_factory=list)
    previous_state: Optional[str] = None
    new_state: Optional[str] = None
    allocation_plan_id: Optional[str] = None
    error_details: Optional[str] = None


class AuditRecord(BaseModel):
    """Immutable audit record with hash-chaining.

    Designed to satisfy FDA 21 CFR Part 11:
    - attributable (actor from SAML/OAuth2 assertion)
    - legible (structured JSON)
    - contemporaneous (server-side NTP-synced timestamp)
    - original (append-only)
    - accurate (hash-chained for tamper detection)
    """

    record_id: str = Field(default_factory=lambda: uuid4().hex)
    prev_record_hash: str = Field(
        default="0" * 64, description="SHA-256 of previous record (genesis = zeros)"
    )
    event_type: AuditEventType
    timestamp_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    thread_id: str = ""
    allocation_plan_id: Optional[str] = None
    actor: Actor
    payload: AuditPayload = Field(default_factory=AuditPayload)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def record_hash(self) -> str:
        """Compute SHA-256 hash of this record for chain integrity."""
        hash_input = {
            "record_id": self.record_id,
            "prev_record_hash": self.prev_record_hash,
            "event_type": self.event_type.value,
            "timestamp_utc": self.timestamp_utc.isoformat(),
            "thread_id": self.thread_id,
            "allocation_plan_id": self.allocation_plan_id,
            "actor_type": self.actor.type.value,
            "actor_id": self.actor.id,
            "payload": self.payload.model_dump(),
        }
        raw = json.dumps(hash_input, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()


class AuditChain:
    """Manages the append-only hash chain of audit records."""

    def __init__(self, initial_chain_tip: str = "0" * 64) -> None:
        self._chain_tip = initial_chain_tip
        self._records: list[AuditRecord] = []

    @property
    def chain_tip(self) -> str:
        return self._chain_tip

    def append(
        self,
        event_type: AuditEventType,
        actor: Actor,
        thread_id: str = "",
        allocation_plan_id: Optional[str] = None,
        payload: Optional[AuditPayload] = None,
        timestamp_utc: Optional[datetime] = None,
    ) -> AuditRecord:
        """Create and append a new audit record to the chain."""
        record = AuditRecord(
            prev_record_hash=self._chain_tip,
            event_type=event_type,
            actor=actor,
            thread_id=thread_id,
            allocation_plan_id=allocation_plan_id,
            payload=payload or AuditPayload(),
        )
        if timestamp_utc is not None:
            record.timestamp_utc = timestamp_utc

        # The record_hash is computed, then becomes the new chain tip
        self._chain_tip = record.record_hash
        self._records.append(record)
        return record

    def verify_integrity(self) -> bool:
        """Verify the entire chain's hash integrity."""
        expected_prev = "0" * 64
        for record in self._records:
            if record.prev_record_hash != expected_prev:
                return False
            expected_prev = record.record_hash
        return True

    def get_records(self) -> list[AuditRecord]:
        """Return all records in the chain."""
        return list(self._records)
