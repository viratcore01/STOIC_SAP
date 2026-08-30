"""End-to-end dry-run: exercises all four subsystems without external services.

Run: python dry_run.py
"""
import sys
from pathlib import Path

# Ensure project root is on path
project_root = Path(__file__).resolve().parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

errors = []

def ok(msg):
    print(f"  [OK] {msg}")

def fail(msg):
    print(f"  [FAIL] {msg}")

# ---------------------------------------------------------------------------
# 1. Schema imports & validation
# ---------------------------------------------------------------------------
print("=" * 60)
print("PHASE 1: Schema imports & validation")
print("=" * 60)

try:
    from schemas import (
        ResilienceState, SenseEvent, DisruptionType, Severity,
        ShelfLifeProjection, PolicyWeights, AllocationPlan,
        ApprovalDecision, WritebackStatus, RecoveryOption, RecoveryOptionType,
    )
    from schemas.graph_state import CCROGraphState
    from schemas.audit_record import AuditChain, AuditEventType, Actor, ActorType
    ok("All schema imports OK")

    # Validate PolicyWeights Pydantic enforcement
    pw = PolicyWeights(w1=0.4, w2=0.3, w3=0.3)
    assert abs(pw.w1 + pw.w2 + pw.w3 - 1.0) < 1e-6, "Weights must sum to 1.0"
    ok(f"PolicyWeights valid: w1={pw.w1}, w2={pw.w2}, w3={pw.w3}")

    try:
        PolicyWeights(w1=0.5, w2=0.5, w3=0.5)
        errors.append("PolicyWeights should reject sum != 1.0")
    except ValueError:
        ok("PolicyWeights rejects sum != 1.0")

    # Validate CCROGraphState
    state = CCROGraphState()
    assert state.resilience_state == ResilienceState.S1_STABLE
    ok(f"CCROGraphState initial state: {state.resilience_state}")

    margin = state.compute_capacity_margin()
    ok(f"Capacity margin (no demand): {margin}")
except Exception as e:
    errors.append(f"Phase 1 (schemas): {e}")
    fail(f"{e}")

# ---------------------------------------------------------------------------
# 2. State Machine transitions
# ---------------------------------------------------------------------------
print("\n" + "=" * 60)
print("PHASE 2: Resilience State Machine (S1-S5)")
print("=" * 60)

try:
    from agents.orchestrator.state_machine import ResilienceStateMachine

    sm = ResilienceStateMachine()

    # S1: Stable
    s1 = CCROGraphState()
    assert sm.evaluate(s1) == ResilienceState.S1_STABLE
    ok("S1_STABLE (no disruption)")

    # S2: Absorbing disruption
    s2 = CCROGraphState(
        telemetry_buffer=[SenseEvent(
            site_id="TEST", disruption_type=DisruptionType.THERMAL_DRIFT,
            severity=Severity.HIGH
        )],
        total_available_capacity=2200, total_demand=1005,
    )
    s2.compute_capacity_margin()
    assert sm.evaluate(s2) == ResilienceState.S2_ABSORBING
    ok(f"S2_ABSORBING (margin={s2.capacity_margin:.2%} >= 15%)")

    # S3: Recovery constrained
    s3 = CCROGraphState(
        telemetry_buffer=[SenseEvent(
            site_id="TEST", disruption_type=DisruptionType.THERMAL_DRIFT,
            severity=Severity.CRITICAL
        )],
        total_available_capacity=1050, total_demand=1005,
    )
    s3.compute_capacity_margin()
    assert sm.evaluate(s3) == ResilienceState.S3_RECOVERY_CONSTRAINED
    ok(f"S3_RECOVERY_CONSTRAINED (margin={s3.capacity_margin:.2%} < 15%)")

    # S4: Recovery insufficient
    s4 = CCROGraphState(
        resilience_state=ResilienceState.S3_RECOVERY_CONSTRAINED,
        telemetry_buffer=[SenseEvent(
            site_id="TEST", disruption_type=DisruptionType.THERMAL_DRIFT,
            severity=Severity.CRITICAL
        )],
        residual_capacity_after_recovery=500,
        total_demand=1005,
        total_available_capacity=1050,
    )
    assert sm.evaluate(s4) == ResilienceState.S4_RECOVERY_INSUFFICIENT
    ok("S4_RECOVERY_INSUFFICIENT (recovery exhausted)")

    # Validate transition graph
    assert sm.can_transition(ResilienceState.S1_STABLE, ResilienceState.S2_ABSORBING)
    assert sm.can_transition(ResilienceState.S4_RECOVERY_INSUFFICIENT, ResilienceState.S5_SCARCITY_ALLOCATION)
    assert not sm.can_transition(ResilienceState.S1_STABLE, ResilienceState.S5_SCARCITY_ALLOCATION)
    ok("Transition graph validation passed")

