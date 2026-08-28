"""Objective Function Builder for the Scarcity Allocation MILP.

Maximizes Σ_i (P_i × Σ_v x_{i,v}) — total priority-weighted fulfillment,
NOT raw units or cost. This is the explicit departure from standard
cost-minimization routing.

P_i is computed as:
  P_i = w1 * SR_i + w2 * OS_i + w3 * VPI_i

where:
  SR_i  = urgency_score(site_i)   — clinical urgency / remaining shelf life
  OS_i  = operational_score(site_i) — operational simplicity (proximity, route density)
  VPI_i = value_score(site_i)      — value preservation (demand volume, criticality)

All sub-scores are normalized to [0, 1].
"""

from __future__ import annotations

from dataclasses import dataclass

from schemas import PolicyWeights, ShelfLifeProjection


@dataclass
class PriorityScores:
    """Computed priority scores for all sites."""

    scores: dict[str, float]  # site_id -> P_i
    sr: dict[str, float]  # site_id -> SR_i
    os: dict[str, float]  # site_id -> OS_i
    vpi: dict[str, float]  # site_id -> VPI_i


class ObjectiveBuilder:
    """Builds priority scores and the objective function for the solver."""

    def compute_priority_scores(
        self,
        shelf_life_projections: dict[str, ShelfLifeProjection],
        policy_weights: PolicyWeights,
    ) -> PriorityScores:
        """Compute P_i = w1*SR_i + w2*OS_i + w3*VPI_i for each site."""
        sr: dict[str, float] = {}
        os_scores: dict[str, float] = {}
        vpi: dict[str, float] = {}
        p_scores: dict[str, float] = {}

        if not shelf_life_projections:
            return PriorityScores(scores={}, sr={}, os={}, vpi={})

        # Compute sub-scores (normalized to [0, 1])
        max_demand = max(
            (p.demand_units for p in shelf_life_projections.values()), default=1
        ) or 1
        max_shelf_life = max(
            (p.remaining_shelf_life_hours for p in shelf_life_projections.values()),
            default=1,
        ) or 1

        for site_id, proj in shelf_life_projections.items():
            # SR_i: Clinical Urgency — shorter remaining shelf life = higher urgency
            # Inverted: sites closest to expiry get highest score
            sr[site_id] = 1.0 - (proj.remaining_shelf_life_hours / max_shelf_life)

            # OS_i: Operational Simplicity — placeholder (proximity, route density)
            # In a full implementation, this would use actual geographic/route data
            os_scores[site_id] = 0.5  # neutral default

            # VPI_i: Value Preservation — higher demand = higher priority
            vpi[site_id] = proj.demand_units / max_demand

            # P_i = w1*SR_i + w2*OS_i + w3*VPI_i
            p_scores[site_id] = (
                policy_weights.w1 * sr[site_id]
                + policy_weights.w2 * os_scores[site_id]
                + policy_weights.w3 * vpi[site_id]
            )

        return PriorityScores(scores=p_scores, sr=sr, os=os_scores, vpi=vpi)

    def build_objective_coefficients(
        self,
        priority_scores: PriorityScores,
        feasible_variables: list,
    ) -> dict[tuple[str, str], float]:
        """Build the objective coefficients for the MILP.

        Returns a dict mapping (vehicle_id, site_id) -> coefficient.
        The coefficient is P_i (the priority score of the site), since we
        maximize Σ (P_i * x_{i,v}).
        """
        coefficients: dict[tuple[str, str], float] = {}
        for var in feasible_variables:
            p_i = priority_scores.scores.get(var.site_id, 0.0)
            coefficients[(var.vehicle_id, var.site_id)] = p_i
        return coefficients
