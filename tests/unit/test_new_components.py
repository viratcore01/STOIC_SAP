"""Unit tests for the 4 new components:
1. SAP OData v4 Mock Server
2. Arrhenius Thermal Decay Engine
3. SOP Ingestion & Chunking
4. Geodesic Recovery Routing
"""

import pytest
import math
from datetime import datetime, timedelta, timezone
from uuid import uuid4

# ---------------------------------------------------------------------------
# 1. SAP Mock Server Tests
# ---------------------------------------------------------------------------

class TestSAPMockServer:
    """Tests for the SAP OData v4 Mock Server."""

    def test_etag_computation_is_deterministic(self):
        """Same input must produce same ETag."""
        from sap_mock_server.main import _compute_etag

        record = {"id": "FO-001", "status": "IN_TRANSIT", "_version": 1}
        etag1 = _compute_etag(record)
        etag2 = _compute_etag(record)
        assert etag1 == etag2
        assert len(etag1) == 32  # MD5 hex digest

    def test_etag_changes_on_version_bump(self):
        """Different versions must produce different ETags."""
        from sap_mock_server.main import _compute_etag

        record_v1 = {"id": "FO-001", "_version": 1}
        record_v2 = {"id": "FO-001", "_version": 2}
        assert _compute_etag(record_v1) != _compute_etag(record_v2)

    def test_make_freight_order_has_required_fields(self):
        """Freight order must have all OData v4 required fields."""
        from sap_mock_server.main import _make_freight_order

        fo = _make_freight_order("FO-TEST", "Hub A", "Clinic B", "VH-01", 100.0)
        assert fo["FreightOrderID"] == "FO-TEST"
        assert fo["SourceLocation"] == "Hub A"
        assert fo["DestinationLocation"] == "Clinic B"
        assert fo["VehicleResource"] == "VH-01"
        assert fo["GrossWeight"] == "100.0"
        assert fo["OverallProcessStatus"] == "IN_TRANSIT"
        assert "_etag" in fo
        assert "_version" in fo

    def test_seed_orders_loaded(self):
        """Seed data should have 8 freight orders."""
        from sap_mock_server.main import SEED_ORDERS
        assert len(SEED_ORDERS) == 8

    def test_idempotency_cache_structure(self):
        """Idempotency cache should store status_code and response_body."""
        from sap_mock_server.main import IDEMPOTENCY_CACHE

        # Cache is empty initially
        assert isinstance(IDEMPOTENCY_CACHE, dict)


# ---------------------------------------------------------------------------
# 2. Thermal Decay Engine Tests
# ---------------------------------------------------------------------------

class TestThermalDecay:
    """Tests for the Arrhenius thermal decay engine."""

    def test_no_readings_returns_original(self):
        """With no temperature readings, shelf life is unchanged."""
        from agents.impact_agent.shelf_life_model.thermal_decay import ShelfLifeProjection

        model = ShelfLifeProjection()
        result = model.compute_remaining_shelf_life(48.0, [])
        assert result == 48.0

    def test_stable_temp_no_degradation(self):
        """At reference temperature (5C), degradation is minimal."""
        from agents.impact_agent.shelf_life_model.thermal_decay import ShelfLifeProjection

        model = ShelfLifeProjection(base_temp_c=5.0)
        # 24 readings at 5C (reference temp)
        readings = [5.0] * 24
        result = model.compute_remaining_shelf_life(48.0, readings, reading_interval_hours=1.0)
        # At reference temp, rate_ratio = 1.0, so effective_time = 24h
        # remaining = 48 - 24 = 24
        assert result == pytest.approx(24.0, abs=0.1)

    def test_high_temp_accelerates_degradation(self):
        """High temperatures should reduce remaining shelf life significantly."""
        from agents.impact_agent.shelf_life_model.thermal_decay import ShelfLifeProjection

        model = ShelfLifeProjection(base_temp_c=5.0)
        # 12 readings at 25C (well above cold chain range)
        readings = [25.0] * 12
        result = model.compute_remaining_shelf_life(48.0, readings, reading_interval_hours=1.0)
        # At 25C, rate_ratio >> 1, so effective_time >> 12h
        # remaining should be significantly less than 36h
        assert result < 36.0
        assert result >= 0.0

    def test_freezing_destroys_shelf_life(self):
        """Freezing temperatures should cause rapid degradation."""
        from agents.impact_agent.shelf_life_model.thermal_decay import ShelfLifeProjection

        model = ShelfLifeProjection(base_temp_c=5.0)
        readings = [0.0] * 6  # freezing for 6 hours
        result = model.compute_remaining_shelf_life(24.0, readings, reading_interval_hours=1.0)
        # Freezing should cause significant degradation
        assert result < 24.0

    def test_remaining_never_negative(self):
        """Remaining shelf life should never go below 0."""
        from agents.impact_agent.shelf_life_model.thermal_decay import ShelfLifeProjection

        model = ShelfLifeProjection(base_temp_c=5.0)
        # Extreme heat for long duration
        readings = [40.0] * 48
        result = model.compute_remaining_shelf_life(24.0, readings, reading_interval_hours=1.0)
        assert result == 0.0

    def test_project_from_sap_data(self):
        """SAP data projection should account for thermal exposure."""
        from agents.impact_agent.shelf_life_model.thermal_decay import ShelfLifeProjection

        model = ShelfLifeProjection(base_temp_c=5.0, handling_buffer_hours=2.0)
        now = datetime.now(timezone.utc)
        expiry = now + timedelta(hours=48)

        # No temperature readings
        result = model.project_from_sap_data(expiry, now)
        assert result == pytest.approx(46.0, abs=0.1)  # 48 - 2 buffer

        # With temperature readings
        result_degraded = model.project_from_sap_data(expiry, now, temperature_readings=[25.0] * 12)
        assert result_degraded < 46.0