except Exception as e:
    errors.append(f"Phase 2 (state machine): {e}")
    fail(f"{e}")

# ---------------------------------------------------------------------------
# 3. Solver pipeline (constraint builder + objective + CP-SAT)
# ---------------------------------------------------------------------------
print("\n" + "=" * 60)
print("PHASE 3: Solver Pipeline (CP-SAT + constraints)")
print("=" * 60)

try:
    from solver.engines.ortools_milp import OrToolsSolver, SolverInput
    from solver.models.constraint_builder import ConstraintBuilder, VehicleConstraintInfo
    from solver.models.objective_builder import ObjectiveBuilder

    projections = {
        "CLN-001": ShelfLifeProjection(site_id="CLN-001", remaining_shelf_life_hours=18.0, demand_units=120),
        "CLN-002": ShelfLifeProjection(site_id="CLN-002", remaining_shelf_life_hours=8.0, demand_units=200),
        "CLN-003": ShelfLifeProjection(site_id="CLN-003", remaining_shelf_life_hours=36.0, demand_units=85),
        "CLN-007": ShelfLifeProjection(site_id="CLN-007", remaining_shelf_life_hours=6.0, demand_units=180),
    }
    vehicles = [
        VehicleConstraintInfo(
            vehicle_id="V1", max_payload_kg=800.0,
            transit_times={"CLN-001": 3.5, "CLN-002": 6.0, "CLN-003": 7.5, "CLN-007": 14.0},
        ),
        VehicleConstraintInfo(
            vehicle_id="V2", max_payload_kg=400.0,
            transit_times={"CLN-001": 5.0, "CLN-002": 3.0, "CLN-003": 5.5, "CLN-007": 16.0},
        ),
    ]

    pw = PolicyWeights(w1=0.4, w2=0.3, w3=0.3)

    # Step 1: Constraint builder
    cb = ConstraintBuilder(handling_buffer_hours=2.0)
    cr = cb.build(shelf_life_projections=projections, vehicles=vehicles, policy_weights=pw)
    ok(f"Constraint builder: {len(cr.feasible_variables)} feasible variables, {len(cr.dropped_sites)} dropped")

    # Verify C1 thermal constraint: CLN-007 with 6h shelf life, 14h transit -> dropped
    dropped_ids = [d.site_id for d in cr.dropped_sites]
    assert "CLN-007" in dropped_ids, "CLN-007 should be dropped (unreachable within shelf life)"
    ok("C1 thermal constraint: CLN-007 correctly dropped (6h shelf, 14h transit)")

    # Step 2: Objective builder
    obj = ObjectiveBuilder()
    ps = obj.compute_priority_scores(shelf_life_projections=projections, policy_weights=pw)
    assert len(ps.scores) > 0, "Priority scores should be computed"
    ok(f"Priority scores computed: {ps.scores}")

    # Step 3: CP-SAT solver
    si = SolverInput(
        priority_scores=ps, constraint_result=cr,
        vehicle_capacities={"V1": 800.0, "V2": 400.0}, per_unit_mass=1.0,
    )
    solver = OrToolsSolver()
    plan = solver.solve(si, obj)
    assert plan.plan_id, "Plan should have an ID"
    assert plan.solver_version == "ortools-cp-sat-9.8"
    ok(f"CP-SAT solver: {len(plan.assignments)} assignments, objective={plan.objective_value:.2f}")
    ok(f"  Snapshot hash: {plan.input_snapshot_hash[:16]}...")

    # Verify determinism
    plan2 = solver.solve(si, obj)
    assert plan.input_snapshot_hash == plan2.input_snapshot_hash, "Same input -> same hash"
    ok("Solver determinism: identical inputs -> identical hash")

