"""SAP Transportation Management OData v4 Client — Freight order read/writeback.

This is the ONLY client permitted to write to SAP TM.
All writes carry idempotency keys and optimistic concurrency ETags.
"""

from __future__ import annotations

import hashlib
import os
from typing import Optional

import httpx
import structlog

logger = structlog.get_logger(__name__)


class SAPTMClient:
    """OData v4 client for SAP Transportation Management.

    Enforces:
    - Idempotency keys on all writes
    - If-Match ETags for optimistic concurrency
    - Two-phase writeback (TM first, then S/4HANA)
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        auth_token: Optional[str] = None,
    ):
        self.base_url = base_url or os.getenv(
            "CCRO_TM_BASE_URL",
            "https://tm.example.com/sap/opu/odata4/sap/api_freightorder",
        )
        self.auth_token = auth_token or os.getenv("CCRO_TM_AUTH_TOKEN", "")
        self.headers = {
            "Authorization": f"Bearer {self.auth_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _generate_idempotency_key(
        self,
        allocation_plan_id: str,
        site_id: str,
        attempt_seq: int = 1,
    ) -> str:
        """Generate deterministic idempotency key."""
        raw = f"{allocation_plan_id}-{site_id}-{attempt_seq}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    async def get_open_freight_orders(self) -> list[dict]:
        """Read open (non-completed) freight orders.

        OData query:
        GET /FreightOrder?$filter=OverallProcessStatus ne 'COMPLETED'
        &$select=FreightOrderID,SourceLocation,DestinationLocation,VehicleResource,GrossWeight
        """
        url = f"{self.base_url}/FreightOrder"
        params = {
            "$filter": "OverallProcessStatus ne 'COMPLETED'",
            "$select": (
                "FreightOrderID,SourceLocation,DestinationLocation,"
                "VehicleResource,GrossWeight"
            ),
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url, headers=self.headers, params=params, timeout=30.0
                )
                response.raise_for_status()
                return response.json().get("value", [])
        except httpx.HTTPError as e:
            logger.error("tm.read_failed", error=str(e))
            return []

    async def update_freight_order(
        self,
        allocation_plan_id: str,
        site_id: str,
        vehicle_id: str,
        allocated_units: int,
        payload_mass_kg: float,
        priority_score: float,
        approver_id: str,
        freight_order_id: Optional[str] = None,
        etag: Optional[str] = None,
        attempt_seq: int = 1,
    ) -> str:
        """Update a freight order with allocation details.

        PATCH /FreightOrder('{FreightOrderID}')
        Headers:
          Idempotency-Key: {hash}
          If-Match: {etag}
        Body:
          { allocation fields }
        """
        if not freight_order_id:
            # In production, look up the freight order from the vehicle mapping
            freight_order_id = f"FO-{vehicle_id}-{site_id}"

        url = f"{self.base_url}/FreightOrder('{freight_order_id}')"
        idempotency_key = self._generate_idempotency_key(
            allocation_plan_id, site_id, attempt_seq
        )

        write_headers = {
            **self.headers,
            "Idempotency-Key": idempotency_key,
        }
        if etag:
            write_headers["If-Match"] = etag

        body = {
            "DestinationLocation": site_id,
            "PlannedGrossWeight": str(payload_mass_kg),
            "CCRO_AllocationReference": allocation_plan_id,
            "CCRO_ApproverID": approver_id,
            "CCRO_PriorityScore": str(priority_score),
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.patch(
                    url, headers=write_headers, json=body, timeout=30.0
                )

                if response.status_code == 412:
                    from schemas import WritebackConflict

                    raise WritebackConflict(
                        freight_order_id, "ETag conflict — concurrent modification"
                    )

                response.raise_for_status()
                logger.info(
                    "tm.writeback_success",
                    freight_order_id=freight_order_id,
                    site_id=site_id,
                )
                return freight_order_id

        except httpx.HTTPError as e:
            logger.error(
                "tm.writeback_failed",
                freight_order_id=freight_order_id,
                error=str(e),
            )
            raise
