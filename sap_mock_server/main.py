"""SAP OData v4 Mock Server — Standalone FastAPI service emulating SAP TM.

Implements:
- GET /FreightOrder — list/query freight orders
- GET /FreightOrder('{id}') — read single freight order
- PATCH /FreightOrder('{id}') — update freight order with ETag validation
- Idempotency key ledger — cache responses, return previous on duplicates
- ETag validation — return 412 Precondition Failed on mismatch

Start: uvicorn sap_mock_server.main:app --port 8080
"""

from __future__ import annotations

import hashlib
import json
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

import structlog

logger = structlog.get_logger(__name__)

app = FastAPI(title="SAP TM OData v4 Mock Server", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# In-memory FreightOrder store (seeded with mock data)
# ---------------------------------------------------------------------------

def _compute_etag(record: dict) -> str:
    """Compute ETag from record version hash."""
    raw = json.dumps(record, sort_keys=True, default=str)
    return hashlib.md5(raw.encode()).hexdigest()


def _make_freight_order(
    fo_id: str,
    source: str,
    destination: str,
    vehicle: str,
    weight: float,
    status: str = "IN_TRANSIT",
) -> dict:
    """Create a mock freight order record."""
    record = {
        "FreightOrderID": fo_id,
        "SourceLocation": source,
        "DestinationLocation": destination,
        "VehicleResource": vehicle,
        "GrossWeight": str(weight),
        "OverallProcessStatus": status,
        "CCRO_AllocationReference": "",
        "CCRO_ApproverID": "",
        "CCRO_PriorityScore": "",
        "CreatedAt": datetime.now(timezone.utc).isoformat(),
        "ModifiedAt": datetime.now(timezone.utc).isoformat(),
        "_version": 1,
    }
    record["_etag"] = _compute_etag(record)
    return record


# Seed data — matches demo clinic/vehicle structure
FREIGHT_ORDERS: dict[str, dict] = {}

SEED_ORDERS = [
    ("FO-VH-A1-CLN001", "Munich Hub", "St. Mary's Hospital, Munich", "VH-A1", 120.0),
    ("FO-VH-A2-CLN002", "Berlin Depot", "Charite Campus Virchow, Berlin", "VH-A2", 200.0),
    ("FO-VH-B1-CLN003", "Cologne Hub", "Universitatsklinikum Koln", "VH-B1", 85.0),
    ("FO-VH-A1-CLN004", "Hannover Depot", "Hannover Medical School", "VH-A1", 150.0),
    ("FO-VH-A2-CLN005", "Zurich Hub", "University Hospital Zurich", "VH-A2", 95.0),
    ("FO-VH-B1-CLN006", "Rotterdam Port", "Erasmus MC Rotterdam", "VH-B1", 65.0),
    ("FO-VH-A1-CLN007", "Stockholm Hub", "Karolinska University Hospital", "VH-A1", 180.0),
    ("FO-VH-C1-CLN008", "Paris Depot", "Hopital Pitie-Salpetriere", "VH-C1", 110.0),
]

for fo_id, src, dst, veh, wt in SEED_ORDERS:
    FREIGHT_ORDERS[fo_id] = _make_freight_order(fo_id, src, dst, veh, wt)

# ---------------------------------------------------------------------------
# Idempotency ledger
# ---------------------------------------------------------------------------

IDEMPOTENCY_CACHE: dict[str, dict] = {}  # key -> {status_code, response_body}


# ---------------------------------------------------------------------------
# OData v4 Endpoints
# ---------------------------------------------------------------------------

@app.get("/sap/opu/odata4/sap/api_freightorder/FreightOrder")
async def list_freight_orders(
    filter: Optional[str] = None,
    select: Optional[str] = None,
):
    """List freight orders with optional OData $filter and $select."""
    orders = list(FREIGHT_ORDERS.values())

    # Simple filter parsing (e.g., "OverallProcessStatus ne 'COMPLETED'")
    if filter:
        if "ne 'COMPLETED'" in filter:
            orders = [o for o in orders if o["OverallProcessStatus"] != "COMPLETED"]
        elif "eq 'COMPLETED'" in filter:
            orders = [o for o in orders if o["OverallProcessStatus"] == "COMPLETED"]
        elif "eq '" in filter:
            # Parse field eq 'value'
            parts = filter.split("eq")
            if len(parts) == 2:
                field = parts[0].strip()
                value = parts[1].strip().strip("'")
                orders = [o for o in orders if o.get(field) == value]

    # Strip internal fields for OData response
    results = []
    for o in orders:
        result = {k: v for k, v in o.items() if not k.startswith("_")}
        results.append(result)

    return {
        "value": results,
        "@odata.context": "$metadata#FreightOrder",
    }


@app.get("/sap/opu/odata4/sap/api_freightorder/FreightOrder('{freight_order_id}')")
async def get_freight_order(freight_order_id: str):
    """Get a single freight order by ID."""
    order = FREIGHT_ORDERS.get(freight_order_id)
    if not order:
        raise HTTPException(status_code=404, detail=f"FreightOrder '{freight_order_id}' not found")

    result = {k: v for k, v in order.items() if not k.startswith("_")}
    return result


@app.patch("/sap/opu/odata4/sap/api_freightorder/FreightOrder('{freight_order_id}')")
async def update_freight_order(
    freight_order_id: str,
    request: Request,
    if_match: Optional[str] = Header(None),
    idempotency_key: Optional[str] = Header(None),
):
    """Update a freight order with ETag validation and idempotency.

    Headers:
        If-Match: ETag for optimistic concurrency
        Idempotency-Key: Unique key for replay protection

    Returns 412 if ETag doesn't match (concurrent modification).
    Returns cached response if idempotency key was already processed.
    """
    # --- Idempotency check ---
    if idempotency_key:
        cached = IDEMPOTENCY_CACHE.get(idempotency_key)
        if cached:
            logger.info("mock.idempotency_hit", key=idempotency_key, fo_id=freight_order_id)
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=cached["status_code"],
                content=cached["response_body"],
            )

    # --- Find the order ---
    order = FREIGHT_ORDERS.get(freight_order_id)
    if not order:
        raise HTTPException(status_code=404, detail=f"FreightOrder '{freight_order_id}' not found")

    # --- ETag validation ---
    if if_match:
        current_etag = order.get("_etag", "")
        if if_match != current_etag:
            logger.warning(
                "mock.etag_mismatch",
                fo_id=freight_order_id,
                expected=current_etag,
                received=if_match,
            )
            error_body = {
                "error": {
                    "code": "412",
                    "message": "Precondition Failed — ETag does not match. Resource was modified by another request.",
                    "target": f"FreightOrder('{freight_order_id}')",
                    "current_etag": current_etag,
                }
            }
            if idempotency_key:
                IDEMPOTENCY_CACHE[idempotency_key] = {
                    "status_code": 412,
                    "response_body": error_body,
                }
            raise HTTPException(status_code=412, detail="Precondition Failed — ETag mismatch")

    # --- Apply update ---
    body = await request.json()
    updated_fields = []
    for key, value in body.items():
        if key in order:
            order[key] = value
            updated_fields.append(key)

    order["_version"] = order.get("_version", 1) + 1
    order["ModifiedAt"] = datetime.now(timezone.utc).isoformat()
    order["_etag"] = _compute_etag(order)

    response_body = {
        "FreightOrderID": freight_order_id,
        "updated_fields": updated_fields,
        "_etag": order["_etag"],
        "_version": order["_version"],
        "status": "updated",
    }

    logger.info(
        "mock.order_updated",
        fo_id=freight_order_id,
        version=order["_version"],
        fields=updated_fields,
    )

    # --- Cache for idempotency ---
    if idempotency_key:
        IDEMPOTENCY_CACHE[idempotency_key] = {
            "status_code": 200,
            "response_body": response_body,
        }

    return response_body