except Exception as e:
    errors.append(f"Phase 3 (solver): {e}")
    fail(f"{e}")

# ---------------------------------------------------------------------------
# 4. RAG & Policy Agent (imports + Pydantic validation)
# ---------------------------------------------------------------------------
print("\n" + "=" * 60)
print("PHASE 4: RAG & Policy Agent")
print("=" * 60)

try:
    from rag.vectorstore.chroma_client import ChromaVectorStore
    from rag.schemas.policy_weights_schema import PolicyWeightsExtraction
    from agents.policy_agent.weight_extraction import WeightExtractor
    from schemas import CitedClause
    ok("All RAG/Policy Agent imports OK")

    # Test WeightExtractor heuristic
    clauses = [
        CitedClause(clause_id="SOP-001", source_doc="DHL-SOP-2026.pdf", text_excerpt="In case of thermal drift, prioritize clinical urgency", similarity_score=0.92),
        CitedClause(clause_id="SOP-002", source_doc="DHL-SOP-2026.pdf", text_excerpt="When capacity is constrained, minimize spoilage cost", similarity_score=0.87),
    ]
    extractor = WeightExtractor()
    weights = extractor.extract_weights(cited_clauses=clauses, disruption_type="thermal_drift", severity="critical")
    assert abs(weights.w1 + weights.w2 + weights.w3 - 1.0) < 1e-6, f"Extracted weights must sum to 1.0, got {weights.w1+weights.w2+weights.w3}"
    ok(f"WeightExtractor: w1={weights.w1}, w2={weights.w2}, w3={weights.w3} (confidence={weights.confidence_score})")

    # Test Pydantic validation with auto-normalization
    pwe = PolicyWeightsExtraction(w1=0.5, w2=0.4, w3=0.3)
    assert abs(pwe.w1 + pwe.w2 + pwe.w3 - 1.0) < 1e-6, "Should auto-normalize"
    ok(f"PolicyWeightsExtraction auto-normalize: w1={pwe.w1:.4f}, w2={pwe.w2:.4f}, w3={pwe.w3:.4f}")

    # Test rejection of wildly off weights
    try:
        PolicyWeightsExtraction(w1=5.0, w2=5.0, w3=5.0)
        errors.append("PolicyWeightsExtraction should reject sum=15.0")
    except Exception:
        ok("PolicyWeightsExtraction rejects sum=15.0")

except Exception as e:
    errors.append(f"Phase 4 (RAG/Policy): {e}")
    fail(f"{e}")

# ---------------------------------------------------------------------------
# 5. SAP Connectors (imports + idempotency)
# ---------------------------------------------------------------------------
print("\n" + "=" * 60)
print("PHASE 5: SAP Connectors")
print("=" * 60)

