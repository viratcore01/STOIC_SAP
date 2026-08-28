"""SAP S/4HANA OData v4 Client — Read-only batch, inventory, and demand queries.

This is a READ-ONLY client. It never writes to S/4HANA.
All writes are mediated through the SAP Integration Gateway.
"""

from __future__ import annotations

import os
from typing import Optional

import httpx
import structlog

logger = structlog.get_logger(__name__)


class S4HANAClient:
    """Read-only OData v4 client for SAP S/4HANA.

    Uses BTP Destination Service for credential brokering.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        auth_token: Optional[str] = None,
    ):
        self.base_url = base_url or os.getenv(
            "CCRO_S4HANA_BASE_URL",
            "https://s4hana.example.com/sap/opu/odata4/sap/api_batch_srv",
        )
        self.auth_token = auth_token or os.getenv("CCRO_S4HANA_AUTH_TOKEN", "")
        self.headers = {
            "Authorization": f"Bearer {self.auth_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def get_batch_expiry(
        self,
        material: str,
        plant: str,
    ) -> list[dict]:
        """Read batch expiry and inventory data.

        OData query:
        GET /BatchSet?$filter=Material eq '...' and Plant eq '...'
        &$select=Batch,MaterialExpirationDate,BatchQuantity,StorageLocation
        &$expand=to_ClinicDemand
        """
        url = f"{self.base_url}/BatchSet"
        params = {
            "$filter": f"Material eq '{material}' and Plant eq '{plant}'",
            "$select": "Batch,MaterialExpirationDate,BatchQuantity,StorageLocation",
            "$expand": "to_ClinicDemand",
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url, headers=self.headers, params=params, timeout=30.0
                )
                response.raise_for_status()
                data = response.json()
                return data.get("value", [])
        except httpx.HTTPError as e:
            logger.error("s4hana.read_failed", error=str(e), material=material)
            return []

    async def get_inventory_status(
        self,
        material: str,
        plant: str,
    ) -> list[dict]:
        """Read inventory status from EWM."""
        # Similar pattern to get_batch_expiry but targeting EWM endpoints
        url = f"{self.base_url}/InventorySet"
        params = {
            "$filter": f"Material eq '{material}' and Plant eq '{plant}'",
            "$select": "Material,Plant,StorageLocation,Quantity,ReservationStatus",
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url, headers=self.headers, params=params, timeout=30.0
                )
                response.raise_for_status()
                return response.json().get("value", [])
        except httpx.HTTPError as e:
            logger.error("s4hana.inventory_read_failed", error=str(e))
            return []
