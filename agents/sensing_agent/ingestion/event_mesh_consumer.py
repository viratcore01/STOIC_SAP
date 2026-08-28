"""Event Mesh Consumer — Subscribes to BTP Event Mesh for IoT telemetry and weather signals.

Handles MQTT bridge events from IoT gateways and REST webhook payloads
from weather/port disruption feeds.
"""

from __future__ import annotations

import json
from typing import Callable, Optional, Awaitable

import structlog

from schemas import DisruptionType, SenseEvent, Severity

logger = structlog.get_logger(__name__)


class EventMeshConsumer:
    """Consumes events from SAP BTP Event Mesh.

    In production, this uses the SAP BTP Event Mesh REST/MQTT bridge.
    For development, it accepts events via a push interface.
    """

    def __init__(
        self,
        topic: str = "ccro/telemetry/ingest",
        on_event: Optional[Callable[[SenseEvent], Awaitable[None]]] = None,
    ):
        self.topic = topic
        self.on_event = on_event
        self._running = False

    def parse_telemetry_event(self, raw_payload: dict) -> Optional[SenseEvent]:
        """Parse a raw MQTT/webhook payload into a SenseEvent."""
        try:
            disruption_type = DisruptionType(
                raw_payload.get("disruption_type", "thermal_drift")
            )
            severity = Severity(raw_payload.get("severity", "medium"))

            return SenseEvent(
                site_id=raw_payload.get("site_id"),
                route_id=raw_payload.get("route_id"),
                drift_delta_celsius=float(raw_payload.get("drift_delta_celsius", 0.0)),
                disruption_type=disruption_type,
                severity=severity,
                geo_lat=raw_payload.get("geo_lat"),
                geo_lon=raw_payload.get("geo_lon"),
                metadata=raw_payload.get("metadata", {}),
            )
        except (ValueError, KeyError) as e:
            logger.error("sensing.parse_error", error=str(e), payload=raw_payload)
            return None

    async def handle_message(self, raw_payload: dict) -> Optional[SenseEvent]:
        """Handle an incoming Event Mesh message."""
        event = self.parse_telemetry_event(raw_payload)
        if event and self.on_event:
            await self.on_event(event)
        return event

    def start_listening(self) -> None:
        """Start the Event Mesh consumer loop.

        In production, this connects to the MQTT broker via paho-mqtt.
        """
        self._running = True
        logger.info("sensing.consumer_started", topic=self.topic)
        # Production: paho-mqtt client.connect() + client.loop_forever()
        # Development: events pushed via handle_message()

    def stop_listening(self) -> None:
        """Stop the consumer loop."""
        self._running = False
        logger.info("sensing.consumer_stopped")
