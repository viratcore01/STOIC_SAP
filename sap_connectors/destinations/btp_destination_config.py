"""BTP Destination & Connectivity Service Configuration.

Routes all outbound calls to S/4HANA and SAP TM through BTP Destination
Service configured destinations, never hardcoded endpoints.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class BTPDestination:
    """Configuration for a BTP destination."""

    name: str
    url: str
    auth_type: str = "OAuth2SAMLBearerAssertion"
    proxy_type: str = "Internet"  # or "OnPremise" for Cloud Connector
    timeout_seconds: int = 30


# Pre-configured destinations per the architecture spec
DESTINATIONS = {
    "S4HANA_CCRO_DEST": BTPDestination(
        name="S4HANA_CCRO_DEST",
        url=os.getenv("CCRO_S4HANA_BASE_URL", ""),
        auth_type="OAuth2SAMLBearerAssertion",
    ),
    "TM_CCRO_DEST": BTPDestination(
        name="TM_CCRO_DEST",
        url=os.getenv("CCRO_TM_BASE_URL", ""),
        auth_type="OAuth2SAMLBearerAssertion",
    ),
}


class BTPDestinationService:
    """BTP Destination Service client for credential brokering."""

    def __init__(self):
        self.destinations = DESTINATIONS

    def get_destination(self, name: str) -> Optional[BTPDestination]:
        """Get a configured destination by name."""
        dest = self.destinations.get(name)
        if dest is None:
            logger.error("destination.not_found", name=name)
        return dest

    def get_s4hana_url(self) -> str:
        """Get the S/4HANA base URL from the configured destination."""
        dest = self.get_destination("S4HANA_CCRO_DEST")
        return dest.url if dest else ""

    def get_tm_url(self) -> str:
        """Get the SAP TM base URL from the configured destination."""
        dest = self.get_destination("TM_CCRO_DEST")
        return dest.url if dest else ""
