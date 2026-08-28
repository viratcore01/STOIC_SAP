"""Idempotency Ledger — Redis-backed replay protection for SAP writes.

Every SAP write carries a caller-generated Idempotency-Key. This ledger
maintains a short-TTL cache (24h) to detect and safely no-op replayed writes.
"""

from __future__ import annotations

import os
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)


class IdempotencyLedger:
    """Redis-backed idempotency ledger for SAP write replay protection.

    In production, this uses Redis. For development, uses an in-memory dict.
    """

    def __init__(
        self,
        redis_url: Optional[str] = None,
        ttl_seconds: int = 86400,  # 24 hours
    ):
        self.redis_url = redis_url or os.getenv("CCRO_REDIS_URL", "")
        self.ttl_seconds = ttl_seconds
        self._memory_store: dict[str, str] = {}  # fallback for development

    async def check_and_claim(self, idempotency_key: str) -> tuple[bool, Optional[str]]:
        """Check if a write has already been executed.

        Returns:
            (is_new, previous_response): True if this is a new write,
            False + the previous response if it's a replay.
        """
        # Try Redis first
        if self.redis_url:
            try:
                import redis.asyncio as aioredis

                r = aioredis.from_url(self.redis_url)
                existing = await r.get(f"idempotency:{idempotency_key}")
                if existing:
                    return False, existing.decode()
                await r.set(
                    f"idempotency:{idempotency_key}",
                    "claimed",
                    ex=self.ttl_seconds,
                )
                return True, None
            except Exception as e:
                logger.warning("idempotency.redis_fallback", error=str(e))

        # Fallback to in-memory
        if idempotency_key in self._memory_store:
            return False, self._memory_store[idempotency_key]
        self._memory_store[idempotency_key] = "claimed"
        return True, None

    async def record_response(
        self, idempotency_key: str, response: str
    ) -> None:
        """Record the SAP response for a completed write."""
        if self.redis_url:
            try:
                import redis.asyncio as aioredis

                r = aioredis.from_url(self.redis_url)
                await r.set(
                    f"idempotency:{idempotency_key}",
                    response,
                    ex=self.ttl_seconds,
                )
                return
            except Exception:
                pass

        self._memory_store[idempotency_key] = response
