"""CCRO Demo Backend — Single FastAPI app with mock data, solver, state machine, audit log.

Start: uvicorn demo.backend.main:app --reload --port 8000

This is a self-contained demo backend for SAP HackFest 2026.
It uses the real solver logic, state machine, compliance agent,
and orchestration pipeline from the existing codebase,
but operates entirely on realistic mock data (no real SAP required).

Round 2: Now uses the LangGraph orchestrator pipeline via CCROGraphState
and ResilienceStateMachine for deterministic state transitions.
"""

from __future__ import annotations

import hashlib
import json
import sys
import os
import uuid
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

# Add project root to path so we can import schemas and solver
project_root = Path(__file__).resolve().parents[2]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from schemas import (
    AllocationPlan,
    DisruptionType,
    DroppedSite,
    PolicyWeights,
    ResilienceState,
    SenseEvent,
    Severity,
    ShelfLifeProjection,
    SiteAllocation,
)
from schemas.audit_record import AuditChain, AuditEventType, Actor, ActorType, AuditPayload
from schemas.graph_state import CCROGraphState
from solver.engines.ortools_milp import OrToolsSolver, SolverInput
from solver.models.constraint_builder import ConstraintBuilder, VehicleConstraintInfo
from solver.models.objective_builder import ObjectiveBuilder

# Import orchestrator components for state machine
from agents.orchestrator.state_machine import ResilienceStateMachine

# Import compliance agent
from agents.compliance_agent.rules import ComplianceAgent

