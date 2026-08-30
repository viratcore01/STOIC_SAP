"""Geodesic Recovery Routing — Haversine-based transit time and distance calculation.

Uses real geographic coordinates to compute:
1. Great-circle distances between warehouse hubs, vehicles, and clinic sites
2. Estimated transit times based on distance and average speed
3. Route feasibility checks against remaining shelf life (Constraint C1)
4. Flags infeasible (vehicle, site) pairs for the Scarcity Engine

This replaces placeholder heuristics with physically-grounded routing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)

# Earth's mean radius in kilometers
EARTH_RADIUS_KM = 6371.0

# Average speeds by vehicle type (km/h)
VEHICLE_SPEEDS = {
    "refrigerated_truck_large": 65.0,
    "refrigerated_truck_medium": 60.0,
    "refrigerated_van_large": 55.0,
    "refrigerated_van_medium": 50.0,
    "refrigerated_van_small": 45.0,
    "default": 55.0,
}

# Default handling buffer in hours
DEFAULT_HANDLING_BUFFER_HOURS = 2.0

# Speed factor for cold chain (slower due to temperature constraints)
COLD_CHAIN_SPEED_FACTOR = 0.85


@dataclass
class GeoLocation:
    """A geographic location with coordinates."""
    name: str
    latitude: float
    longitude: float
    location_type: str = "clinic"  # clinic, warehouse, hub


@dataclass
class RouteResult:
    """Result of a geodesic route calculation."""
    origin: str
    destination: str
    distance_km: float
    transit_time_hours: float
    is_feasible: bool
    remaining_shelf_life_hours: float
    time_margin_hours: float  # remaining_shelf_life - transit_time - buffer
    reason: str = ""


@dataclass
class RouteFeasibilityReport:
    """Complete feasibility report for all (vehicle, site) pairs."""
    feasible_routes: list[RouteResult] = field(default_factory=list)
    infeasible_routes: list[RouteResult] = field(default_factory=list)
    total_pairs: int = 0
    feasible_count: int = 0
    infeasible_count: int = 0


# ---------------------------------------------------------------------------
# European clinic and warehouse coordinates (realistic locations)
# ---------------------------------------------------------------------------

LOCATIONS = {
    # Warehouse hubs
    "Munich_Hub": GeoLocation("Munich Distribution Hub", 48.1351, 11.5820, "warehouse"),
    "Berlin_Depot": GeoLocation("Berlin Logistics Depot", 52.5200, 13.4050, "warehouse"),
    "Rotterdam_Port": GeoLocation("Rotterdam Port Terminal", 51.9225, 4.4792, "warehouse"),
    "Paris_Depot": GeoLocation("Paris Logistics Center", 48.8566, 2.3522, "warehouse"),

    # Clinic sites
    "CLN-001": GeoLocation("St. Mary's Hospital, Munich", 48.1508, 11.5802, "clinic"),
    "CLN-002": GeoLocation("Charite Campus Virchow, Berlin", 52.5236, 13.3417, "clinic"),
    "CLN-003": GeoLocation("Universitatsklinikum Koln", 50.9333, 6.9500, "clinic"),
    "CLN-004": GeoLocation("Hannover Medical School", 52.3750, 9.8100, "clinic"),
    "CLN-005": GeoLocation("University Hospital Zurich", 47.3769, 8.5417, "clinic"),
    "CLN-006": GeoLocation("Erasmus MC Rotterdam", 51.9115, 4.4736, "clinic"),
    "CLN-007": GeoLocation("Karolinska University Hospital", 59.3489, 18.0238, "clinic"),
    "CLN-008": GeoLocation("Hopital Pitie-Salpetriere", 48.8384, 2.3640, "clinic"),
}


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute the great-circle distance between two points using the Haversine formula.

    Args:
        lat1, lon1: Latitude and longitude of point 1 in degrees.
        lat2, lon2: Latitude and longitude of point 2 in degrees.

    Returns:
        Distance in kilometers.
    """
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return EARTH_RADIUS_KM * c


def estimate_transit_time(distance_km: float, vehicle_type: str = "default") -> float:
    """Estimate transit time from distance and vehicle speed.

    Applies a cold-chain speed factor to account for temperature constraints.

    Args:
        distance_km: Distance in kilometers.
        vehicle_type: Vehicle type key for speed lookup.

    Returns:
        Estimated transit time in hours.
    """
    speed = VEHICLE_SPEEDS.get(vehicle_type, VEHICLE_SPEEDS["default"])
    speed_with_cold_chain_factor = speed * COLD_CHAIN_SPEED_FACTOR
    return distance_km / speed_with_cold_chain_factor


