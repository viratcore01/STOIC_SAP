"""Primary solver using Google OR-Tools CP-SAT for Mixed-Integer Linear Programming.

Models the scarcity allocation problem as:
  Maximize Σ_i (P_i × Σ_v x_{i,v})
  Subject to:
    C1: (pre-filtered — infeasible pairs removed)
    C2: Σ_i (payload_mass × x_{i,v}) <= C_max(v)  for each vehicle v
    C3: (pre-filtered — unreachable sites dropped)
    x_{i,v} ∈ {0, 1, 2, ...}  (integer allocation units)

The solver is stateless, versioned (pinned OR-Tools), and seeded deterministically.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from ortools.sat.python import cp_model

from solver.models.constraint_builder import (
    ConstraintBuildResult,
    FeasibleVariable,
)
from solver.models.objective_builder import ObjectiveBuilder, PriorityScores
from schemas import AllocationPlan, DroppedSite, PolicyWeights, SiteAllocation


SOLVER_VERSION = "ortools-cp-sat-9.8"


@dataclass
class SolverInput:
    """Complete input snapshot for deterministic re-runs."""

    priority_scores: PriorityScores
    constraint_result: ConstraintBuildResult
    vehicle_capacities: dict[str, float]
    per_unit_mass: float = 1.0  # kg per allocation unit

    def snapshot_hash(self) -> str:
        """Compute a deterministic hash of the input for audit reproducibility."""
        data = {
            "priority_scores": self.priority_scores.scores,
            "feasible_variables": [
                (v.vehicle_id, v.site_id, v.max_assignable_units)
                for v in self.constraint_result.feasible_variables
            ],
            "vehicle_capacities": self.vehicle_capacities,
            "per_unit_mass": self.per_unit_mass,
        }
        raw = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()


class OrToolsSolver:
    """CP-SAT solver for the allocation MILP.

    Stateless: identical inputs always produce identical outputs.
    """

    def __init__(self, time_limit_seconds: int = 30):
        self.time_limit_seconds = time_limit_seconds

    def solve(
        self,
        solver_input: SolverInput,
        objective_builder: ObjectiveBuilder | None = None,
    ) -> AllocationPlan:
        """Run the MILP solver and return an AllocationPlan."""
        obj_builder = objective_builder or ObjectiveBuilder()
        model = cp_model.CpModel()

        feasible = solver_input.constraint_result.feasible_variables
        if not feasible:
            return AllocationPlan(
                dropped_sites=solver_input.constraint_result.dropped_sites,
                solver_version=SOLVER_VERSION,
                input_snapshot_hash=solver_input.snapshot_hash(),
            )

        # Decision variables: x[v_id, s_id] ∈ {0, ..., max_units}
        x: dict[tuple[str, str], cp_model.IntVar] = {}
        for var in feasible:
            x[(var.vehicle_id, var.site_id)] = model.NewIntVar(
                0, var.max_assignable_units, f"x_{var.vehicle_id}_{var.site_id}"
            )

        # C2: Capacity constraint per vehicle
        vehicles_by_id: dict[str, list[FeasibleVariable]] = {}
        for var in feasible:
            vehicles_by_id.setdefault(var.vehicle_id, []).append(var)

        for vehicle_id, vehicle_vars in vehicles_by_id.items():
            cap = int(solver_input.vehicle_capacities.get(vehicle_id, 0))
            mass = int(solver_input.per_unit_mass * 1000)  # scale to int
            model.Add(
                sum(
                    x[(v.vehicle_id, v.site_id)] * mass
                    for v in vehicle_vars
                )
                <= cap * 1000
            )

        # Objective: maximize Σ (P_i * x_{i,v})
        p_scores = solver_input.priority_scores.scores
        objective_terms = []
        for var in feasible:
            p_i = p_scores.get(var.site_id, 0.0)
            # CP-SAT requires integer coefficients; scale by 1000 for precision
            scaled_p = int(p_i * 1000)
            objective_terms.append(x[(var.vehicle_id, var.site_id)] * scaled_p)

        model.Maximize(sum(objective_terms) if objective_terms else 0)

        # Solve
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = self.time_limit_seconds
        # Deterministic seed for reproducibility
        solver.parameters.random_seed = 42

        status = solver.Solve(model)

        # Build output
        assignments: list[SiteAllocation] = []
        objective_value = 0.0

        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            for var in feasible:
                val = solver.Value(x[(var.vehicle_id, var.site_id)])
                if val > 0:
                    p_i = p_scores.get(var.site_id, 0.0)
                    assignments.append(
                        SiteAllocation(
                            site_id=var.site_id,
                            allocated_units=val,
                            vehicle_id=var.vehicle_id,
                            priority_score=p_i,
                            payload_mass_kg=val * solver_input.per_unit_mass,
                        )
                    )
                    objective_value += p_i * val

        # Sites with no feasible assignments are dropped
        dropped = list(solver_input.constraint_result.dropped_sites)
        assigned_site_ids = {a.site_id for a in assignments}
        # Check for sites that had feasible variables but got zero allocation
        all_feasible_site_ids = {v.site_id for v in feasible}
        for site_id in all_feasible_site_ids - assigned_site_ids:
            dropped.append(
                DroppedSite(
                    site_id=site_id,
                    reason="capacity_exhausted",
                    priority_score=p_scores.get(site_id, 0.0),
                )
            )

        return AllocationPlan(
            assignments=assignments,
            dropped_sites=dropped,
            objective_value=objective_value / 1000.0,  # un-scale
            solver_version=SOLVER_VERSION,
            input_snapshot_hash=solver_input.snapshot_hash(),
        )