@app.post("/sap/opu/odata4/sap/api_freightorder/FreightOrder")
async def create_freight_order(request: Request):
    """Create a new freight order (POST)."""
    body = await request.json()
    fo_id = body.get("FreightOrderID", f"FO-{uuid.uuid4().hex[:8].upper()}")

    if fo_id in FREIGHT_ORDERS:
        raise HTTPException(status_code=409, detail=f"FreightOrder '{fo_id}' already exists")

    record = _make_freight_order(
        fo_id=fo_id,
        source=body.get("SourceLocation", ""),
        destination=body.get("DestinationLocation", ""),
        vehicle=body.get("VehicleResource", ""),
        weight=float(body.get("GrossWeight", 0)),
        status=body.get("OverallProcessStatus", "CREATED"),
    )
    FREIGHT_ORDERS[fo_id] = record

    return {
        "FreightOrderID": fo_id,
        "_etag": record["_etag"],
        "status": "created",
    }


@app.get("/sap/opu/odata4/$metadata")
async def metadata():
    """OData v4 metadata document."""
    return {
        "edmx:Edmx": {
            "edmx:DataServices": {
                "Schema": {
                    "@Namespace": "API_FREIGHTORDER",
                    "EntityType": {
                        "@Name": "FreightOrderType",
                        "Key": {"PropertyRef": {"@Name": "FreightOrderID"}},
                        "Property": [
                            {"@Name": "FreightOrderID", "@Type": "Edm.String"},
                            {"@Name": "SourceLocation", "@Type": "Edm.String"},
                            {"@Name": "DestinationLocation", "@Type": "Edm.String"},
                            {"@Name": "VehicleResource", "@Type": "Edm.String"},
                            {"@Name": "GrossWeight", "@Type": "Edm.Decimal"},
                            {"@Name": "OverallProcessStatus", "@Type": "Edm.String"},
                            {"@Name": "CCRO_AllocationReference", "@Type": "Edm.String"},
                            {"@Name": "CCRO_ApproverID", "@Type": "Edm.String"},
                            {"@Name": "CCRO_PriorityScore", "@Type": "Edm.String"},
                        ],
                    },
                }
            }
        }
    }


@app.get("/api/idempotency-cache")
async def get_idempotency_cache():
    """Debug endpoint — view cached idempotency keys."""
    return {
        "cached_keys": len(IDEMPOTENCY_CACHE),
        "keys": list(IDEMPOTENCY_CACHE.keys()),
    }


@app.post("/api/reset")
async def reset():
    """Reset all freight orders to seed data."""
    FREIGHT_ORDERS.clear()
    for fo_id, src, dst, veh, wt in SEED_ORDERS:
        FREIGHT_ORDERS[fo_id] = _make_freight_order(fo_id, src, dst, veh, wt)
    IDEMPOTENCY_CACHE.clear()
    return {"status": "ok", "message": "Reset to seed data"}


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "freight_orders": len(FREIGHT_ORDERS),
        "idempotency_cache_size": len(IDEMPOTENCY_CACHE),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
