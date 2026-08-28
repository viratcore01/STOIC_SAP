"""Scarcity Allocation Engine Service — Phase 4 PROTECT.

Orchestrates the solver + policy scoring pipeline:
1. Request PolicyWeights from Policy Agent
2. Compute P_i priority scores
3. Submit constrained allocation problem to Solver
4. Return proposed AllocationPlan to Orchestrator
"""

from __future__ import annotations

import structlog
from fastapi import FastAPI

from agents.scarcity_engine.priority_scoring import compute_priority_scores
from schemas import AllocationPlan, PolicyWeights, ShelfLifeProjection

logger = structlog.get_logger(__name__)
app = FastAPI(title="CCRO Scarcity Allocation Engine", version="0.1.0")


@app.post("/allocate", response_model=AllocationPlan)
async def run_scarcity_allocation(
    shelf_life_projections: dict[str, ShelfLifeProjection],
    policy_weights: PolicyWeights,
    vehicle_capacity_kg: dict[str, float],
    vehicle_transit_times: dict[str, dict[str, float]],
    handling_buffer_hours: float = 2.0,
    per_unit_mass_kg: float = 1.0,
) -> AllocationPlan:
    """Run the full scarcity allocation pipeline.

    1. Compute P_i scores from policy weights + projections
    2. Call solver service for constrained optimization
    3. Return allocation plan for governance review
    """
    logger.info(
        "scarcity.allocation_started",
        n_sites=len(shelf_life_projections),
        n_vehicles=len(vehicle_capacity_kg),
    )

    # Step 1: Compute priority scores
    priority_scores = compute_priority_scores(shelf_life_projections, policy_weights)

    # Step 2: Call solver service
    import httpx

    solver_request = {
        "shelf_life_projections": {
            k: v.model_dump() for k, v in shelf_life_projections.items()
        },
        "vehicle_capacity_kg": vehicle_capacity_kg,
        "vehicle_transit_times": vehicle_transit_times,
        "policy_weights": policy_weights.model_dump(),
        "handling_buffer_hours": handling_buffer_hours,
        "per_unit_mass_kg": per_unit_mass_kg,
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "http://localhost:8001/solve",
                json=solver_request,
                timeout=60.0,
            )
            response.raise_for_status()
            result = response.json()
            allocation_plan = AllocationPlan(**result["allocation_plan"])
    except Exception as e:
        logger.error("scarcity.solver_error", error=str(e))
        allocation_plan = AllocationPlan()

    logger.info(
        "scarcity.allocation_completed",
        assignments=len(allocation_plan.assignments),
        dropped=len(allocation_plan.dropped_sites),
        objective=allocation_plan.objective_value,
    )

    return allocation_plan


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8004)
