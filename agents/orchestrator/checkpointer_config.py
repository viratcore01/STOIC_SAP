"""LangGraph Checkpointer Configuration.

Short-term memory (per-thread): LangGraph checkpointer persists CCROGraphState
per disruption-episode thread_id, enabling pause/resume across the
human-approval boundary (which may take minutes to hours).
"""

from __future__ import annotations

import os
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)


class CheckpointerConfig:
    """Configuration for the LangGraph state checkpointer.

    Uses Redis-backed persistence for session/thread memory.
    Each disruption episode gets a unique thread_id.
    """

    def __init__(
        self,
        redis_url: Optional[str] = None,
        checkpoint_ttl_seconds: int = 86400,  # 24 hours
    ):
        self.redis_url = redis_url or os.getenv(
            "CCRO_REDIS_URL", "redis://localhost:6379"
        )
        self.checkpoint_ttl = checkpoint_ttl_seconds

    def get_checkpointer(self):
        """Create and return a LangGraph checkpointer instance.

        In production, uses Redis-backed AsyncPostgresSaver or
        RedisCheckpointSaver. For development, uses MemorySaver.
        """
        try:
            from langgraph.checkpoint.redis import AsyncRedisSaver

            checkpointer = AsyncRedisSaver.from_conn_string(self.redis_url)
            logger.info(
                "checkpointer.initialized",
                backend="redis",
                ttl=self.checkpoint_ttl,
            )
            return checkpointer
        except ImportError:
            logger.warning("checkpointer.redis_unavailable", fallback="memory")
            from langgraph.checkpoint.memory import MemorySaver

            return MemorySaver()
