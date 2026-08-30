"""CCRO Demo Backend — Single FastAPI app with mock data, solver, state machine, audit log.

Start: uvicorn demo.backend.main:app --reload --port 8000

This is a self-contained demo backend for SAP HackFest 2026.
It uses the real solver logic and state machine from the existing codebase,
but operates entirely on realistic mock data (no real SAP required).
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
from solver.engines.ortools_milp import OrToolsSolver, SolverInput
from solver.models.constraint_builder import ConstraintBuilder, VehicleConstraintInfo
from solver.models.objective_builder import ObjectiveBuilder

app = FastAPI(title="CCRO Demo Backend", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# MOCK DATA — Realistic cold-chain pharmaceutical scenario
# ============================================================================

CLINICS = {
    "CLN-001": {
        "id": "CLN-001",
        "name": "St. Mary's General Hospital",
        "city": "Munich",
        "demand_units": 120,
        "criticality": "high",
        "vulnerable_population_index": 0.92,
        "batch_ids": ["BAT-2026-A1", "BAT-2026-A2"],
    },
    "CLN-002": {
        "id": "CLN-002",
        "name": "Charité Campus Virchow",
        "city": "Berlin",
        "demand_units": 200,
        "criticality": "critical",
        "vulnerable_population_index": 0.97,
        "batch_ids": ["BAT-2026-B1"],
    },
    "CLN-003": {
        "id": "CLN-003",
        "name": "Universitätsklinikum Köln",
        "city": "Cologne",
        "demand_units": 85,
        "criticality": "medium",
        "vulnerable_population_index": 0.71,
        "batch_ids": ["BAT-2026-C1", "BAT-2026-C2"],
    },
    "CLN-004": {
        "id": "CLN-004",
        "name": "Hannover Medical School",
        "city": "Hannover",
        "demand_units": 150,
        "criticality": "high",
        "vulnerable_population_index": 0.85,
        "batch_ids": ["BAT-2026-D1"],
    },
    "CLN-005": {
        "id": "CLN-005",
        "name": "University Hospital Zurich",
        "city": "Zurich",
        "demand_units": 95,
        "criticality": "high",
        "vulnerable_population_index": 0.88,
        "batch_ids": ["BAT-2026-E1"],
    },
    "CLN-006": {
        "id": "CLN-006",
        "name": "Erasmus MC Rotterdam",
        "city": "Rotterdam",
        "demand_units": 65,
        "criticality": "medium",
        "vulnerable_population_index": 0.62,
        "batch_ids": ["BAT-2026-F1"],
    },
    "CLN-007": {
        "id": "CLN-007",
        "name": "Karolinska University Hospital",
        "city": "Stockholm",
        "demand_units": 180,
        "criticality": "critical",
        "vulnerable_population_index": 0.94,
        "batch_ids": ["BAT-2026-G1", "BAT-2026-G2"],
    },
    "CLN-008": {
        "id": "CLN-008",
        "name": "Hôpital Pitié-Salpêtrière",
        "city": "Paris",
        "demand_units": 110,
        "criticality": "high",
        "vulnerable_population_index": 0.81,
        "batch_ids": ["BAT-2026-H1"],
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

# Shelf-life projections (in hours remaining) — these create interesting solver behavior
# Some sites are close to expiry (high urgency), others have plenty of time
BATCH_SHELF_LIFE = {
    "CLN-001": 18.0,   # 18 hours left — urgent
    "CLN-002": 8.0,    # 8 hours left — critical
    "CLN-003": 36.0,   # 36 hours left — moderate
    "CLN-004": 14.0,   # 14 hours left — urgent
    "CLN-005": 24.0,   # 24 hours left — moderate
    "CLN-006": 48.0,   # 48 hours left — plenty of time
    "CLN-007": 6.0,    # 6 hours left — extreme urgency
    "CLN-008": 3.0,    # 3 hours left — will be dropped (unreachable for most vehicles)
}

# Default policy weights (balanced)
DEFAULT_POLICY_WEIGHTS = {"w1": 0.4, "w2": 0.3, "w3": 0.3}

# Disruption scenarios
DISRUPTION_SCENARIOS = [
    {
        "id": "D-001",
        "name": "Cold Storage Failure — Munich Hub",
        "type": "thermal_drift",
        "severity": "critical",
        "affected_sites": ["CLN-001", "CLN-004"],
        "description": "Main cold storage compressor failed at Munich distribution hub. Temperature rose 4.2°C above threshold. All batches at CLN-001 and CLN-004 affected — shelf life reduced by 60%.",
        "temperature_delta": 4.2,
        "shelf_life_reduction_pct": 0.60,
    },
    {
        "id": "D-002",
        "name": "Port Congestion — Rotterdam",
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
# IN-MEMORY STATE
# ============================================================================

class DemoState:
    def __init__(self):
        self.reset()

    def reset(self):
        self.resilience_state: str = "S1_STABLE"
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
        self.thread_id: str = f"EP-{uuid.uuid4().hex[:8].upper()}"
        self.tick_count: int = 0
        self.residual_capacity_after_recovery: float = 0.0
        self.recovery_options: list[dict] = []
        self.writeback_status: str = "PENDING"

    def compute_totals(self):
        self.total_demand = sum(
            CLINICS[cid]["demand_units"] for cid in self.shelf_life_projections
        )
        # Total available capacity = sum of vehicle capacities
        self.total_available_capacity = sum(
            v["max_payload_kg"] for v in VEHICLES.values()
        )
        if self.total_demand > 0:
            self.capacity_margin = (self.total_available_capacity - self.total_demand) / self.total_demand
        else:
            self.capacity_margin = 1.0

    def get_capacity_margin_for_gauge(self) -> float:
        """Returns capacity margin as a percentage for display."""
        self.compute_totals()
        return round(self.capacity_margin * 100, 1)

    def get_site_details(self) -> list[dict]:
        """Return detailed site info for display."""
        sites = []
        for clinic_id in sorted(CLINICS.keys()):
            clinic = CLINICS[clinic_id]
            remaining = self.shelf_life_projections.get(clinic_id, 0)
            original = self.original_shelf_life.get(clinic_id, remaining)
            sites.append({
                "id": clinic_id,
                "name": clinic["name"],
                "city": clinic["city"],
                "demand_units": clinic["demand_units"],
                "criticality": clinic["criticality"],
                "vpi": clinic["vulnerable_population_index"],
                "remaining_shelf_life_hours": remaining,
                "original_shelf_life_hours": original,
                "batch_ids": clinic["batch_ids"],
                "is_threatened": remaining < 24,
            })
        return sites


state = DemoState()


# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint — serves React SPA if available, else API landing page."""
    index_file = frontend_dist / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {
        "service": "CCRO Demo Backend",
        "version": "1.0.0",
        "endpoints": {
            "health": "/health",
            "state": "/api/state",
            "disruptions": "/api/disruptions",
            "trigger": "POST /api/disruption/trigger?disruption_id=D-001",
            "run_allocation": "POST /api/allocation/run?w1=0.4&w2=0.3&w3=0.3",
            "approve": "POST /api/allocation/approve",
            "audit_log": "/api/audit/log",
            "settings": "/api/settings",
            "docs": "/docs",
        },
    }


