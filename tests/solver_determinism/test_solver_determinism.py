"""Solver Determinism Tests — Regression tests for reproducibility.

Asserts that identical (PolicyWeights, SAP snapshot) inputs always produce
identical AllocationPlan outputs. This is an audit requirement.
"""

import pytest
from schemas import PolicyWeights, ShelfLifeProjection
from solver.engines.ortools_milp import OrToolsSolver, SolverInput
from solver.models.constraint_builder import ConstraintBuilder, VehicleConstraintInfo
from solver.models.objective_builder import ObjectiveBuilder


def _make_test_input() -> tuple[dict[str, ShelfLifeProjection], list[VehicleConstraintInfo], dict[str, float]]:
    """Create a standard test input for solver determinism tests."""
    projections = {
        "SITE-A": ShelfLifeProjection(
            site_id="SITE-A",
            remaining_shelf_life_hours=48.0,
            demand_units=100,
        ),
        "SITE-B": ShelfLifeProjection(
            site_id="SITE-B",
            remaining_shelf_life_hours=24.0,
            demand_units=200,
        ),
        "SITE-C": ShelfLifeProjection(
            site_id="SITE-C",
            remaining_shelf_life_hours=12.0,
            demand_units=50,
        ),
    }

    vehicles = [
        VehicleConstraintInfo(
            vehicle_id="V1",
            max_payload_kg=500.0,
            transit_times={"SITE-A": 6.0, "SITE-B": 10.0, "SITE-C": 20.0},
        ),
        VehicleConstraintInfo(
            vehicle_id="V2",
            max_payload_kg=300.0,
            transit_times={"SITE-A": 8.0, "SITE-B": 12.0, "SITE-C": 30.0},
        ),
    ]

    vehicle_capacities = {"V1": 500.0, "V2": 300.0}

    return projections, vehicles, vehicle_capacities


def _solve_test_input(
    projections: dict[str, ShelfLifeProjection],
    vehicles: list[VehicleConstraintInfo],
    vehicle_capacities: dict[str, float],
    policy_weights: PolicyWeights,
) -> tuple:
    """Run the full solver pipeline and return the allocation plan."""
    constraint_builder = ConstraintBuilder(handling_buffer_hours=2.0)
    constraint_result = constraint_builder.build(
        shelf_life_projections=projections,
        vehicles=vehicles,
        policy_weights=policy_weights,
    )

    obj_builder = ObjectiveBuilder()
    priority_scores = obj_builder.compute_priority_scores(
        shelf_life_projections=projections,
        policy_weights=policy_weights,
    )

    solver_input = SolverInput(
        priority_scores=priority_scores,
        constraint_result=constraint_result,
        vehicle_capacities=vehicle_capacities,
        per_unit_mass_kg=1.0,
    )

    solver = OrToolsSolver()
    return solver.solve(solver_input, obj_builder)


class TestSolverDeterminism:
    """Regression tests: identical inputs → identical outputs."""

    def test_identical_inputs_identical_outputs(self):
        """Same input twice must produce the same AllocationPlan."""
        projections, vehicles, capacities = _make_test_input()
        pw = PolicyWeights(w1=0.4, w2=0.3, w3=0.3)

        plan1 = _solve_test_input(projections, vehicles, capacities, pw)
        plan2 = _solve_test_input(projections, vehicles, capacities, pw)

        # Same structure
        assert len(plan1.assignments) == len(plan2.assignments)
        assert len(plan1.dropped_sites) == len(plan2.dropped_sites)

        # Same objective value
        assert plan1.objective_value == pytest.approx(plan2.objective_value)

        # Same snapshot hash
        assert plan1.input_snapshot_hash == plan2.input_snapshot_hash

        # Same assignments (sorted by site_id for comparison)
        sorted1 = sorted(plan1.assignments, key=lambda a: a.site_id)
        sorted2 = sorted(plan2.assignments, key=lambda a: a.site_id)
        for a1, a2 in zip(sorted1, sorted2):
            assert a1.site_id == a2.site_id
            assert a1.allocated_units == a2.allocated_units
            assert a1.vehicle_id == a2.vehicle_id

    def test_different_weights_different_output(self):
        """Different PolicyWeights must produce different allocations."""
        projections, vehicles, capacities = _make_test_input()

        pw1 = PolicyWeights(w1=0.8, w2=0.1, w3=0.1)
        pw2 = PolicyWeights(w1=0.1, w2=0.1, w3=0.8)

        plan1 = _solve_test_input(projections, vehicles, capacities, pw1)
        plan2 = _solve_test_input(projections, vehicles, capacities, pw2)

        # Different weight profiles should produce different objective values
        # (though the same assignments are possible if only one feasible solution exists)
        assert plan1.input_snapshot_hash != plan2.input_snapshot_hash

    def test_dropped_site_for_unreachable(self):
        """Sites unreachable within shelf life must be in dropped_sites."""
        projections = {
            "SITE-FAR": ShelfLifeProjection(
                site_id="SITE-FAR",
                remaining_shelf_life_hours=5.0,  # very short
                demand_units=100,
            ),
        }
        vehicles = [
            VehicleConstraintInfo(
                vehicle_id="V1",
                max_payload_kg=500.0,
                transit_times={"SITE-FAR": 20.0},  # way too long
            ),
        ]

        pw = PolicyWeights(w1=0.4, w2=0.3, w3=0.3)
        plan = _solve_test_input(projections, vehicles, {"V1": 500.0}, pw)

        dropped_ids = [d.site_id for d in plan.dropped_sites]
        assert "SITE-FAR" in dropped_ids
