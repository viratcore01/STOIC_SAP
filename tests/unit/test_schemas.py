"""Unit tests for core schemas."""

import pytest
from schemas import (
    AllocationPlan,
    PolicyWeights,
    ResilienceState,
    SenseEvent,
    DisruptionType,
    Severity,
    ShelfLifeProjection,
    ApprovalDecision,
)
from schemas.audit_record import AuditChain, AuditEventType, Actor, ActorType, AuditPayload
from schemas.graph_state import CCROGraphState


class TestPolicyWeights:
    def test_valid_weights(self):
        pw = PolicyWeights(w1=0.4, w2=0.3, w3=0.3)
        assert pw.w1 + pw.w2 + pw.w3 == pytest.approx(1.0)

    def test_weights_must_sum_to_one(self):
        with pytest.raises(ValueError):
            PolicyWeights(w1=0.5, w2=0.5, w3=0.5)

    def test_weights_out_of_bounds(self):
        with pytest.raises(ValueError):
            PolicyWeights(w1=1.5, w2=0.0, w3=-0.5)

    def test_boundary_weights(self):
        pw = PolicyWeights(w1=1.0, w2=0.0, w3=0.0)
        assert pw.w1 == 1.0


class TestSenseEvent:
    def test_creation(self):
        event = SenseEvent(
            site_id="SITE-001",
            disruption_type=DisruptionType.THERMAL_DRIFT,
            severity=Severity.HIGH,
            drift_delta_celsius=3.5,
        )
        assert event.site_id == "SITE-001"
        assert event.drift_delta_celsius == 3.5
        assert event.event_id  # auto-generated


class TestResilienceState:
    def test_all_states_exist(self):
        assert ResilienceState.S1_STABLE.value == "S1_STABLE"
        assert ResilienceState.S5_SCARCITY_ALLOCATION.value == "S5_SCARCITY_ALLOCATION"


class TestAuditChain:
    def test_genesis_hash(self):
        chain = AuditChain()
        assert chain.chain_tip == "0" * 64

    def test_append_creates_record(self):
        chain = AuditChain()
        record = chain.append(
            event_type=AuditEventType.STATE_TRANSITION,
            actor=Actor(type=ActorType.SYSTEM, id="orchestrator"),
            thread_id="test-thread",
        )
        assert record.record_id
        assert record.prev_record_hash == "0" * 64
        assert record.record_hash != "0" * 64
        assert chain.chain_tip == record.record_hash

    def test_chain_integrity(self):
        chain = AuditChain()
        chain.append(
            event_type=AuditEventType.STATE_TRANSITION,
            actor=Actor(type=ActorType.SYSTEM, id="orchestrator"),
        )
        chain.append(
            event_type=AuditEventType.SOLVER_RUN,
            actor=Actor(type=ActorType.AGENT, id="solver"),
        )
        chain.append(
            event_type=AuditEventType.APPROVAL_DECISION,
            actor=Actor(type=ActorType.HUMAN, id="ops-manager"),
        )
        assert chain.verify_integrity()
        assert len(chain.get_records()) == 3

    def test_chain_integrity_detects_tampering(self):
        chain = AuditChain()
        chain.append(
            event_type=AuditEventType.STATE_TRANSITION,
            actor=Actor(type=ActorType.SYSTEM, id="orchestrator"),
        )
        r2 = chain.append(
            event_type=AuditEventType.SOLVER_RUN,
            actor=Actor(type=ActorType.AGENT, id="solver"),
        )
        # Tamper with the second record's prev_record_hash
        r2.prev_record_hash = "tampered"
        assert not chain.verify_integrity()


class TestCCROGraphState:
    def test_initial_state(self):
        state = CCROGraphState()
        assert state.resilience_state == ResilienceState.S1_STABLE
        assert state.capacity_margin == 1.0
        assert len(state.telemetry_buffer) == 0

    def test_compute_capacity_margin(self):
        state = CCROGraphState(
            total_available_capacity=80,
            total_demand=100,
        )
        margin = state.compute_capacity_margin()
        assert margin == pytest.approx(-0.2)

    def test_compute_capacity_margin_no_demand(self):
        state = CCROGraphState(
            total_available_capacity=100,
            total_demand=0,
        )
        margin = state.compute_capacity_margin()
        assert margin == 1.0

    def test_add_sense_event(self):
        state = CCROGraphState()
        event = SenseEvent(
            site_id="SITE-001",
            disruption_type=DisruptionType.THERMAL_DRIFT,
            severity=Severity.HIGH,
        )
        state.add_sense_event(event)
        assert len(state.telemetry_buffer) == 1


class TestAllocationPlan:
    def test_creation(self):
        plan = AllocationPlan()
        assert plan.plan_id
        assert len(plan.assignments) == 0
        assert len(plan.dropped_sites) == 0
