"""Sensing Agent Service — IoT + weather + port signal ingestion.

Phase 1 — SENSE: Receives telemetry from Event Mesh, normalizes events,
and emits SenseEvents to the Orchestrator.
"""

from __future__ import annotations

from typing import Optional

import structlog
from fastapi import FastAPI

from agents.sensing_agent.ingestion.event_mesh_consumer import EventMeshConsumer
from agents.sensing_agent.normalizers.telemetry_normalizer import TelemetryNormalizer
from schemas import SenseEvent

logger = structlog.get_logger(__name__)
app = FastAPI(title="CCRO Sensing Agent", version="0.1.0")

# Initialize components
normalizer = TelemetryNormalizer()
consumer = EventMeshConsumer()
_telemetry_buffer: list[SenseEvent] = []


async def _on_event(event: SenseEvent) -> None:
    """Callback for incoming events — buffer and forward to orchestrator."""
    _telemetry_buffer.append(event)
    logger.info(
        "sensing.event_received",
        event_id=event.event_id,
        disruption_type=event.disruption_type.value,
        severity=event.severity.value,
    )


consumer.on_event = _on_event


@app.post("/ingest/mqtt")
async def ingest_mqtt(payload: dict) -> dict:
    """Ingest an MQTT telemetry payload."""
    event = normalizer.from_mqtt_json(payload)
    _telemetry_buffer.append(event)
    return {"status": "accepted", "event_id": event.event_id}


@app.post("/ingest/weather")
async def ingest_weather(payload: dict) -> dict:
    """Ingest a weather/port disruption webhook payload."""
    event = normalizer.from_weather_webhook(payload)
    _telemetry_buffer.append(event)
    return {"status": "accepted", "event_id": event.event_id}


@app.post("/ingest/tracking")
async def ingest_tracking(payload: dict) -> dict:
    """Ingest a carrier tracking signal from LBN."""
    event = normalizer.from_carrier_tracking(payload)
    _telemetry_buffer.append(event)
    return {"status": "accepted", "event_id": event.event_id}


@app.get("/events")
async def get_pending_events() -> list[dict]:
    """Return buffered events (consumed by Orchestrator)."""
    events = [e.model_dump() for e in _telemetry_buffer]
    return events


@app.post("/events/drain")
async def drain_events() -> list[dict]:
    """Drain and return all buffered events (consumed by Orchestrator)."""
    events = [e.model_dump() for e in _telemetry_buffer]
    _telemetry_buffer.clear()
    return events


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy", "buffered_events": str(len(_telemetry_buffer))}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8002)