try:
    from sap_connectors.odata_client.s4hana_client import S4HANAClient
    from sap_connectors.odata_client.sap_tm_client import SAPTMClient
    from sap_connectors.idempotency.idempotency_ledger import IdempotencyLedger
    from sap_connectors.destinations.btp_destination_config import BTPDestinationService
    ok("All SAP connector imports OK")

    # Test idempotency key generation (deterministic)
    client = SAPTMClient()
    key1 = client._generate_idempotency_key("plan-001", "CLN-001", 1)
    key2 = client._generate_idempotency_key("plan-001", "CLN-001", 1)
    assert key1 == key2, "Same inputs must produce same idempotency key"
    ok(f"Idempotency key deterministic: {key1}")

    key3 = client._generate_idempotency_key("plan-001", "CLN-001", 2)
    assert key1 != key3, "Different attempt_seq must produce different key"
    ok(f"Different attempt_seq -> different key: {key3}")

    # Test BTP destination service
    btp = BTPDestinationService()
    assert btp.get_destination("S4HANA_CCRO_DEST") is not None
    assert btp.get_destination("TM_CCRO_DEST") is not None
    ok("BTP Destination Service: S4HANA and TM destinations configured")

    # Test idempotency ledger (in-memory fallback)
    ledger = IdempotencyLedger()
    import asyncio

    async def test_ledger():
        is_new, prev = await ledger.check_and_claim("test-key-001")
        assert is_new is True, "First claim should return True"
        assert prev is None
        await ledger.record_response("test-key-001", '{"status":"ok"}')

        is_new2, prev2 = await ledger.check_and_claim("test-key-001")
        assert is_new2 is False, "Replay should return False"
        assert prev2 == '{"status":"ok"}', "Should return cached response"
        return True

    result = asyncio.run(test_ledger())
    ok("Idempotency ledger: claim -> record -> replay detected")

except Exception as e:
    errors.append(f"Phase 5 (SAP connectors): {e}")
    fail(f"{e}")

# ---------------------------------------------------------------------------
# 6. Audit Chain
# ---------------------------------------------------------------------------
print("\n" + "=" * 60)
print("PHASE 6: Audit Chain Integrity")
print("=" * 60)

try:
    chain = AuditChain()
    chain.append(event_type=AuditEventType.STATE_TRANSITION, actor=Actor(type=ActorType.SYSTEM, id="orchestrator"), thread_id="dry-run")
    chain.append(event_type=AuditEventType.SOLVER_RUN, actor=Actor(type=ActorType.AGENT, id="solver"), thread_id="dry-run")
    chain.append(event_type=AuditEventType.APPROVAL_DECISION, actor=Actor(type=ActorType.HUMAN, id="ops-manager"), thread_id="dry-run")
    chain.append(event_type=AuditEventType.SAP_WRITEBACK, actor=Actor(type=ActorType.AGENT, id="execution-agent"), thread_id="dry-run")
    assert chain.verify_integrity(), "Audit chain should be valid"
    ok(f"Audit chain: {len(chain.get_records())} records, integrity verified")

    # Tamper detection
    records = chain.get_records()
    records[1].prev_record_hash = "tampered"
    assert not chain.verify_integrity(), "Tampered chain should fail"
    ok("Audit chain: tamper detection works")

except Exception as e:
    errors.append(f"Phase 6 (audit chain): {e}")
    fail(f"{e}")

# ---------------------------------------------------------------------------
# 7. Demo backend module import
# ---------------------------------------------------------------------------
print("\n" + "=" * 60)
print("PHASE 7: Demo Backend Module Import")
print("=" * 60)

try:
    from demo.backend.main import app
    ok(f"Demo backend FastAPI app loaded: {app.title} v{app.version}")
    routes = [r.path for r in app.routes if hasattr(r, "path")]
    ok(f"Routes: {len(routes)} endpoints registered")
except Exception as e:
    errors.append(f"Phase 7 (demo backend): {e}")
    fail(f"{e}")

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print("\n" + "=" * 60)
if errors:
    print(f"DRY RUN COMPLETED WITH {len(errors)} ERROR(S):")
    for i, err in enumerate(errors, 1):
        print(f"  {i}. {err}")
    sys.exit(1)
else:
    print("DRY RUN PASSED -- All 7 phases completed successfully")
    print("  Schemas, State Machine, Solver, RAG/Policy, SAP Connectors,")
    print("  Audit Chain, and Demo Backend all verified.")
    sys.exit(0)
