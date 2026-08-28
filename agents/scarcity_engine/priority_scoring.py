"""Priority Scoring — Computes P_i for each clinic/site.

P_i = w1 * SR_i + w2 * OS_i + w3 * VPI_i

Where:
  SR_i  = urgency_score(site_i)   — clinical urgency / remaining shelf life
  OS_i  = operational_score(site_i) — operational simplicity
  VPI_i = value_score(site_i)      — value preservation (demand volume)
"""

from __future__ import annotations

import structlog

from schemas import PolicyWeights, ShelfLifeProjection

logger = structlog.get_logger(__name__)


def compute_priority_scores(
    shelf_life_projections: dict[str, ShelfLifeProjection],
    policy_weights: PolicyWeights,
) -> dict[str, float]:
    """Compute P_i = w1*SR_i + w2*OS_i + w3*VPI_i for each site.

    Returns:
        Dict mapping site_id to P_i score.
    """
    if not shelf_life_projections:
        return {}

    max_demand = max(
        (p.demand_units for p in shelf_life_projections.values()), default=1
    ) or 1

    scores: dict[str, float] = {}

    for site_id, proj in shelf_life_projections.items():
        # SR_i: Clinical Urgency — shorter remaining shelf life = higher urgency
        max_shelf_life = max(
            (p.remaining_shelf_life_hours for p in shelf_life_projections.values()),
            default=1,
        ) or 1
        sr_i = 1.0 - (proj.remaining_shelf_life_hours / max_shelf_life)

        # OS_i: Operational Simplicity — placeholder (would use actual route data)
        os_i = 0.5  # neutral default

        # VPI_i: Value Preservation — higher demand = higher priority
        vpi_i = proj.demand_units / max_demand

        # P_i = w1*SR_i + w2*OS_i + w3*VPI_i
        p_i = (
            policy_weights.w1 * sr_i
            + policy_weights.w2 * os_i
            + policy_weights.w3 * vpi_i
        )

        scores[site_id] = round(p_i, 6)

    logger.info(
        "scarcity.priority_computed",
        n_sites=len(scores),
        avg_priority=sum(scores.values()) / max(len(scores), 1),
    )

    return scores
