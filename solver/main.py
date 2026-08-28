"""Solver Microservice Entrypoint.

Stateless, side-effect-free compute service. Never writes to SAP.
Deployed as independently scalable container on SAP BTP Kyma runtime.
"""

from __future__ import annotations

import hashlib
import json
import structlog
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from schemas import AllocationPlan, PolicyWeights, ShelfLifeProjection
from solver.engines.ortools_milp import OrToolsSolver, SolverInput
from solver.engines.scipy_relaxation import SciPyRelaxation
from solver.models.constraint_builder import ConstraintBuilder, VehicleConstraintInfo
from solver.models.objective_builder import ObjectiveBuilder

logger = structlog.get_logger(__name__)
app = FastAPI(title="CCRO Solver Service", version="0.1.0")


class SolverRequest(BaseModel):
    """Request to solve a scarcity allocation problem."""

    shelf_life_projections: dict[str, ShelfLifeProjection]
    vehicle_capacity_kg: dict[str, float]
    vehicle_transit_times: dict[str, dict[str, float]]  # vid -> {site_id: hours}
    policy_weights: PolicyWeights
    handling_buffer_hours: float = 2.0
    per_unit_mass_kg: float = 1.0


class SolverResponse(BaseModel):
    """Solver response with allocation plan."""

    allocation_plan: AllocationPlan
    relaxation_feasible: bool
    relaxation_message: str


@app.post("/solve", response_model=SolverResponse)
async def solve_allocation(request: SolverRequest) -> SolverResponse:
    """Run the deterministic solver pipeline.

    Pipeline:
    1. SciPy LP relaxation (rapid feasibility check)
    2. Constraint builder (pre-filter infeasible variables)
    3. Objective builder (compute P_i scores)
    4. OR-Tools MILP (final allocation)
    """
    logger.info(
        "solver.invocation",
        n_sites=len(request.shelf_life_projections),
        n_vehicles=len(request.vehicle_capacity_kg),
    )

    # Step 1: Build vehicle constraint info
    vehicles = []
    for vid, cap in request.vehicle_capacity_kg.items():
        transit = request.vehicle_transit_times.get(vid, {})
        vehicles.append(
            VehicleConstraintInfo(
                vehicle_id=vid, max_payload_kg=cap, transit_times=transit
            )
        )

    # Step 2: Constraint builder — pre-filter infeasible pairs
    constraint_builder = ConstraintBuilder(
        handling_buffer_hours=request.handling_buffer_hours
    )
    constraint_result = constraint_builder.build(
        shelf_life_projections=request.shelf_life_projections,
        vehicles=vehicles,
        policy_weights=request.policy_weights,
    )

    # Step 3: Objective builder — compute priority scores
    obj_builder = ObjectiveBuilder()
    priority_scores = obj_builder.compute_priority_scores(
        shelf_life_projections=request.shelf_life_projections,
        policy_weights=request.policy_weights,
    )

    # Step 4: SciPy relaxation pre-check
    relaxation = SciPyRelaxation()
    relax_result = relaxation.check_feasibility(
        feasible_variables=constraint_result.feasible_variables,
        priority_scores=priority_scores,
        vehicle_capacities=constraint_result.vehicle_capacity_map,
        per_unit_mass=request.per_unit_mass_kg,
    )

    if not relax_result.is_feasible:
        logger.warning(
            "solver.infeasible_relaxation",
            message=relax_result.message,
        )
        return SolverResponse(
            allocation_plan=AllocationPlan(
                dropped_sites=constraint_result.dropped_sites,
            ),
            relaxation_feasible=False,
            relaxation_message=relax_result.message,
        )

    # Step 5: OR-Tools MILP solve
    solver_input = SolverInput(
        priority_scores=priority_scores,
        constraint_result=constraint_result,
        vehicle_capacities=constraint_result.vehicle_capacity_map,
        per_unit_mass=request.per_unit_mass_kg,
    )

    milp_solver = OrToolsSolver()
    allocation_plan = milp_solver.solve(solver_input, obj_builder)

    logger.info(
        "solver.completed",
        assignments=len(allocation_plan.assignments),
        dropped=len(allocation_plan.dropped_sites),
        objective=allocation_plan.objective_value,
    )

    return SolverResponse(
        allocation_plan=allocation_plan,
        relaxation_feasible=True,
        relaxation_message="Feasible solution found",
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
