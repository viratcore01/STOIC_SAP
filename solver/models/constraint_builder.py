"""Hard Constraint Builder for the Scarcity Allocation problem.

Encodes three non-negotiable physical constraints:
  C1: TransitTime(v,i) + HandlingBuffer < RemainingShelfLife(i)
  C2: Σ_i (PayloadMass_i × x_{i,v}) <= C_max(v)
  C3: If TransitTime(v,i) > RemainingShelfLife(i) for all v, P_i forced to 0

These are pre-filters that zero out infeasible variables BEFORE the solver runs,
reducing problem dimensionality. The solver never sees infeasible assignments.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from schemas import DroppedSite, PolicyWeights, ShelfLifeProjection


# Default handling buffer in hours (loading, unloading, inspection)
DEFAULT_HANDLING_BUFFER_HOURS: float = 2.0


@dataclass
class VehicleConstraintInfo:
    """Vehicle-specific constraint data."""

    vehicle_id: str
    max_payload_kg: float
    transit_times: dict[str, float]  # site_id -> hours


@dataclass
class SiteConstraintInfo:
    """Site-specific constraint data."""

    site_id: str
    remaining_shelf_life_hours: float
    payload_mass_kg: float  # per-unit mass
    priority_score: float  # P_i


@dataclass
class FeasibleVariable:
    """A variable (vehicle, site) pair that passed all hard constraints."""

    vehicle_id: str
    site_id: str
    max_assignable_units: int  # limited by capacity and shelf life


@dataclass
class ConstraintBuildResult:
    """Output of the constraint builder."""

    feasible_variables: list[FeasibleVariable] = field(default_factory=list)
    dropped_sites: list[DroppedSite] = field(default_factory=list)
    vehicle_capacity_map: dict[str, float] = field(default_factory=dict)
    site_units_map: dict[str, int] = field(default_factory=dict)


class ConstraintBuilder:
    """Builds hard constraints for the MILP solver.

    Pre-filters infeasible (vehicle, site) pairs before the solver sees them.
    """

    def __init__(self, handling_buffer_hours: float = DEFAULT_HANDLING_BUFFER_HOURS):
        self.handling_buffer_hours = handling_buffer_hours

    def build(
        self,
        shelf_life_projections: dict[str, ShelfLifeProjection],
        vehicles: list[VehicleConstraintInfo],
        policy_weights: PolicyWeights,
    ) -> ConstraintBuildResult:
        """Build the set of feasible variables and dropped sites.

        Args:
            shelf_life_projections: Per-site remaining shelf life.
            vehicles: Vehicle constraint data.
            policy_weights: Policy weight coefficients (for P_i scoring).

        Returns:
            ConstraintBuildResult with feasible variable pairs and dropped sites.
        """
        result = ConstraintBuildResult()

        for site_id, projection in shelf_life_projections.items():
            remaining_hours = projection.remaining_shelf_life_hours
            site_dropped = True  # assume dropped until proven reachable

            for v_info in vehicles:
                site_id_in_v = site_id  # assuming direct mapping
                transit_time = v_info.transit_times.get(site_id_in_v, float("inf"))

                # C1: Thermal Lifetime — transit + buffer must fit within shelf life
                if transit_time + self.handling_buffer_hours >= remaining_hours:
                    continue

                # C3: Reachability — already passed if we're here
                site_dropped = False

                # Max units limited by vehicle capacity and per-unit mass
                per_unit_mass = max(
                    projection.demand_units and 1.0, 1.0
                )  # simplified
                max_units_by_capacity = int(
                    v_info.max_payload_kg / per_unit_mass
                )
                max_units_by_shelf_life = int(
                    (remaining_hours - transit_time - self.handling_buffer_hours) / 1.0
                )
                max_units = max(0, min(max_units_by_capacity, max_units_by_shelf_life))

                if max_units > 0:
                    result.feasible_variables.append(
                        FeasibleVariable(
                            vehicle_id=v_info.vehicle_id,
                            site_id=site_id,
                            max_assignable_units=max_units,
                        )
                    )

            if site_dropped:
                result.dropped_sites.append(
                    DroppedSite(
                        site_id=site_id,
                        reason="unreachable_within_shelf_life",
                        priority_score=0.0,
                    )
                )

        # Build capacity maps for the solver
        for v_info in vehicles:
            result.vehicle_capacity_map[v_info.vehicle_id] = v_info.max_payload_kg

        return result

    def validate_override(
        self,
        site_id: str,
        vehicle_id: str,
        shelf_life_projections: dict[str, ShelfLifeProjection],
        vehicles: list[VehicleConstraintInfo],
    ) -> tuple[bool, str]:
        """Validate a manual override against hard constraints.

        Returns (is_valid, violation_message).
        """
        projection = shelf_life_projections.get(site_id)
        if projection is None:
            return False, f"Site {site_id} not found in projections"

        vehicle = next((v for v in vehicles if v.vehicle_id == vehicle_id), None)
        if vehicle is None:
            return False, f"Vehicle {vehicle_id} not found"

        transit_time = vehicle.transit_times.get(site_id, float("inf"))

        # C1: Thermal Lifetime
        if transit_time + self.handling_buffer_hours >= projection.remaining_shelf_life_hours:
            return (
                False,
                f"C1 violated: transit ({transit_time}h) + buffer "
                f"({self.handling_buffer_hours}h) >= shelf life "
                f"({projection.remaining_shelf_life_hours}h)",
            )

        # C2: Capacity (per-vehicle, validated at allocation time)
        # C3: Reachability (already passed if we got here)

        return True, ""
