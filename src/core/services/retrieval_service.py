"""RetrievalService — encapsulates auto-retrieval logic for orchestrator."""

from __future__ import annotations

import hashlib
import logging
from collections import OrderedDict
from typing import Any

from src.memory.retrieval.token_budget import format_memories_for_prompt

logger = logging.getLogger(__name__)


class RetrievalService:
    """Service that handles automatic memory retrieval for chat turns.

    Encapsulates:
    - Auto-retrieval enable/disable check
    - Per-session throttling (rate-limit expensive searches)
    - HybridRetriever creation and search
    - Memory formatting for prompt injection
    - Short-lived cache to avoid re-running retrieval on retries
    """

    RETRIEVAL_INTERVAL = 1  # inject on every user message
    MAX_SESSIONS = 1000
    MAX_CACHE_SIZE = 50  # LRU cache for retrieval results

    def __init__(self, config: Any | None = None, retrieval_service: Any | None = None):
        self._throttle: OrderedDict[str, int] = OrderedDict()
        self._retrieval_cache: OrderedDict[str, tuple[str | None, bool]] = OrderedDict()
        self._retrieval_service = retrieval_service
        self._config = config

    def _check_throttle(self, session_id: str, message_user: str) -> bool:
        """Check if auto-retrieval should run for this session/turn.

        Returns True if retrieval should proceed, False if throttled.
        """
        if not message_user or not message_user.strip():
            logger.info("Auto-retrieval skipped: empty message")
            return False
        if len(message_user.strip()) < 3:
            logger.info("Auto-retrieval skipped: message too short (%d chars)", len(message_user.strip()))
            return False

        sid = session_id or "default"
        current = self._throttle.get(sid, 0)
        self._throttle[sid] = current + 1
        self._throttle.move_to_end(sid)

        # LRU eviction
        if len(self._throttle) > self.MAX_SESSIONS:
            for _ in range(len(self._throttle) - self.MAX_SESSIONS):
                self._throttle.popitem(last=False)

        if current > 0 and current % self.RETRIEVAL_INTERVAL != 0:
            logger.info("Auto-retrieval throttled for session %s (turn %d)", sid[:12], current + 1)
            return False

        return True

    async def retrieve(
        self,
        message_user: str,
        session_id: str | None = None,
        db_path: str | None = None,
        top_k: int = 8,
    ) -> tuple[str | None, bool]:
        """Run auto-retrieval and return (memory_block, degraded) tuple.

        Returns:
            Tuple of (formatted memory block or None, whether the reranker was degraded).
        """
        retriever = None
        degraded = False
        try:
            if self._retrieval_service is not None:
                retriever = self._retrieval_service
            elif db_path:
                from src.memory.retrieval.hybrid_retriever import HybridRetriever
                retriever = HybridRetriever(db_path)
            else:
                from src.memory.memory_db_path import resolve_memory_db_path
                from src.memory.retrieval.hybrid_retriever import HybridRetriever
                retriever = HybridRetriever(resolve_memory_db_path())

            if retriever is None:
                return None, False

            results = await retriever.search(
                message_user[:1000],
                top_k=top_k,
                apply_budget=True,
                source_filter='session',     # skip source='memory' (already in MEMORY.md)
                session_id=session_id or '', # exclude current session's own exchanges
            )

            if hasattr(retriever, 'was_reranker_degraded') and retriever.was_reranker_degraded:
                degraded = True

            logger.info("Auto-retrieval: %d results for session %s", len(results), (session_id or "default")[:12])

            if results:
                dicts = [r.to_dict() for r in results]
                memory_block = format_memories_for_prompt(dicts, query=message_user[:1000])
                logger.info("Auto-retrieval: memory block %d chars", len(memory_block))
                return memory_block, degraded
        except Exception as e:
            logger.info("Auto-retrieval failed (non-fatal): %s", e)
            degraded = True
        finally:
            if retriever is not None and hasattr(retriever, 'close'):
                try:
                    retriever.close()
                except Exception:
                    logger.warning("Failed to close retriever", exc_info=True)

        return None, degraded

    async def retrieve_if_allowed(
        self,
        message_user: str,
        session_id: str | None = None,
        config: Any | None = None,
        db_path: str | None = None,
    ) -> tuple[str | None, bool]:
        """Check config + throttle, then retrieve if allowed.

        Returns:
            Tuple of (memory_block or None, whether reranker was degraded).
        """
        if config is None:
            if self._config is not None:
                config = self._config
            else:
                from src._config import resolve_config
                config = resolve_config()

        if hasattr(config, 'auto_retrieval_enabled') and not config.auto_retrieval_enabled:
            logger.info("Auto-retrieval disabled via config")
            return None, False

        if not self._check_throttle(session_id or "default", message_user):
            return None, False

        # Cache check: avoid re-running retrieval on retries for the same message
        message_hash = hashlib.md5(message_user.strip().encode()).hexdigest()
        cache_key = f"{session_id or 'default'}:{message_hash}"
        if cache_key in self._retrieval_cache:
            logger.info("Auto-retrieval cache hit for session %s", (session_id or "default")[:12])
            self._retrieval_cache.move_to_end(cache_key)
            return self._retrieval_cache[cache_key]

        result = await self.retrieve(message_user, session_id, db_path)

        # Cache the result
        self._retrieval_cache[cache_key] = result
        self._retrieval_cache.move_to_end(cache_key)
        if len(self._retrieval_cache) > self.MAX_CACHE_SIZE:
            for _ in range(len(self._retrieval_cache) - self.MAX_CACHE_SIZE):
                self._retrieval_cache.popitem(last=False)

        return result