class GeodesicRouter:
    """Geodesic recovery router that calculates true transit times and distances.

    Uses real geographic coordinates and the Haversine formula to compute
    physically-grounded route feasibility checks.
    """

    def __init__(
        self,
        handling_buffer_hours: float = DEFAULT_HANDLING_BUFFER_HOURS,
        locations: dict[str, GeoLocation] | None = None,
    ):
        self.handling_buffer_hours = handling_buffer_hours
        self.locations = locations or LOCATIONS

    def compute_route(
        self,
        origin_id: str,
        destination_id: str,
        remaining_shelf_life_hours: float,
        vehicle_type: str = "default",
    ) -> RouteResult:
        """Compute a single route between origin and destination.

        Args:
            origin_id: ID of the origin location (warehouse or vehicle position).
            destination_id: ID of the destination clinic.
            remaining_shelf_life_hours: Remaining cold-chain viability in hours.
            vehicle_type: Vehicle type for speed estimation.

        Returns:
            RouteResult with distance, transit time, and feasibility assessment.
        """
        origin = self.locations.get(origin_id)
        destination = self.locations.get(destination_id)

        if not origin:
            return RouteResult(
                origin=origin_id,
                destination=destination_id,
                distance_km=0,
                transit_time_hours=float("inf"),
                is_feasible=False,
                remaining_shelf_life_hours=remaining_shelf_life_hours,
                time_margin_hours=float("-inf"),
                reason=f"Unknown origin: {origin_id}",
            )

        if not destination:
            return RouteResult(
                origin=origin_id,
                destination=destination_id,
                distance_km=0,
                transit_time_hours=float("inf"),
                is_feasible=False,
                remaining_shelf_life_hours=remaining_shelf_life_hours,
                time_margin_hours=float("-inf"),
                reason=f"Unknown destination: {destination_id}",
            )

        # Compute geodesic distance
        distance_km = haversine_distance(
            origin.latitude, origin.longitude,
            destination.latitude, destination.longitude,
        )

        # Estimate transit time
        transit_time = estimate_transit_time(distance_km, vehicle_type)

        # Add handling buffer
        total_time = transit_time + self.handling_buffer_hours

        # Check feasibility (C1: Thermal Lifetime)
        time_margin = remaining_shelf_life_hours - total_time
        is_feasible = time_margin > 0

        reason = ""
        if not is_feasible:
            reason = (
                f"C1 VIOLATION: transit ({transit_time:.1f}h) + buffer "
                f"({self.handling_buffer_hours}h) = {total_time:.1f}h >= "
                f"shelf life ({remaining_shelf_life_hours:.1f}h)"
            )

        result = RouteResult(
            origin=origin_id,
            destination=destination_id,
            distance_km=round(distance_km, 1),
            transit_time_hours=round(transit_time, 2),
            is_feasible=is_feasible,
            remaining_shelf_life_hours=remaining_shelf_life_hours,
            time_margin_hours=round(time_margin, 2),
            reason=reason,
        )

        if not is_feasible:
            logger.warning(
                "route.infeasible",
                origin=origin_id,
                destination=destination_id,
                distance_km=round(distance_km, 1),
                transit_hours=round(transit_time, 2),
                shelf_life_hours=remaining_shelf_life_hours,
            )

        return result

    def evaluate_all_routes(
        self,
        vehicle_positions: dict[str, str],  # vehicle_id -> current location_id
        shelf_life_by_site: dict[str, float],  # site_id -> remaining shelf life hours
        vehicle_types: dict[str, str] | None = None,  # vehicle_id -> vehicle type
    ) -> RouteFeasibilityReport:
        """Evaluate feasibility for all (vehicle, site) combinations.

        Args:
            vehicle_positions: Mapping of vehicle_id to current location_id.
            shelf_life_by_site: Mapping of site_id to remaining shelf life in hours.
            vehicle_types: Optional mapping of vehicle_id to vehicle type.

        Returns:
            RouteFeasibilityReport with feasible and infeasible routes.
        """
        report = RouteFeasibilityReport()
        vehicle_types = vehicle_types or {}

        for vehicle_id, origin_id in vehicle_positions.items():
            vehicle_type = vehicle_types.get(vehicle_id, "default")

            for site_id, shelf_life in shelf_life_by_site.items():
                report.total_pairs += 1

                result = self.compute_route(
                    origin_id=origin_id,
                    destination_id=site_id,
                    remaining_shelf_life_hours=shelf_life,
                    vehicle_type=vehicle_type,
                )

                if result.is_feasible:
                    report.feasible_routes.append(result)
                    report.feasible_count += 1
                else:
                    report.infeasible_routes.append(result)
                    report.infeasible_count += 1

        logger.info(
            "route.evaluation_completed",
            total_pairs=report.total_pairs,
            feasible=report.feasible_count,
            infeasible=report.infeasible_count,
        )

        return report

    def find_nearest_hub(self, site_id: str) -> tuple[str, float, float]:
        """Find the nearest warehouse hub to a clinic site.

        Args:
            site_id: Clinic site ID.

        Returns:
            Tuple of (hub_id, distance_km, transit_time_hours).
        """
        site = self.locations.get(site_id)
        if not site:
            return ("", float("inf"), float("inf"))

        nearest_hub = None
        min_distance = float("inf")

        for loc_id, loc in self.locations.items():
            if loc.location_type == "warehouse":
                distance = haversine_distance(
                    site.latitude, site.longitude,
                    loc.latitude, loc.longitude,
                )
                if distance < min_distance:
                    min_distance = distance
                    nearest_hub = loc_id

        if nearest_hub:
            transit_time = estimate_transit_time(min_distance)
            return (nearest_hub, min_distance, transit_time)
        return ("", float("inf"), float("inf"))

    def compute_route_distance_matrix(self) -> dict[str, dict[str, float]]:
        """Compute full distance matrix between all locations.

        Returns:
            Nested dict: distances[origin_id][destination_id] = km.
        """
        distances = {}
        for orig_id, orig in self.locations.items():
            distances[orig_id] = {}
            for dest_id, dest in self.locations.items():
                if orig_id == dest_id:
                    distances[orig_id][dest_id] = 0.0
                else:
                    distances[orig_id][dest_id] = round(
                        haversine_distance(orig.latitude, orig.longitude, dest.latitude, dest.longitude),
                        1,
                    )
        return distances
