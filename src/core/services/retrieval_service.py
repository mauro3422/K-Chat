"""RetrievalService — encapsulates auto-retrieval logic for orchestrator."""

from __future__ import annotations

import hashlib
import logging
from collections import OrderedDict
from typing import Any

from src.memory.retrieval.token_budget import format_memories_for_prompt
from src.memory.retrieval.receipts import build_memory_receipt, format_receipt_ledger

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

    def __init__(
        self,
        config: Any | None = None,
        retrieval_service: Any | None = None,
        entity_graph_repo: Any | None = None,
        receipt_repo: Any | None = None,
        recall_event_root: str | None = None,
        record_recall_events: bool = True,
    ):
        self._throttle: OrderedDict[str, int] = OrderedDict()
        self._retrieval_cache: OrderedDict[str, tuple[str | None, bool]] = OrderedDict()
        self._retrieval_service = retrieval_service
        self._entity_graph_repo = entity_graph_repo
        self._receipt_repo = receipt_repo
        self._config = config
        self._recall_event_root = recall_event_root
        self._record_recall_events = record_recall_events

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
        source_filter: str | None = "session",
        include_graph_context: bool = False,
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
                source_filter=source_filter,
                session_id=session_id or '', # exclude current session's own exchanges
            )

            if hasattr(retriever, 'was_reranker_degraded') and retriever.was_reranker_degraded:
                degraded = True

            logger.info("Auto-retrieval: %d results for session %s", len(results), (session_id or "default")[:12])

            if results:
                receipts: list[dict[str, Any]] = []
                if self._receipt_repo is not None and session_id:
                    receipts = [
                        build_memory_receipt(session_id, result, message_user[:1000])
                        for result in results
                    ]
                    try:
                        await self._receipt_repo.upsert_many(session_id, receipts)
                    except Exception:
                        logger.info(
                            "Memory receipt persistence unavailable (non-fatal)",
                            exc_info=True,
                        )
                        receipts = []

                receipt_by_rowid = {
                    receipt.get("vec_rowid"): receipt for receipt in receipts
                }
                dicts = []
                for result in results:
                    payload = result.to_dict()
                    receipt = receipt_by_rowid.get(getattr(result, "rowid", None))
                    if receipt is not None:
                        payload["receipt_id"] = receipt["receipt_id"]
                    dicts.append(payload)
                memory_block = format_memories_for_prompt(dicts, query=message_user[:1000])
                if include_graph_context:
                    graph_context = await self._active_recall_graph_context(
                        results,
                        query=message_user[:1000],
                    )
                    if graph_context:
                        memory_block = f"{memory_block}\n\n{graph_context}"
                ledger = await self._receipt_ledger(
                    session_id,
                    exclude_ids={receipt["receipt_id"] for receipt in receipts},
                )
                if ledger:
                    memory_block = f"{memory_block}\n\n{ledger}"
                logger.info("Auto-retrieval: memory block %d chars", len(memory_block))
                return memory_block, degraded
            ledger = await self._receipt_ledger(session_id)
            if ledger:
                return ledger, degraded
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

    async def _receipt_ledger(
        self,
        session_id: str | None,
        *,
        exclude_ids: set[str] | None = None,
    ) -> str:
        if self._receipt_repo is None or not session_id:
            return ""
        try:
            recent = await self._receipt_repo.list_recent(
                session_id,
                limit=20,
                exclude_ids=exclude_ids,
            )
            total = await self._receipt_repo.count(session_id)
            return format_receipt_ledger(recent, total_count=total)
        except Exception:
            logger.info("Memory receipt ledger unavailable (non-fatal)", exc_info=True)
            return ""

    async def _active_recall_graph_context(self, results: list[Any], *, query: str) -> str:
        """Append curated graph context for explicit recall prompt injection."""

        repo = self._entity_graph_repo
        if repo is None:
            try:
                from src.memory.repos_memory.entity_repo import EntityRepository

                repo = EntityRepository()
            except Exception:
                logger.info("Active recall graph repo unavailable", exc_info=True)
                return ""
        try:
            from src.memory.retrieval.graph_context import format_graph_context

            return await format_graph_context(
                results,
                query=query,
                known_entities=[],
                repo=repo,
            )
        except Exception:
            logger.info("Active recall graph context failed (non-fatal)", exc_info=True)
            return ""

    def _active_recall_policy(self, message_user: str) -> Any:
        """Return the active recall policy for a user message."""

        try:
            from src.memory.curator.workbench import should_recall

            return should_recall(message_user, known_entities=[])
        except Exception:
            logger.info("Active recall policy failed (non-fatal)", exc_info=True)

            class _FallbackPolicy:
                should_recall = False
                reason = "policy_unavailable"

            return _FallbackPolicy()

    def _record_recall_event(
        self,
        message_user: str,
        session_id: str | None,
        trigger: str,
        memory_block: str | None,
        degraded: bool,
    ) -> None:
        """Persist a lightweight active-recall event for nightly curation."""

        if not self._record_recall_events:
            return
        try:
            from src.memory.curator.recall_events import append_recall_event

            append_recall_event(
                {
                    "query": message_user[:1000],
                    "intent": "auto",
                    "trigger": trigger,
                    "session_id": session_id or "",
                    "source": "retrieval_service",
                    "status": "recalled" if memory_block else "no_results",
                    "degraded": degraded,
                    "result_excerpt": (memory_block or "")[:500],
                },
                root=self._recall_event_root,
            )
        except Exception:
            logger.info("Failed to write active recall event (non-fatal)", exc_info=True)

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

        policy = self._active_recall_policy(message_user)
        active_recall = bool(getattr(policy, "should_recall", False))
        if not active_recall and not self._check_throttle(session_id or "default", message_user):
            ledger = await self._receipt_ledger(session_id)
            return (ledger or None), False

        source_filter = None if active_recall else "session"
        top_k = 10 if active_recall else 8

        # Cache check: avoid re-running automatic retrieval on retries for the same message.
        # Explicit active recall should stay fresh and keep producing curation events.
        cache_key = ""
        if not active_recall:
            message_hash = hashlib.md5(message_user.strip().encode()).hexdigest()
            cache_key = f"{session_id or 'default'}:auto:{message_hash}"
        if cache_key and cache_key in self._retrieval_cache:
            logger.info("Auto-retrieval cache hit for session %s", (session_id or "default")[:12])
            self._retrieval_cache.move_to_end(cache_key)
            memory_block, degraded = self._retrieval_cache[cache_key]
        else:
            memory_block, degraded = await self.retrieve(
                message_user,
                session_id,
                db_path,
                top_k=top_k,
                source_filter=source_filter,
                include_graph_context=active_recall,
            )
            if cache_key:
                self._retrieval_cache[cache_key] = (memory_block, degraded)
                self._retrieval_cache.move_to_end(cache_key)
                if len(self._retrieval_cache) > self.MAX_CACHE_SIZE:
                    for _ in range(len(self._retrieval_cache) - self.MAX_CACHE_SIZE):
                        self._retrieval_cache.popitem(last=False)

        if active_recall:
            self._record_recall_event(
                message_user,
                session_id,
                getattr(policy, "reason", "active_recall"),
                memory_block,
                degraded,
            )
        return memory_block, degraded
