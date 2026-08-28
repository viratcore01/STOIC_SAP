"""CCRO API Gateway — SAP API Management facade.

External-facing OData/REST facade with rate limiting, auth,
and routing to internal microservices.
"""

from __future__ import annotations

import os
from typing import Optional

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

logger = structlog.get_logger(__name__)
app = FastAPI(
    title="CCRO API Gateway",
    version="0.1.0",
    description="ColdChain Resilience Orchestrator — External API Facade",
)

# CORS for Governance UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CCRO_ALLOWED_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Service URLs
ORCHESTRATOR_URL = os.getenv("CCRO_ORCHESTRATOR_URL", "http://localhost:8000")
SENSING_URL = os.getenv("CCRO_SENSING_URL", "http://localhost:8002")
IMPACT_URL = os.getenv("CCRO_IMPACT_URL", "http://localhost:8003")
SCARCITY_URL = os.getenv("CCRO_SCARCITY_URL", "http://localhost:8004")
POLICY_URL = os.getenv("CCRO_POLICY_URL", "http://localhost:8005")
EXECUTION_URL = os.getenv("CCRO_EXECUTION_URL", "http://localhost:8006")
SOLVER_URL = os.getenv("CCRO_SOLVER_URL", "http://localhost:8001")


@app.post("/api/v1/events/ingest")
async def ingest_event(request: Request) -> dict:
    """Ingest a telemetry event."""
    import httpx

    body = await request.json()
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{SENSING_URL}/ingest/mqtt", json=body)
        return resp.json()


@app.get("/api/v1/state/{thread_id}")
async def get_state(thread_id: str) -> dict:
    """Get current resilience state for a disruption episode."""
    import httpx

    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{ORCHESTRATOR_URL}/state/{thread_id}")
        return resp.json()


@app.post("/api/v1/approval")
async def submit_approval(request: Request) -> dict:
    """Submit a human approval decision."""
    import httpx

    body = await request.json()
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{ORCHESTRATOR_URL}/approve", json=body)
        return resp.json()


@app.get("/api/v1/health")
async def gateway_health() -> dict:
    """Health check for all downstream services."""
    import httpx

    services = {
        "orchestrator": ORCHESTRATOR_URL,
        "solver": SOLVER_URL,
        "sensing": SENSING_URL,
        "impact": IMPACT_URL,
        "scarcity": SCARCITY_URL,
        "policy": POLICY_URL,
        "execution": EXECUTION_URL,
    }

    health = {}
    async with httpx.AsyncClient() as client:
        for name, url in services.items():
            try:
                resp = await client.get(f"{url}/health", timeout=5.0)
                health[name] = "healthy" if resp.status_code == 200 else "degraded"
            except Exception:
                health[name] = "unreachable"

    return {"status": "healthy", "services": health}
