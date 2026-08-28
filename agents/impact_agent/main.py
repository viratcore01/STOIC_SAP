"""Impact & Scenario Agent Service — Phase 2 UNDERSTAND.

Reads batch expiry, inventory, and demand data from SAP S/4HANA and EWM,
computes shelf-life projections per site, and returns them to the Orchestrator.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import structlog
from fastapi import FastAPI

from agents.impact_agent.shelf_life_model.thermal_decay import ShelfLifeProjection
from schemas import ShelfLifeProjection as ShelfLifeProjectionSchema

logger = structlog.get_logger(__name__)
app = FastAPI(title="CCRO Impact Agent", version="0.1.0")

shelf_life_model = ShelfLifeProjection()


@app.post("/assess")
async def assess_impact(
    site_projections: dict[str, dict],
) -> dict[str, ShelfLifeProjectionSchema]:
    """Assess impact for a set of sites.

    Input: site_id -> {remaining_shelf_life_hours, demand_units, batch_ids}
    Output: site_id -> ShelfLifeProjection
    """
    projections: dict[str, ShelfLifeProjectionSchema] = {}

    for site_id, data in site_projections.items():
        remaining_hours = float(data.get("remaining_shelf_life_hours", 0))
        demand = int(data.get("demand_units", 0))
        batch_ids = data.get("batch_ids", [])

        projections[site_id] = ShelfLifeProjectionSchema(
            site_id=site_id,
            remaining_shelf_life_hours=remaining_hours,
            demand_units=demand,
            batch_ids=batch_ids,
        )

    logger.info(
        "impact.assessed",
        n_sites=len(projections),
        avg_remaining_hours=(
            sum(p.remaining_shelf_life_hours for p in projections.values())
            / max(len(projections), 1)
        ),
    )

    return projections


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8003)