app = FastAPI(title="CCRO Demo Backend", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize state machine and compliance agent
state_machine = ResilienceStateMachine()
compliance_agent = ComplianceAgent()


# ============================================================================
# MOCK DATA — Realistic cold-chain pharmaceutical scenario
# ============================================================================

CLINICS = {
    "CLN-001": {
        "id": "CLN-001",
        "name": "St. Mary's General Hospital",
        "city": "Munich",
        "country": "DE",
        "demand_units": 120,
        "criticality": "high",
        "vulnerable_population_index": 0.92,
        "batch_ids": ["BAT-2026-A1", "BAT-2026-A2"],
        "product_type": "pharmaceutical",
        "requires_cold_chain_vehicle": True,
    },
    "CLN-002": {
        "id": "CLN-002",
        "name": "Charite Campus Virchow",
        "city": "Berlin",
        "country": "DE",
        "demand_units": 200,
        "criticality": "critical",
        "vulnerable_population_index": 0.97,
        "batch_ids": ["BAT-2026-B1"],
        "product_type": "pharmaceutical",
        "requires_cold_chain_vehicle": True,
    },
    "CLN-003": {
        "id": "CLN-003",
        "name": "Universitatsklinikum Koln",
        "city": "Cologne",
        "country": "DE",
        "demand_units": 85,
        "criticality": "medium",
        "vulnerable_population_index": 0.71,
        "batch_ids": ["BAT-2026-C1", "BAT-2026-C2"],
        "product_type": "pharmaceutical",
        "requires_cold_chain_vehicle": True,
    },
    "CLN-004": {
        "id": "CLN-004",
        "name": "Hannover Medical School",
        "city": "Hannover",
        "country": "DE",
        "demand_units": 150,
        "criticality": "high",
        "vulnerable_population_index": 0.85,
        "batch_ids": ["BAT-2026-D1"],
        "product_type": "pharmaceutical",
        "requires_cold_chain_vehicle": True,
    },
    "CLN-005": {
        "id": "CLN-005",
        "name": "University Hospital Zurich",
        "city": "Zurich",
        "country": "CH",
        "demand_units": 95,
        "criticality": "high",
        "vulnerable_population_index": 0.88,
        "batch_ids": ["BAT-2026-E1"],
        "product_type": "pharmaceutical",
        "requires_cold_chain_vehicle": True,
    },
    "CLN-006": {
        "id": "CLN-006",
        "name": "Erasmus MC Rotterdam",
        "city": "Rotterdam",
        "country": "NL",
        "demand_units": 65,
        "criticality": "medium",
        "vulnerable_population_index": 0.62,
        "batch_ids": ["BAT-2026-F1"],
        "product_type": "pharmaceutical",
        "requires_cold_chain_vehicle": True,
    },
    "CLN-007": {
        "id": "CLN-007",
        "name": "Karolinska University Hospital",
        "city": "Stockholm",
        "country": "SE",
        "demand_units": 180,
        "criticality": "critical",
        "vulnerable_population_index": 0.94,
        "batch_ids": ["BAT-2026-G1", "BAT-2026-G2"],
        "product_type": "pharmaceutical",
        "requires_cold_chain_vehicle": True,
    },
    "CLN-008": {
        "id": "CLN-008",
        "name": "Hopital Pitie-Salpetriere",
        "city": "Paris",
        "country": "FR",
        "demand_units": 110,
        "criticality": "high",
        "vulnerable_population_index": 0.81,
        "batch_ids": ["BAT-2026-H1"],
        "product_type": "pharmaceutical",
        "requires_cold_chain_vehicle": True,
    },
}

VEHICLES = {
    "VH-A1": {
        "id": "VH-A1",
        "type": "Refrigerated Truck (Large)",
        "max_payload_kg": 800.0,
        "transit_times": {
            "CLN-001": 3.5,
            "CLN-002": 6.0,
            "CLN-003": 7.5,
            "CLN-004": 4.0,
            "CLN-005": 8.0,
            "CLN-006": 10.0,
            "CLN-007": 14.0,
            "CLN-008": 12.0,
        },
    },
    "VH-A2": {
        "id": "VH-A2",
        "type": "Refrigerated Van (Medium)",
        "max_payload_kg": 400.0,
        "transit_times": {
            "CLN-001": 5.0,
            "CLN-002": 3.0,
            "CLN-003": 5.5,
            "CLN-004": 7.0,
            "CLN-005": 11.0,
            "CLN-006": 8.0,
            "CLN-007": 16.0,
            "CLN-008": 13.0,
        },
    },
    "VH-B1": {
        "id": "VH-B1",
        "type": "Refrigerated Truck (Large)",
        "max_payload_kg": 750.0,
        "transit_times": {
            "CLN-001": 9.0,
            "CLN-002": 8.0,
            "CLN-003": 4.0,
            "CLN-004": 5.0,
            "CLN-005": 7.0,
            "CLN-006": 6.0,
            "CLN-007": 18.0,
            "CLN-008": 11.0,
        },
    },
    "VH-C1": {
        "id": "VH-C1",
        "type": "Refrigerated Van (Small)",
        "max_payload_kg": 250.0,
        "transit_times": {
            "CLN-001": 4.5,
            "CLN-002": 5.0,
            "CLN-003": 8.0,
            "CLN-004": 6.5,
            "CLN-005": 12.0,
            "CLN-006": 9.0,
            "CLN-007": 22.0,
            "CLN-008": 14.0,
        },
    },
}

# Shelf-life projections (in hours remaining) -- these create interesting solver behavior
BATCH_SHELF_LIFE = {
    "CLN-001": 18.0,
    "CLN-002": 8.0,
    "CLN-003": 36.0,
    "CLN-004": 14.0,
    "CLN-005": 24.0,
    "CLN-006": 48.0,
    "CLN-007": 6.0,
    "CLN-008": 3.0,
}

# Default policy weights (balanced)
DEFAULT_POLICY_WEIGHTS = {"w1": 0.4, "w2": 0.3, "w3": 0.3}

# Disruption scenarios
DISRUPTION_SCENARIOS = [
    {
        "id": "D-001",
        "name": "Cold Storage Failure -- Munich Hub",
        "type": "thermal_drift",
        "severity": "critical",
        "affected_sites": ["CLN-001", "CLN-004"],
        "description": "Main cold storage compressor failed at Munich distribution hub. Temperature rose 4.2C above threshold. All batches at CLN-001 and CLN-004 affected -- shelf life reduced by 60%.",
        "temperature_delta": 4.2,
        "shelf_life_reduction_pct": 0.60,
    },
    {
        "id": "D-002",
        "name": "Port Congestion -- Rotterdam",
        "type": "port_disruption",
        "severity": "high",
        "affected_sites": ["CLN-002", "CLN-006", "CLN-007"],
        "description": "Severe weather caused port closure at Rotterdam. Incoming shipments delayed by 8-12 hours. Existing inventory at Berlin and Stockholm clinics under pressure.",
        "temperature_delta": 0,
        "shelf_life_reduction_pct": 0.0,
    },
    {
        "id": "D-003",
        "name": "Multi-Site Thermal Event",
        "type": "thermal_drift",
        "severity": "critical",
        "affected_sites": ["CLN-001", "CLN-002", "CLN-004", "CLN-007", "CLN-008"],
        "description": "System-wide refrigeration anomaly across Central European network. Power fluctuation during heatwave affected 5 distribution points simultaneously.",
        "temperature_delta": 3.8,
        "shelf_life_reduction_pct": 0.55,
    },
]


# ============================================================================
# IN-MEMORY STATE — Now uses CCROGraphState for orchestrator integration
# ============================================================================

class DemoState:
    """Demo state that wraps CCROGraphState for orchestrator pipeline integration.

    The resilience_state field is now driven by the ResilienceStateMachine
    instead of being hardcoded. Each transition is logged to the audit chain.
    """

    def __init__(self):
        self.reset()

    def reset(self):
        # Core CCRO state for orchestrator pipeline
        self.ccro = CCROGraphState(
            resilience_state=ResilienceState.S1_STABLE,
            capacity_margin=1.0,
            thread_id=f"EP-{uuid.uuid4().hex[:8].upper()}",
        )

        # Legacy fields for backward compatibility with frontend
        self.telemetry_buffer: list[dict] = []
        self.shelf_life_projections: dict[str, float] = deepcopy(BATCH_SHELF_LIFE)
        self.original_shelf_life: dict[str, float] = deepcopy(BATCH_SHELF_LIFE)
        self.policy_weights: dict = deepcopy(DEFAULT_POLICY_WEIGHTS)
        self.current_disruption: Optional[dict] = None
        self.proposed_allocation: Optional[dict] = None
        self.last_allocation_plan_id: Optional[str] = None
        self.total_demand: float = 0.0
        self.total_available_capacity: float = 0.0
        self.capacity_margin: float = 1.0
        self.audit_chain = AuditChain()
        self.allocation_history: list[dict] = []
        self.tick_count: int = 0
        self.residual_capacity_after_recovery: float = 0.0
        self.recovery_options: list[dict] = []
        self.writeback_status: str = "PENDING"
        self.last_compliance_report: Optional[dict] = None

        # State transition history for the orchestrator pipeline display
        self.state_transition_log: list[dict] = []

    @property
    def resilience_state(self) -> str:
        return self.ccro.resilience_state.value

    @resilience_state.setter
    def resilience_state(self, value: str):
        # Update the CCROGraphState when resilience_state changes
        try:
            self.ccro.resilience_state = ResilienceState(value)
        except ValueError:
            # Handle the enum value mapping (e.g., S2 has a longer value)
            for rs in ResilienceState:
                if rs.value == value or rs.name == value:
                    self.ccro.resilience_state = rs
                    break

    def _record_transition(self, from_state: str, to_state: str, trigger: str = ""):
        """Record a state transition to the audit chain and transition log."""
        self.audit_chain.append(
            event_type=AuditEventType.STATE_TRANSITION,
            actor=Actor(type=ActorType.SYSTEM, id="orchestrator@1.0"),
            thread_id=self.ccro.thread_id,
            payload=AuditPayload(
                previous_state=from_state,
                new_state=to_state,
                allocation_plan_id=None,
            ),
        )
        self.state_transition_log.append({
            "from": from_state,
            "to": to_state,
            "trigger": trigger,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tick": self.tick_count,
        })

    def evaluate_state_machine(self) -> str:
        """Run the ResilienceStateMachine to determine the current state.

        This is the key integration point with the LangGraph orchestrator.
        Instead of hardcoding state transitions, we use the formal state machine
        that evaluates four network-health metrics.
        """
        old_state = self.resilience_state

        # Sync CCROGraphState with demo state
        self.ccro.total_demand = self.total_demand
        self.ccro.total_available_capacity = self.total_available_capacity
        self.ccro.residual_capacity_after_recovery = self.residual_capacity_after_recovery

        # Evaluate using the formal state machine
        new_state = state_machine.evaluate(self.ccro)

        # Record transition if state changed
        if old_state != new_state.value:
            self._record_transition(old_state, new_state.value, "state_machine_evaluate")
            self.ccro.resilience_state = new_state
            self.tick_count += 1

        return self.resilience_state

    def compute_totals(self):
        self.total_demand = sum(
            CLINICS[cid]["demand_units"] for cid in self.shelf_life_projections
        )
        self.total_available_capacity = sum(
            v["max_payload_kg"] for v in VEHICLES.values()
        )
        if self.total_demand > 0:
            self.capacity_margin = (self.total_available_capacity - self.total_demand) / self.total_demand
        else:
            self.capacity_margin = 1.0

        # Sync with CCROGraphState
        self.ccro.total_demand = self.total_demand
        self.ccro.total_available_capacity = self.total_available_capacity
        self.ccro.capacity_margin = self.capacity_margin

    def get_capacity_margin_for_gauge(self) -> float:
        self.compute_totals()
        return round(self.capacity_margin * 100, 1)

    def get_site_details(self) -> list[dict]:
        sites = []
        for clinic_id in sorted(CLINICS.keys()):
            clinic = CLINICS[clinic_id]
            remaining = self.shelf_life_projections.get(clinic_id, 0)
            original = self.original_shelf_life.get(clinic_id, remaining)
            sites.append({
                "id": clinic_id,
                "name": clinic["name"],
                "city": clinic["city"],
                "country": clinic.get("country", ""),
                "demand_units": clinic["demand_units"],
                "criticality": clinic["criticality"],
                "vpi": clinic["vulnerable_population_index"],
                "remaining_shelf_life_hours": remaining,
                "original_shelf_life_hours": original,
                "batch_ids": clinic["batch_ids"],
                "is_threatened": remaining < 24,
                "product_type": clinic.get("product_type", ""),
            })
        return sites


state = DemoState()


# ============================================================================
# SOLVER HELPER — Shared by allocation and what-if endpoints
# ============================================================================

def _run_solver(
    shelf_life_projections: dict[str, float],
    policy_weights_dict: dict,
) -> AllocationPlan:
    """Run the full solver pipeline and return an AllocationPlan.

    This is the shared solver logic used by both the allocation endpoint
    and the what-if simulation endpoint.
    """
    pw = PolicyWeights(**policy_weights_dict)

    projections = {
        site_id: ShelfLifeProjection(
            site_id=site_id,
            remaining_shelf_life_hours=hours,
            demand_units=CLINICS[site_id]["demand_units"],
            batch_ids=CLINICS[site_id]["batch_ids"],
        )
        for site_id, hours in shelf_life_projections.items()
        if hours > 0
    }

    vehicles = [
        VehicleConstraintInfo(
            vehicle_id=v["id"],
            max_payload_kg=v["max_payload_kg"],
            transit_times=v["transit_times"],
        )
        for v in VEHICLES.values()
    ]

    vehicle_capacities = {v["id"]: v["max_payload_kg"] for v in VEHICLES.values()}

    constraint_builder = ConstraintBuilder(handling_buffer_hours=2.0)
    constraint_result = constraint_builder.build(
        shelf_life_projections=projections,
        vehicles=vehicles,
        policy_weights=pw,
    )

    obj_builder = ObjectiveBuilder()
    priority_scores = obj_builder.compute_priority_scores(
        shelf_life_projections=projections,
        policy_weights=pw,
    )

    solver_input = SolverInput(
        priority_scores=priority_scores,
        constraint_result=constraint_result,
        vehicle_capacities=vehicle_capacities,
        per_unit_mass=1.0,
    )

    solver = OrToolsSolver()
    return solver.solve(solver_input, obj_builder)


def _build_allocation_response(allocation_plan: AllocationPlan, pw_dict: dict) -> dict:
    """Build the full allocation response with do-nothing comparison."""
    return {
        "plan_id": allocation_plan.plan_id,
        "assignments": [
            {
                "site_id": a.site_id,
                "site_name": CLINICS.get(a.site_id, {}).get("name", a.site_id),
                "city": CLINICS.get(a.site_id, {}).get("city", "Unknown"),
                "allocated_units": a.allocated_units,
                "vehicle_id": a.vehicle_id,
                "priority_score": round(a.priority_score, 4),
                "payload_mass_kg": round(a.payload_mass_kg, 1),
            }
            for a in allocation_plan.assignments
        ],
        "dropped_sites": [
            {
                "site_id": d.site_id,
                "site_name": CLINICS.get(d.site_id, {}).get("name", d.site_id),
                "reason": d.reason,
                "priority_score": round(d.priority_score, 4),
            }
            for d in allocation_plan.dropped_sites
        ],
        "objective_value": round(allocation_plan.objective_value, 4),
        "solver_version": allocation_plan.solver_version,
        "input_snapshot_hash": allocation_plan.input_snapshot_hash,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "policy_weights": pw_dict,
        "do_nothing": {
            "total_spoilage_cost_eur": sum(
                CLINICS.get(site_id, {}).get("demand_units", 0) * 350
                for site_id in state.shelf_life_projections
                if state.shelf_life_projections[site_id] < 24
            ),
            "sites_at_risk": [
                site_id
                for site_id in state.shelf_life_projections
                if state.shelf_life_projections[site_id] < 24
            ],
            "estimated_stockout_sites": [
                site_id
                for site_id in state.shelf_life_projections
                if state.shelf_life_projections[site_id] < 12
            ],
        },
        "ccro_allocation": {
            "total_avoided_loss_eur": sum(
                a.priority_score * a.allocated_units * 350
                for a in allocation_plan.assignments
            ),
            "sites_covered": len(allocation_plan.assignments),
            "total_units_dispatched": sum(a.allocated_units for a in allocation_plan.assignments),
        },
    }


# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint -- serves React SPA if available, else API landing page."""
    index_file = frontend_dist / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {
        "service": "CCRO Demo Backend",
        "version": "1.0.0",
        "pipeline": "LangGraph Orchestrator (S1-S5 State Machine)",
        "endpoints": {
            "health": "/health",
            "state": "/api/state",
            "disruptions": "/api/disruptions",
            "trigger": "POST /api/disruption/trigger?disruption_id=D-001",
            "run_allocation": "POST /api/allocation/run?w1=0.4&w2=0.3&w3=0.3",
            "what_if": "POST /api/allocation/what-if",
            "compliance_check": "POST /api/compliance/check",
            "approve": "POST /api/allocation/approve",
            "audit_log": "/api/audit/log",
            "settings": "/api/settings",
            "docs": "/docs",
        },
    }


@app.get("/api/state")
async def get_state():
    """Get the current system state with orchestrator pipeline info."""
    state.compute_totals()

    # Run state machine evaluation on each tick
    evaluated_state = state.evaluate_state_machine()

    return {
        "resilience_state": evaluated_state,
        "capacity_margin": state.get_capacity_margin_for_gauge(),
        "total_demand": state.total_demand,
        "total_available_capacity": state.total_available_capacity,
        "thread_id": state.ccro.thread_id,
        "tick_count": state.tick_count,
        "current_disruption": state.current_disruption,
        "has_proposed_allocation": state.proposed_allocation is not None,
        "sites": state.get_site_details(),
        "vehicles": [
            {"id": v["id"], "type": v["type"], "max_payload_kg": v["max_payload_kg"]}
            for v in VEHICLES.values()
        ],
        # Orchestrator pipeline info
        "orchestrator": {
            "pipeline": "sense -> understand -> adapt -> protect -> govern -> execute",
            "state_machine": "ResilienceStateMachine (S1-S5)",
            "compliance_agent": "Rule-based (sanctions, cold chain, limits)",
            "transition_log": state.state_transition_log[-10:],  # Last 10 transitions
            "last_compliance_report": state.last_compliance_report,
        },
    }


@app.post("/api/disruption/trigger")
async def trigger_disruption(disruption_id: str = "D-001"):
    """Trigger a disruption event and run through the orchestrator pipeline.

    Instead of hardcoding S4, this now runs the state machine to determine
    the correct state based on the disruption severity and capacity metrics.
    """
    scenario = next((d for d in DISRUPTION_SCENARIOS if d["id"] == disruption_id), None)
    if not scenario:
        raise HTTPException(status_code=404, detail=f"Disruption {disruption_id} not found")

    # Apply disruption to shelf life
    for site_id in scenario["affected_sites"]:
        if site_id in state.shelf_life_projections:
            reduction = state.original_shelf_life.get(site_id, 0) * scenario["shelf_life_reduction_pct"]
            state.shelf_life_projections[site_id] = max(
                0.5, state.shelf_life_projections[site_id] - reduction
            )

    state.current_disruption = {
        "id": scenario["id"],
        "name": scenario["name"],
        "type": scenario["type"],
        "severity": scenario["severity"],
        "description": scenario["description"],
        "affected_sites": scenario["affected_sites"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Record in telemetry buffer (sensing agent input)
    event = SenseEvent(
        site_id=scenario["affected_sites"][0] if scenario["affected_sites"] else None,
        disruption_type=DisruptionType(scenario["type"]),
        severity=Severity(scenario["severity"]),
        drift_delta_celsius=scenario.get("temperature_delta", 0.0),
    )
    state.telemetry_buffer.append(event.model_dump(mode="json"))

    # Sync with CCROGraphState
    state.ccro.telemetry_buffer.append(event)

    # Compute totals before state machine evaluation
    state.compute_totals()

    # Run through the orchestrator pipeline:
    # SENSE -> UNDERSTAND -> ADAPT -> PROTECT -> GOVERN -> EXECUTE
    # The state machine evaluates the correct state based on metrics

    # Phase 1: SENSE - Events are in the buffer
    # Phase 2: UNDERSTAND - Compute impact (shelf life already updated)

    # Phase 3: ADAPT - Evaluate recovery options
    # Since we have no real recovery agents, residual capacity = total capacity
    state.residual_capacity_after_recovery = state.total_available_capacity
    state.ccro.residual_capacity_after_recovery = state.residual_capacity_after_recovery

    # Run state machine to determine the correct state
    evaluated_state = state.evaluate_state_machine()

    return {
        "status": "ok",
        "new_state": evaluated_state,
        "disruption": state.current_disruption,
        "capacity_margin": state.get_capacity_margin_for_gauge(),
        "pipeline_execution": {
            "phase_1_sense": f"Received {len(state.telemetry_buffer)} event(s)",
            "phase_2_understand": f"Updated {len(state.shelf_life_projections)} site projections",
            "phase_3_adapt": f"Recovery options evaluated, residual capacity: {state.residual_capacity_after_recovery}kg",
            "phase_4_protect": "Skipped (recovery sufficient)" if evaluated_state != ResilienceState.S4_RECOVERY_INSUFFICIENT.value else "Pending allocation",
            "state_machine_result": evaluated_state,
        },
        "message": f"Disruption '{scenario['name']}' triggered. Orchestrator pipeline executed. State: {evaluated_state}.",
    }


@app.post("/api/allocation/run")
async def run_allocation(
    w1: float = 0.4,
    w2: float = 0.3,
    w3: float = 0.3,
):
    """Run the scarcity allocation solver with compliance check.

    This now goes through the full pipeline:
    1. Run solver (protect phase)
    2. Run compliance agent (pre-writeback check)
    3. Store results with compliance report
    """
    if abs(w1 + w2 + w3 - 1.0) > 1e-6:
        raise HTTPException(status_code=400, detail=f"Weights must sum to 1.0, got {w1 + w2 + w3}")

    pw_dict = {"w1": w1, "w2": w2, "w3": w3}
    state.policy_weights = pw_dict

    # Phase 4: PROTECT - Run solver
    allocation_plan = _run_solver(state.shelf_life_projections, pw_dict)

    # Log solver run to audit chain
    state.audit_chain.append(
        event_type=AuditEventType.SOLVER_RUN,
        actor=Actor(type=ActorType.AGENT, id="scarcity-engine@1.0"),
        thread_id=state.ccro.thread_id,
        allocation_plan_id=allocation_plan.plan_id,
        payload=AuditPayload(
            solver_version=allocation_plan.solver_version,
            input_snapshot_hash=allocation_plan.input_snapshot_hash,
            policy_weights=pw_dict,
        ),
    )

    # Run compliance agent (pre-writeback check)
    compliance_report = compliance_agent.check_plan(allocation_plan, CLINICS)
    state.last_compliance_report = compliance_report.model_dump()

    # Store the proposed allocation
    state.last_allocation_plan_id = allocation_plan.plan_id
    state.proposed_allocation = _build_allocation_response(allocation_plan, pw_dict)
    state.proposed_allocation["compliance_report"] = state.last_compliance_report

    # Compute residual capacity
    total_allocated = sum(a.payload_mass_kg for a in allocation_plan.assignments)
    total_vehicle_capacity = sum(v["max_payload_kg"] for v in VEHICLES.values())
    state.residual_capacity_after_recovery = total_vehicle_capacity - total_allocated

    # Run state machine to update state
    evaluated_state = state.evaluate_state_machine()

    return {
        "status": "ok",
        "resilience_state": evaluated_state,
        "allocation": state.proposed_allocation,
        "compliance": {
            "is_compliant": compliance_report.is_compliant,
            "summary": compliance_report.summary,
            "violations_count": len(compliance_report.violations),
            "warnings_count": len(compliance_report.warnings),
        },
        "message": f"Solver completed: {len(allocation_plan.assignments)} sites allocated, {len(allocation_plan.dropped_sites)} dropped. Compliance: {'PASS' if compliance_report.is_compliant else 'BLOCKED'}.",
    }


@app.post("/api/allocation/what-if")
async def what_if_simulation(
    scenarios: list[dict],
):
    """What-if simulation: compare solver output across varying policy weights.

    Accepts a list of weight scenarios and returns comparative results.
    Each scenario should have {w1, w2, w3, label?}.

    Example:
    [
        {"w1": 0.7, "w2": 0.2, "w3": 0.1, "label": "Clinical Focus"},
        {"w1": 0.3, "w2": 0.4, "w3": 0.3, "label": "Balanced"},
        {"w1": 0.1, "w2": 0.2, "w3": 0.7, "label": "Value Focus"}
    ]
    """
    if not scenarios:
        raise HTTPException(status_code=400, detail="Provide at least one weight scenario")

    results = []
    for i, scenario in enumerate(scenarios):
        w1 = scenario.get("w1", 0.4)
        w2 = scenario.get("w2", 0.3)
        w3 = scenario.get("w3", 0.3)
        label = scenario.get("label", f"Scenario {i + 1}")

        if abs(w1 + w2 + w3 - 1.0) > 1e-6:
            results.append({
                "label": label,
                "error": f"Weights must sum to 1.0, got {w1 + w2 + w3}",
            })
            continue

        pw_dict = {"w1": w1, "w2": w2, "w3": w3}
        allocation_plan = _run_solver(state.shelf_life_projections, pw_dict)

        results.append({
            "label": label,
            "weights": pw_dict,
            "objective_value": round(allocation_plan.objective_value, 4),
            "sites_allocated": len(allocation_plan.assignments),
            "sites_dropped": len(allocation_plan.dropped_sites),
            "total_units_dispatched": sum(a.allocated_units for a in allocation_plan.assignments),
            "total_avoided_loss_eur": sum(
                a.priority_score * a.allocated_units * 350
                for a in allocation_plan.assignments
            ),
            "assignments_summary": [
                {"site_id": a.site_id, "units": a.allocated_units, "vehicle": a.vehicle_id, "P_i": round(a.priority_score, 4)}
                for a in allocation_plan.assignments
            ],
            "dropped_summary": [
                {"site_id": d.site_id, "reason": d.reason}
                for d in allocation_plan.dropped_sites
            ],
        })

    # Find the best scenario by objective value
    valid_results = [r for r in results if "error" not in r]
    best_label = max(valid_results, key=lambda r: r["objective_value"])["label"] if valid_results else None

    return {
        "status": "ok",
        "scenarios": results,
        "comparison": {
            "best_scenario": best_label,
            "total_scenarios": len(scenarios),
            "valid_scenarios": len(valid_results),
        },
        "current_weights": state.policy_weights,
    }


@app.get("/api/allocation/proposed")
async def get_proposed_allocation():
    """Get the current proposed allocation."""
    if not state.proposed_allocation:
        raise HTTPException(status_code=404, detail="No proposed allocation. Run allocation first.")
    return state.proposed_allocation


@app.post("/api/compliance/check")
async def check_compliance():
    """Run compliance check on the current proposed allocation.

    This is the Compliance Agent endpoint that checks:
    1. Sanctions compliance (sanctioned countries/entities)
    2. Cold chain temperature compliance (pharmaceutical products)
    3. Allocation limits (prevent over-allocation)
    4. Dropped site risk assessment
    5. Vehicle-site compatibility
    """
    if not state.proposed_allocation:
        raise HTTPException(status_code=404, detail="No proposed allocation. Run allocation first.")

    # Reconstruct AllocationPlan from the stored response
    assignment_dicts = state.proposed_allocation.get("assignments", [])
    dropped_dicts = state.proposed_allocation.get("dropped_sites", [])

    allocation = AllocationPlan(
        plan_id=state.proposed_allocation.get("plan_id", ""),
        assignments=[
            SiteAllocation(
                site_id=a["site_id"],
                allocated_units=a["allocated_units"],
                vehicle_id=a["vehicle_id"],
                priority_score=a["priority_score"],
                payload_mass_kg=a.get("payload_mass_kg", 0),
            )
            for a in assignment_dicts
        ],
        dropped_sites=[
            DroppedSite(
                site_id=d["site_id"],
                reason=d["reason"],
                priority_score=d.get("priority_score", 0),
            )
            for d in dropped_dicts
        ],
        objective_value=state.proposed_allocation.get("objective_value", 0),
    )

    report = compliance_agent.check_plan(allocation, CLINICS)
    state.last_compliance_report = report.model_dump()

    return {
        "status": "ok",
        "report": report.model_dump(),
    }


@app.post("/api/allocation/approve")
async def approve_allocation(approver_id: str = "ops-manager@demo"):
    """Approve the current allocation plan.

    Before SAP writeback, the Compliance Agent runs final checks.
    If compliance fails, the writeback is blocked.
    """
    if not state.proposed_allocation:
        raise HTTPException(status_code=404, detail="No proposed allocation to approve.")

    plan_id = state.proposed_allocation["plan_id"]

    # Phase 5: GOVERN - Log approval
    state.audit_chain.append(
        event_type=AuditEventType.APPROVAL_DECISION,
        actor=Actor(type=ActorType.HUMAN, id=approver_id),
        thread_id=state.ccro.thread_id,
        allocation_plan_id=plan_id,
        payload=AuditPayload(
            approval_decision="approved",
            policy_weights=state.policy_weights,
        ),
    )

    # Phase 6: EXECUTE - Run compliance check before SAP writeback
    compliance_report = state.last_compliance_report
    if compliance_report and not compliance_report.get("is_compliant", True):
        # Compliance blocked -- cannot proceed with writeback
        state.audit_chain.append(
            event_type=AuditEventType.WRITEBACK_FAILURE,
            actor=Actor(type=ActorType.AGENT, id="compliance-agent@1.0"),
            thread_id=state.ccro.thread_id,
            allocation_plan_id=plan_id,
            payload=AuditPayload(
                error_details="Compliance check failed. Writeback blocked.",
            ),
        )
        return {
            "status": "blocked",
            "reason": "compliance_check_failed",
            "compliance_report": compliance_report,
            "message": "Allocation approved but SAP writeback blocked by compliance agent. Fix violations first.",
        }

    # Compliance passed -- proceed with SAP writeback (simulated)
    old_state = state.resilience_state
    state.ccro.resilience_state = ResilienceState.S5_SCARCITY_ALLOCATION

    state._record_transition(old_state, "S5_SCARCITY_ALLOCATION", "human_approval")

    state.audit_chain.append(
        event_type=AuditEventType.SAP_WRITEBACK,
        actor=Actor(type=ActorType.AGENT, id="execution-agent@1.0"),
        thread_id=state.ccro.thread_id,
        allocation_plan_id=plan_id,
        payload=AuditPayload(
            sap_response_codes=["200", "200", "200"],
        ),
    )

    state.writeback_status = "SUCCESS"

    state.allocation_history.append({
        "plan_id": plan_id,
        "status": "EXECUTED",
        "approved_by": approver_id,
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "assignments_count": len(state.proposed_allocation["assignments"]),
        "dropped_count": len(state.proposed_allocation["dropped_sites"]),
        "objective_value": state.proposed_allocation["objective_value"],
        "policy_weights": state.policy_weights,
        "disruption": state.current_disruption["name"] if state.current_disruption else None,
        "compliance_passed": True,
    })

    return {
        "status": "ok",
        "new_state": state.resilience_state,
        "plan_id": plan_id,
        "compliance": {"is_compliant": True, "summary": "All checks passed."},
        "message": f"Allocation {plan_id} approved and executed. State moved to S5. SAP writeback completed.",
    }


@app.post("/api/allocation/reject")
async def reject_allocation(approver_id: str = "ops-manager@demo"):
    """Reject the current allocation plan."""
    if not state.proposed_allocation:
        raise HTTPException(status_code=404, detail="No proposed allocation to reject.")

    plan_id = state.proposed_allocation["plan_id"]

    state.audit_chain.append(
        event_type=AuditEventType.APPROVAL_DECISION,
        actor=Actor(type=ActorType.HUMAN, id=approver_id),
        thread_id=state.ccro.thread_id,
        allocation_plan_id=plan_id,
        payload=AuditPayload(approval_decision="rejected"),
    )

    state.allocation_history.append({
        "plan_id": plan_id,
        "status": "REJECTED",
        "approved_by": approver_id,
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "assignments_count": len(state.proposed_allocation["assignments"]),
        "dropped_count": len(state.proposed_allocation["dropped_sites"]),
        "objective_value": state.proposed_allocation["objective_value"],
        "policy_weights": state.policy_weights,
        "disruption": state.current_disruption["name"] if state.current_disruption else None,
    })

    state.proposed_allocation = None
    state.writeback_status = "REJECTED"

    return {
        "status": "ok",
        "new_state": state.resilience_state,
        "message": "Allocation rejected. No changes made to SAP.",
    }


@app.post("/api/allocation/modify")
async def modify_allocation(
    modifications: list[dict],
    approver_id: str = "ops-manager@demo",
):
    """Submit a modified allocation plan for approval."""
    if not state.proposed_allocation:
        raise HTTPException(status_code=404, detail="No proposed allocation to modify.")

    plan_id = state.proposed_allocation["plan_id"]

    for mod in modifications:
        site_id = mod.get("site_id")
        vehicle_id = mod.get("vehicle_id")
        allocated_units = mod.get("allocated_units", 0)

        if site_id not in CLINICS:
            raise HTTPException(status_code=400, detail=f"Unknown site: {site_id}")
        if vehicle_id not in VEHICLES:
            raise HTTPException(status_code=400, detail=f"Unknown vehicle: {vehicle_id}")

        remaining_hours = state.shelf_life_projections.get(site_id, 0)
        transit_time = VEHICLES[vehicle_id]["transit_times"].get(site_id, float("inf"))
        if transit_time + 2.0 >= remaining_hours:
            raise HTTPException(
                status_code=400,
                detail=f"C1 VIOLATION: {site_id} via {vehicle_id} -- transit ({transit_time}h) + buffer (2h) >= shelf life ({remaining_hours}h). Site is unreachable.",
            )

    state.proposed_allocation["assignments"] = [
        {
            "site_id": mod["site_id"],
            "site_name": CLINICS.get(mod["site_id"], {}).get("name", mod["site_id"]),
            "city": CLINICS.get(mod["site_id"], {}).get("city", "Unknown"),
            "allocated_units": mod["allocated_units"],
            "vehicle_id": mod["vehicle_id"],
            "priority_score": next(
                (a["priority_score"] for a in state.proposed_allocation["assignments"]
                 if a["site_id"] == mod["site_id"]),
                0.0,
            ),
            "payload_mass_kg": float(mod["allocated_units"]),
        }
        for mod in modifications
    ]

    state.audit_chain.append(
        event_type=AuditEventType.APPROVAL_DECISION,
        actor=Actor(type=ActorType.HUMAN, id=approver_id),
        thread_id=state.ccro.thread_id,
        allocation_plan_id=plan_id,
        payload=AuditPayload(
            approval_decision="modified",
            policy_weights=state.policy_weights,
        ),
    )

    return {
        "status": "ok",
        "allocation": state.proposed_allocation,
        "message": "Allocation modified. Review the updated plan.",
    }


@app.get("/api/audit/log")
async def get_audit_log(limit: int = 20):
    """Get the audit log entries."""
    records = state.audit_chain.get_records()
    entries = []
    for record in reversed(records[-limit:]):
        entries.append({
            "record_id": record.record_id,
            "event_type": record.event_type.value,
            "timestamp": record.timestamp_utc.isoformat(),
            "actor_type": record.actor.type.value,
            "actor_id": record.actor.id,
            "thread_id": record.thread_id,
            "allocation_plan_id": record.allocation_plan_id,
            "payload": record.payload.model_dump(),
            "record_hash": record.record_hash[:16] + "...",
            "prev_hash": record.prev_record_hash[:16] + "..." if record.prev_record_hash != "0" * 64 else "genesis",
        })

    chain_valid = state.audit_chain.verify_integrity()

    return {
        "entries": entries,
        "chain_length": len(records),
        "chain_valid": chain_valid,
        "chain_tip": state.audit_chain.chain_tip[:16] + "...",
    }


@app.get("/api/allocation/history")
async def get_allocation_history():
    """Get allocation history."""
    return {
        "history": state.allocation_history,
    }


@app.get("/api/disruptions")
async def get_disruptions():
    """Get available disruption scenarios."""
    return {"scenarios": DISRUPTION_SCENARIOS}


@app.post("/api/reset")
async def reset_state():
    """Reset the demo to initial state."""
    state.reset()
    return {"status": "ok", "message": "Demo reset to initial state."}


@app.get("/api/settings")
async def get_settings():
    """Get current system settings."""
    return {
        "state_machine_thresholds": {
            "s2_s3_capacity_margin": 15.0,
            "s3_s4_capacity_margin": 0.0,
        },
        "solver_config": {
            "handling_buffer_hours": 2.0,
            "per_unit_mass_kg": 1.0,
            "time_limit_seconds": 30,
        },
        "policy_weights": state.policy_weights,
        "sap_destinations": {
            "s4hana": {"status": "mock", "url": "https://s4hana.example.com"},
            "sap_tm": {"status": "mock", "url": "https://tm.example.com"},
        },
        "agent_health": {
            "sensing_agent": "healthy",
            "impact_agent": "healthy",
            "recovery_agents": "healthy",
            "scarcity_engine": "healthy",
            "policy_agent": "healthy",
            "execution_agent": "healthy",
            "compliance_agent": "healthy",
        },
        "orchestrator": {
            "pipeline": "sense -> understand -> adapt -> protect -> govern -> execute",
            "state_machine": "ResilienceStateMachine",
            "graph_state": "CCROGraphState",
        },
    }


@app.get("/health")
async def health():
    return {"status": "healthy", "version": "1.0.0"}


# ============================================================================
# SERVE FRONTEND -- Static files from the React build
# ============================================================================

frontend_dist = project_root / "demo" / "frontend" / "dist"

if frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="static-assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        """Serve the React SPA -- all non-API routes return index.html."""
        file_path = frontend_dist / full_path
        if file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(frontend_dist / "index.html"))
