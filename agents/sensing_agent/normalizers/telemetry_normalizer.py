"""Telemetry Normalizer — Maps raw IoT sensor data to the SenseEvent schema.

Handles multiple input formats (MQTT JSON, CSV, binary sensor protocols)
and normalizes them into the canonical SenseEvent format.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog

from schemas import DisruptionType, SenseEvent, Severity

logger = structlog.get_logger(__name__)


class TelemetryNormalizer:
    """Normalizes various telemetry formats into SenseEvent objects."""

    @staticmethod
    def from_mqtt_json(payload: dict[str, Any]) -> SenseEvent:
        """Normalize a standard MQTT JSON payload."""
        return SenseEvent(
            site_id=payload.get("site_id"),
            route_id=payload.get("route_id"),
            drift_delta_celsius=float(payload.get("temperature_drift", 0.0)),
            disruption_type=DisruptionType(
                payload.get("disruption_type", "thermal_drift")
            ),
            severity=Severity(payload.get("severity", "medium")),
            geo_lat=payload.get("latitude"),
            geo_lon=payload.get("longitude"),
            metadata={
                "source": "mqtt",
                "device_id": payload.get("device_id", ""),
                "raw_temperature": payload.get("temperature"),
                "humidity": payload.get("humidity"),
            },
        )

    @staticmethod
    def from_weather_webhook(payload: dict[str, Any]) -> SenseEvent:
        """Normalize a weather/port disruption webhook payload."""
        return SenseEvent(
            site_id=payload.get("affected_site_id"),
            route_id=payload.get("affected_route_id"),
            drift_delta_celsius=0.0,
            disruption_type=DisruptionType(
                payload.get("event_type", "weather")
            ),
            severity=Severity(payload.get("severity", "medium")),
            geo_lat=payload.get("lat"),
            geo_lon=payload.get("lon"),
            metadata={
                "source": "weather_webhook",
                "event_name": payload.get("event_name", ""),
                "affected_port": payload.get("affected_port", ""),
                "estimated_duration_hours": payload.get("estimated_duration_hours"),
            },
        )

    @staticmethod
    def from_carrier_tracking(payload: dict[str, Any]) -> SenseEvent:
        """Normalize a carrier tracking signal from LBN."""
        return SenseEvent(
            site_id=payload.get("destination_site_id"),
            route_id=payload.get("freight_order_id"),
            drift_delta_celsius=0.0,
            disruption_type=DisruptionType.CARRIER_DELAY,
            severity=Severity(payload.get("severity", "low")),
            geo_lat=payload.get("current_lat"),
            geo_lon=payload.get("current_lon"),
            metadata={
                "source": "lbn_tracking",
                "carrier_id": payload.get("carrier_id", ""),
                "delay_minutes": payload.get("delay_minutes", 0),
                "eta_delay_hours": payload.get("eta_delay_hours", 0),
            },
        )