@app.get("/api/state")
async def get_state():
    """Get the current system state."""
    state.compute_totals()
    return {
        "resilience_state": state.resilience_state,
        "capacity_margin": state.get_capacity_margin_for_gauge(),
        "total_demand": state.total_demand,
        "total_available_capacity": state.total_available_capacity,
        "thread_id": state.thread_id,
        "tick_count": state.tick_count,
        "current_disruption": state.current_disruption,
        "has_proposed_allocation": state.proposed_allocation is not None,
        "sites": state.get_site_details(),
        "vehicles": [
            {"id": v["id"], "type": v["type"], "max_payload_kg": v["max_payload_kg"]}
            for v in VEHICLES.values()
        ],
    }


@app.post("/api/disruption/trigger")
async def trigger_disruption(disruption_id: str = "D-001"):
    """Trigger a disruption event and move state to S4."""
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

    # Record in telemetry buffer
    state.telemetry_buffer.append({
        "event_id": uuid.uuid4().hex,
        "disruption_type": scenario["type"],
        "severity": scenario["severity"],
        "affected_sites": scenario["affected_sites"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    # Move to S2 (absorbing) then S3 (recovery constrained) then S4 (recovery insufficient)
    # For demo purposes, we go straight to S4 since we have no real recovery agents
    state.resilience_state = "S4_RECOVERY_INSUFFICIENT"

    # Compute totals
    state.compute_totals()

    # Log state transition to audit chain
    state.audit_chain.append(
        event_type=AuditEventType.STATE_TRANSITION,
        actor=Actor(type=ActorType.SYSTEM, id="orchestrator@1.0"),
        thread_id=state.thread_id,
        payload=AuditPayload(
            previous_state="S1_STABLE",
            new_state="S4_RECOVERY_INSUFFICIENT",
            allocation_plan_id=None,
        ),
    )

    return {
        "status": "ok",
        "new_state": state.resilience_state,
        "disruption": state.current_disruption,
        "capacity_margin": state.get_capacity_margin_for_gauge(),
        "message": f"Disruption '{scenario['name']}' triggered. State moved to S4.",
    }


@app.post("/api/allocation/run")
async def run_allocation(
    w1: float = 0.4,
    w2: float = 0.3,
    w3: float = 0.3,
):
    """Run the scarcity allocation solver with current state."""
    # Validate weights
    if abs(w1 + w2 + w3 - 1.0) > 1e-6:
        raise HTTPException(status_code=400, detail=f"Weights must sum to 1.0, got {w1 + w2 + w3}")

    policy_weights = PolicyWeights(w1=w1, w2=w2, w3=w3)
    state.policy_weights = {"w1": w1, "w2": w2, "w3": w3}

    # Build shelf life projections
    shelf_life_projections = {
        site_id: ShelfLifeProjection(
            site_id=site_id,
            remaining_shelf_life_hours=hours,
            demand_units=CLINICS[site_id]["demand_units"],
            batch_ids=CLINICS[site_id]["batch_ids"],
        )
        for site_id, hours in state.shelf_life_projections.items()
        if hours > 0
    }

    # Build vehicle constraint info
    vehicles = [
        VehicleConstraintInfo(
            vehicle_id=v["id"],
            max_payload_kg=v["max_payload_kg"],
            transit_times=v["transit_times"],
        )
        for v in VEHICLES.values()
    ]

    vehicle_capacities = {v["id"]: v["max_payload_kg"] for v in VEHICLES.values()}

    # Step 1: Constraint builder
    constraint_builder = ConstraintBuilder(handling_buffer_hours=2.0)
    constraint_result = constraint_builder.build(
        shelf_life_projections=shelf_life_projections,
        vehicles=vehicles,
        policy_weights=policy_weights,
    )

    # Step 2: Objective builder
    obj_builder = ObjectiveBuilder()
    priority_scores = obj_builder.compute_priority_scores(
        shelf_life_projections=shelf_life_projections,
        policy_weights=policy_weights,
    )

    # Step 3: SciPy feasibility check (skip for demo, go straight to solver)
    # Step 4: OR-Tools MILP
    solver_input = SolverInput(
        priority_scores=priority_scores,
        constraint_result=constraint_result,
        vehicle_capacities=vehicle_capacities,
        per_unit_mass=1.0,
    )

    solver = OrToolsSolver()
    allocation_plan = solver.solve(solver_input, obj_builder)

    # Log solver run to audit chain
    state.audit_chain.append(
        event_type=AuditEventType.SOLVER_RUN,
        actor=Actor(type=ActorType.AGENT, id="scarcity-engine@1.0"),
        thread_id=state.thread_id,
        allocation_plan_id=allocation_plan.plan_id,
        payload=AuditPayload(
            solver_version=allocation_plan.solver_version,
            input_snapshot_hash=allocation_plan.input_snapshot_hash,
            policy_weights=state.policy_weights,
        ),
    )

    # Store the proposed allocation
    state.last_allocation_plan_id = allocation_plan.plan_id
    state.proposed_allocation = {
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
        "policy_weights": state.policy_weights,
        # Build the "do nothing" comparison
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
        # Build the "CCRO allocation" comparison
        "ccro_allocation": {
            "total_avoided_loss_eur": sum(
                a.priority_score * a.allocated_units * 350
                for a in allocation_plan.assignments
            ),
            "sites_covered": len(allocation_plan.assignments),
            "total_units_dispatched": sum(a.allocated_units for a in allocation_plan.assignments),
        },
    }

    # Compute residual capacity
    total_allocated = sum(a.payload_mass_kg for a in allocation_plan.assignments)
    total_vehicle_capacity = sum(v["max_payload_kg"] for v in VEHICLES.values())
    state.residual_capacity_after_recovery = total_vehicle_capacity - total_allocated

    return {
        "status": "ok",
        "allocation": state.proposed_allocation,
        "message": f"Solver completed. {len(allocation_plan.assignments)} sites allocated, {len(allocation_plan.dropped_sites)} dropped.",
    }


@app.get("/api/allocation/proposed")
async def get_proposed_allocation():
    """Get the current proposed allocation."""
    if not state.proposed_allocation:
        raise HTTPException(status_code=404, detail="No proposed allocation. Run allocation first.")
    return state.proposed_allocation


@app.post("/api/allocation/approve")
async def approve_allocation(approver_id: str = "ops-manager@demo"):
    """Approve the current allocation plan."""
    if not state.proposed_allocation:
        raise HTTPException(status_code=404, detail="No proposed allocation to approve.")

    plan_id = state.proposed_allocation["plan_id"]

    # Log approval to audit chain
    state.audit_chain.append(
        event_type=AuditEventType.APPROVAL_DECISION,
        actor=Actor(type=ActorType.HUMAN, id=approver_id),
        thread_id=state.thread_id,
        allocation_plan_id=plan_id,
        payload=AuditPayload(
            approval_decision="approved",
            policy_weights=state.policy_weights,
        ),
    )

    # Move to S5
    old_state = state.resilience_state
    state.resilience_state = "S5_SCARCITY_ALLOCATION"

    # Log state transition
    state.audit_chain.append(
        event_type=AuditEventType.STATE_TRANSITION,
        actor=Actor(type=ActorType.SYSTEM, id="orchestrator@1.0"),
        thread_id=state.thread_id,
        allocation_plan_id=plan_id,
        payload=AuditPayload(
            previous_state=old_state,
            new_state="S5_SCARCITY_ALLOCATION",
            allocation_plan_id=plan_id,
        ),
    )

    # Log SAP writeback (simulated)
    state.audit_chain.append(
        event_type=AuditEventType.SAP_WRITEBACK,
        actor=Actor(type=ActorType.AGENT, id="execution-agent@1.0"),
        thread_id=state.thread_id,
        allocation_plan_id=plan_id,
        payload=AuditPayload(
            sap_response_codes=["200", "200", "200"],
        ),
    )

    state.writeback_status = "SUCCESS"

    # Add to history
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
    })

    return {
        "status": "ok",
        "new_state": state.resilience_state,
        "plan_id": plan_id,
        "message": f"Allocation {plan_id} approved. State moved to S5. SAP writeback initiated.",
    }


@app.post("/api/allocation/reject")
async def reject_allocation(approver_id: str = "ops-manager@demo"):
    """Reject the current allocation plan."""
    if not state.proposed_allocation:
        raise HTTPException(status_code=404, detail="No proposed allocation to reject.")

    plan_id = state.proposed_allocation["plan_id"]

    # Log rejection
    state.audit_chain.append(
        event_type=AuditEventType.APPROVAL_DECISION,
        actor=Actor(type=ActorType.HUMAN, id=approver_id),
        thread_id=state.thread_id,
        allocation_plan_id=plan_id,
        payload=AuditPayload(approval_decision="rejected"),
    )

    # Add to history
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

    # Clear proposed allocation
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

    # Validate modifications against hard constraints
    for mod in modifications:
        site_id = mod.get("site_id")
        vehicle_id = mod.get("vehicle_id")
        allocated_units = mod.get("allocated_units", 0)

        if site_id not in CLINICS:
            raise HTTPException(status_code=400, detail=f"Unknown site: {site_id}")
        if vehicle_id not in VEHICLES:
            raise HTTPException(status_code=400, detail=f"Unknown vehicle: {vehicle_id}")

        # C1: Check thermal constraint
        remaining_hours = state.shelf_life_projections.get(site_id, 0)
        transit_time = VEHICLES[vehicle_id]["transit_times"].get(site_id, float("inf"))
        if transit_time + 2.0 >= remaining_hours:
            raise HTTPException(
                status_code=400,
                detail=f"C1 VIOLATION: {site_id} via {vehicle_id} — transit ({transit_time}h) + buffer (2h) >= shelf life ({remaining_hours}h). Site is unreachable.",
            )

    # Update the proposed allocation
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

    # Log modification
    state.audit_chain.append(
        event_type=AuditEventType.APPROVAL_DECISION,
        actor=Actor(type=ActorType.HUMAN, id=approver_id),
        thread_id=state.thread_id,
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
    # Return most recent first
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
        },
    }


@app.get("/health")
async def health():
    return {"status": "healthy", "version": "1.0.0"}


# ============================================================================
# SERVE FRONTEND — Static files from the React build
# ============================================================================

frontend_dist = project_root / "demo" / "frontend" / "dist"

if frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="static-assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        """Serve the React SPA — all non-API routes return index.html."""
        file_path = frontend_dist / full_path
        if file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(frontend_dist / "index.html"))