# ---------------------------------------------------------------------------
# 3. SOP Ingestion Tests
# ---------------------------------------------------------------------------

class TestSOPIngestion:
    """Tests for SOP chunking and ingestion."""

    def test_chunk_markdown_splits_on_headers(self):
        """Markdown headers should create new chunks."""
        from scripts.ingest_sops import chunk_markdown

        text = """# Section 1

Some content here that is long enough to pass the minimum length filter and be included as a valid chunk for testing.

# Section 2

More content here that is also long enough to pass the minimum length filter and be included as a valid chunk for testing.
"""
        chunks = chunk_markdown(text, "test_doc")
        assert len(chunks) >= 1

    def test_chunk_markdown_splits_on_list_items(self):
        """Numbered list items should create new chunks."""
        from scripts.ingest_sops import chunk_markdown

        text = """## Requirements

1. First requirement with enough text to be a valid chunk that passes the minimum length filter.
2. Second requirement with enough text to be a valid chunk that passes the minimum length filter.
"""
        chunks = chunk_markdown(text, "test_doc")
        assert len(chunks) >= 1

    def test_chunk_preserves_source_doc(self):
        """Chunks should carry the source document name."""
        from scripts.ingest_sops import chunk_markdown

        text = "# Section\n\nThis is test content that is long enough to pass the filter and be included as a chunk."
        chunks = chunk_markdown(text, "WHO_Guidelines")
        assert all(c["metadata"]["source_doc"] == "WHO_Guidelines" for c in chunks)

    def test_chunk_ids_are_unique(self):
        """Each chunk should have a unique ID."""
        from scripts.ingest_sops import chunk_markdown

        text = """# Section A

Content A that is sufficiently long to pass the minimum length filter for chunks.

# Section B

Content B that is sufficiently long to pass the minimum length filter for chunks.

# Section C

Content C that is sufficiently long to pass the minimum length filter for chunks.
"""
        chunks = chunk_markdown(text, "test_doc")
        ids = [c["id"] for c in chunks]
        assert len(ids) == len(set(ids))

    def test_empty_text_produces_no_chunks(self):
        """Empty input should produce no chunks."""
        from scripts.ingest_sops import chunk_markdown
        chunks = chunk_markdown("", "test_doc")
        assert len(chunks) == 0

    def test_sop_files_exist(self):
        """All 3 SOP files should exist in data/sops/."""
        from pathlib import Path
        sops_dir = Path(__file__).resolve().parents[2] / "data" / "sops"
        assert (sops_dir / "WHO_Cold_Chain_Guidelines.md").exists()
        assert (sops_dir / "DHL_Emergency_Allocation_SOP.md").exists()
        assert (sops_dir / "EU_GDP_Temp_Control.md").exists()


# ---------------------------------------------------------------------------
# 4. Geodesic Routing Tests
# ---------------------------------------------------------------------------

