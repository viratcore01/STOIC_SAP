"""Continuous relaxation solver using SciPy for rapid feasibility pre-checks.

Before committing to the more expensive MILP pass, this engine runs a
continuous (non-integer) relaxation to quickly determine if a feasible
solution exists at all. If the relaxed problem is infeasible, the MILP
will certainly be infeasible too.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import linprog

from solver.models.constraint_builder import ConstraintBuildResult, FeasibleVariable
from solver.models.objective_builder import ObjectiveBuilder, PriorityScores


@dataclass
class RelaxationResult:
    """Result of the continuous relaxation pre-check."""

    is_feasible: bool
    objective_value: float = 0.0
    relaxed_allocations: dict[tuple[str, str], float] = (
        {}
    )  # (vehicle, site) -> fractional units
    message: str = ""


class SciPyRelaxation:
    """Continuous relaxation feasibility pre-check.

    Solves the LP relaxation of the MILP to quickly determine feasibility.
    If infeasible, the full MILP is skipped.
    """

    def check_feasibility(
        self,
        feasible_variables: list[FeasibleVariable],
        priority_scores: PriorityScores,
        vehicle_capacities: dict[str, float],
        per_unit_mass: float = 1.0,
    ) -> RelaxationResult:
        """Run LP relaxation to check if a feasible solution exists."""
        if not feasible_variables:
            return RelaxationResult(
                is_feasible=False, message="No feasible variables"
            )

        # Build variable index
        var_list = [(v.vehicle_id, v.site_id) for v in feasible_variables]
        n_vars = len(var_list)
        var_index = {pair: i for i, pair in enumerate(var_list)}
        var_bounds = {
            (v.vehicle_id, v.site_id): (0, v.max_assignable_units)
            for v in feasible_variables
        }

        # Objective: maximize Σ P_i * x_{i,v} → minimize -Σ P_i * x_{i,v}
        c = np.zeros(n_vars)
        p_scores = priority_scores.scores
        for vid, sid in var_list:
            c[var_index[(vid, sid)]] = -p_scores.get(sid, 0.0)

        # Variable bounds
        bounds = [
            (0, var_bounds[(vid, sid)]) for vid, sid in var_list
        ]

        # Capacity constraints: Σ_i mass * x_{i,v} <= C_max(v)
        # One constraint per vehicle
        vehicles = set(vid for vid, _ in var_list)
        n_constraints = len(vehicles)
        A_ub = np.zeros((n_constraints, n_vars))
        b_ub = np.zeros(n_constraints)

        for row, vid in enumerate(vehicles):
            for sid in [s for v, s in var_list if v == vid]:
                A_ub[row, var_index[(vid, sid)]] = per_unit_mass
            b_ub[row] = vehicle_capacities.get(vid, 0)

        # Solve
        result = linprog(c, A_ub=A_ub, b_ub=b_ub, bounds=bounds, method="highs")

        if result.success:
            allocations = {}
            for vid, sid in var_list:
                val = result.x[var_index[(vid, sid)]]
                if val > 1e-6:
                    allocations[(vid, sid)] = val

            return RelaxationResult(
                is_feasible=True,
                objective_value=-result.fun,  # un-negate
                relaxed_allocations=allocations,
                message="LP relaxation feasible",
            )
        else:
            return RelaxationResult(
                is_feasible=False,
                message=f"LP relaxation infeasible: {result.message}",
            )