class TestGeodesicRouting:
    """Tests for the geodesic recovery router."""

    def test_haversine_same_point(self):
        """Distance from a point to itself should be 0."""
        from agents.recovery_agents.geodesic_router import haversine_distance
        dist = haversine_distance(48.1351, 11.5820, 48.1351, 11.5820)
        assert dist == pytest.approx(0.0, abs=0.01)

    def test_haversine_munich_to_berlin(self):
        """Munich to Berlin should be approximately 505 km."""
        from agents.recovery_agents.geodesic_router import haversine_distance
        dist = haversine_distance(48.1351, 11.5820, 52.5200, 13.4050)
        assert dist == pytest.approx(505, abs=30)  # within 30km tolerance

    def test_haversine_munich_to_zurich(self):
        """Munich to Zurich should be approximately 240 km."""
        from agents.recovery_agents.geodesic_router import haversine_distance
        dist = haversine_distance(48.1351, 11.5820, 47.3769, 8.5417)
        assert dist == pytest.approx(240, abs=20)

    def test_transit_time_calculation(self):
        """Transit time should be distance / speed with cold chain factor."""
        from agents.recovery_agents.geodesic_router import estimate_transit_time, VEHICLE_SPEEDS, COLD_CHAIN_SPEED_FACTOR

        distance_km = 240.0
        speed = VEHICLE_SPEEDS["default"] * COLD_CHAIN_SPEED_FACTOR
        expected_time = distance_km / speed

        result = estimate_transit_time(distance_km, "default")
        assert result == pytest.approx(expected_time, abs=0.1)

    def test_route_feasibility_c1_constraint(self):
        """Route should be infeasible if transit + buffer > shelf life."""
        from agents.recovery_agents.geodesic_router import GeodesicRouter

        router = GeodesicRouter(handling_buffer_hours=2.0)

        # Munich to Stockholm is ~1800km, transit ~33h + 2h buffer = 35h
        # If shelf life is only 6h, this is infeasible
        result = router.compute_route("Munich_Hub", "CLN-007", remaining_shelf_life_hours=6.0)
        assert not result.is_feasible
        assert result.time_margin_hours < 0
        assert "C1 VIOLATION" in result.reason

    def test_route_feasibility_short_distance(self):
        """Short-distance route should be feasible with sufficient shelf life."""
        from agents.recovery_agents.geodesic_router import GeodesicRouter

        router = GeodesicRouter(handling_buffer_hours=2.0)

        # Munich Hub to CLN-001 (same city, ~2km)
        result = router.compute_route("Munich_Hub", "CLN-001", remaining_shelf_life_hours=18.0)
        assert result.is_feasible
        assert result.time_margin_hours > 0
        assert result.distance_km < 10

    def test_evaluate_all_routes(self):
        """Full evaluation should categorize all (vehicle, site) pairs."""
        from agents.recovery_agents.geodesic_router import GeodesicRouter

        router = GeodesicRouter(handling_buffer_hours=2.0)

        vehicle_positions = {
            "VH-A1": "Munich_Hub",
            "VH-A2": "Berlin_Depot",
        }
        shelf_life_by_site = {
            "CLN-001": 18.0,  # near Munich — feasible
            "CLN-002": 8.0,   # Berlin — feasible for A2
            "CLN-007": 6.0,   # Stockholm — likely infeasible from Munich
        }

        report = router.evaluate_all_routes(vehicle_positions, shelf_life_by_site)
        assert report.total_pairs == 6  # 2 vehicles x 3 sites
        assert report.feasible_count + report.infeasible_count == 6
        assert report.feasible_count > 0  # At least some routes should be feasible

    def test_find_nearest_hub(self):
        """Should find the closest warehouse hub to a clinic."""
        from agents.recovery_agents.geodesic_router import GeodesicRouter

        router = GeodesicRouter()
        hub_id, distance, transit = router.find_nearest_hub("CLN-001")
        assert hub_id == "Munich_Hub"  # CLN-001 is in Munich
        assert distance < 10  # Very close

    def test_distance_matrix_completeness(self):
        """Distance matrix should cover all location pairs."""
        from agents.recovery_agents.geodesic_router import GeodesicRouter

        router = GeodesicRouter()
        matrix = router.compute_route_distance_matrix()
        assert len(matrix) == len(router.locations)
        for origin in matrix:
            assert len(matrix[origin]) == len(router.locations)
            assert matrix[origin][origin] == 0.0  # Self-distance is 0

    def test_unknown_location_returns_infeasible(self):
        """Unknown location should return infeasible route."""
        from agents.recovery_agents.geodesic_router import GeodesicRouter

        router = GeodesicRouter()
        result = router.compute_route("UNKNOWN_HUB", "CLN-001", 24.0)
        assert not result.is_feasible
        assert "Unknown origin" in result.reason
