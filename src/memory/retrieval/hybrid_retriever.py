"""HybridRetriever — orchestrates vector + keyword + entity search with fusion."""

from __future__ import annotations
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from src.memory.retrieval.fusion import FusionConfig, fuse, normalize_scores
from src.memory.retrieval.keyword_search import keyword_search
from src.memory.retrieval.entity_search import entity_search
from src.memory.retrieval.token_budget import (
    TokenBudgetConfig,
    select_by_budget,
    format_memories_for_prompt,
)
from src.memory.retrieval.hydrator import hydrate_results
from src.memory.retrieval.tracker import track_retrieval
from src.utils.async_utils import run_in_thread

logger = logging.getLogger(__name__)


@dataclass
class HybridResult:
    """A single result from hybrid retrieval."""
    rowid: int
    text: str
    source: str = ""
    source_key: str = ""
    relevance_score: float = 0.5
    vector_score: float = 0.0
    keyword_score: float = 0.0
    entity_score: float = 0.0
    fusion_score: float = 0.0
    rank: int = 0
    query_count: int = 0
    last_accessed: str = ""
    entities: list[str] = field(default_factory=list)

    @property
    def score(self) -> float:
        """Alias for fusion_score for backward compatibility."""
        return self.fusion_score

    @score.setter
    def score(self, value: float) -> None:
        self.fusion_score = value

    def to_dict(self) -> dict[str, Any]:
        return {
            "rowid": self.rowid,
            "text": self.text,
            "source": self.source,
            "source_key": self.source_key,
            "score": self.fusion_score,
            "entities": self.entities,
        }


class HybridRetriever:
    """Orchestrates 3 retrieval signals and fuses them.

    Usage:
        retriever = HybridRetriever(db_path)
        results = await retriever.search("query about something", top_k=10)
    """

    def __init__(
        self,
        db_path: str,
        fusion_config: Optional[FusionConfig] = None,
        token_budget: Optional[TokenBudgetConfig] = None,
    ):
        self._db_path = db_path
        self._fusion_config = fusion_config or FusionConfig()
        self._token_budget = token_budget or TokenBudgetConfig()
        self._reranker_degraded = False

    @property
    def was_reranker_degraded(self) -> bool:
        return self._reranker_degraded

    async def search(
        self,
        query: str,
        top_k: int = 10,
        source_filter: Optional[str] = None,
        apply_budget: bool = False,
        session_id: str = "",
    ) -> list[HybridResult]:
        """Run hybrid search with all 3 signals fused.

        Args:
            query: User query string.
            top_k: Number of results to return after fusion.
            source_filter: Optional 'memory' or 'session'.
            apply_budget: If True, apply token budget to results.

        Returns:
            List of HybridResult sorted by fusion score descending.
        """
        self._reranker_degraded = False  # Reset per search

        prefetch_k = max(top_k * 3, 30)  # Fetch more candidates, then fuse and cut

        exclude_key = session_id or None  # None = no exclusion

        # Run all 3 searches in parallel via shared thread pool
        vec_task = run_in_thread(
            self._vector_search, query, prefetch_k, source_filter, exclude_key
        )
        kw_task = run_in_thread(
            keyword_search, query, self._db_path, prefetch_k, source_filter, exclude_key
        )
        ent_task = run_in_thread(
            entity_search, query, self._db_path, prefetch_k, source_filter, exclude_key
        )

        vec_results, kw_results, ent_results = await asyncio.gather(
            vec_task, kw_task, ent_task,
            return_exceptions=True,
        )

        # Handle exceptions gracefully: if one search method fails (e.g. missing table),
        # log it and treat as empty results so remaining methods still contribute.
        _raw_vec = []
        _raw_kw = []
        _raw_ent = []
        if isinstance(vec_results, BaseException):
            logger.warning("Vector search failed (non-fatal): %s", vec_results)
        else:
            _raw_vec = vec_results
        if isinstance(kw_results, BaseException):
            logger.warning("Keyword search failed (non-fatal): %s", kw_results)
        else:
            _raw_kw = kw_results
        if isinstance(ent_results, BaseException):
            logger.warning("Entity search failed (non-fatal): %s", ent_results)
        else:
            _raw_ent = ent_results

        # Fuse: RRF on ranked lists
        ranked_lists = [
            [r[0] for r in _raw_vec],   # rowids sorted by vector similarity
            [r[0] for r in _raw_kw],     # rowids sorted by keyword score
            [r[0] for r in _raw_ent],    # rowids sorted by entity score
        ]

        # Also normalize scores for weighted_sum mode
        scored_lists = [
            normalize_scores(_raw_vec) if _raw_vec else [],
            normalize_scores(_raw_kw) if _raw_kw else [],
            normalize_scores(_raw_ent) if _raw_ent else [],
        ]

        fused = fuse(ranked_lists, scored_lists, self._fusion_config)
        fused = fused[:top_k]  # Cut to top_k after fusion

        # Filter by minimum score threshold from fusion config
        fused = [(rowid, score) for rowid, score in fused if score >= self._fusion_config.min_score]

        # Hydrate: load text and metadata from vec_meta
        import sqlite3
        conn = sqlite3.connect(self._db_path)
        try:
            hydrated_dicts = hydrate_results(fused, conn, top_k)
        finally:
            conn.close()

        vec_dict = dict(vec_results)
        kw_dict = dict(kw_results)
        ent_dict = dict(ent_results)

        hydrated_map = {d["rowid"]: d for d in hydrated_dicts}

        results = []
        for rank, (rowid, fusion_score) in enumerate(fused, 1):
            hd = hydrated_map.get(rowid)
            if hd is None:
                continue
            results.append(HybridResult(
                rowid=rowid,
                text=hd["text"],
                source=hd["source"],
                source_key=hd["source_key"],
                vector_score=vec_dict.get(rowid, 0.0),
                keyword_score=kw_dict.get(rowid, 0.0),
                entity_score=ent_dict.get(rowid, 0.0),
                fusion_score=fusion_score,
                rank=rank,
            ))

        # ── Cross-encoder re-ranking ──────────────────────────────
        if results and query:
            dicts = [r.to_dict() for r in results]
            try:
                from src.memory.retrieval.reranker import rerank
                reranked_dicts = rerank(query, dicts, top_k=top_k)
                reranked_ids = {d["rowid"] for d in reranked_dicts}
                results = [r for r in results if r.rowid in reranked_ids]
                score_map = {d["rowid"]: d["score"] for d in reranked_dicts}
                for r in results:
                    r.fusion_score = score_map.get(r.rowid, r.fusion_score)
                results.sort(key=lambda x: x.fusion_score, reverse=True)
            except Exception as e:
                logger.warning("Reranker failed (non-fatal), using original results: %s", e)
                self._reranker_degraded = True
                # Fall through with original results

        # Apply token budget if requested
        if apply_budget:
            dicts = [r.to_dict() for r in results]
            selected_dicts = select_by_budget(dicts, self._token_budget)
            selected_ids = {d["rowid"] for d in selected_dicts}
            results = [r for r in results if r.rowid in selected_ids]

        # Log results for debugging quality
        if results:
            logger.info("Search results for query %r: %d results", query[:60], len(results))
            for r in results[:5]:
                logger.info("  [%d] source=%s key=%s fusion=%.3f vec=%.3f kw=%.3f ent=%.3f",
                            r.rowid, r.source, r.source_key, r.fusion_score,
                            r.vector_score, r.keyword_score, r.entity_score)
        else:
            logger.info("Search returned 0 results for query %r", query[:60])

        track_retrieval(self._db_path, query, len(results), "hybrid", source_filter)
        return results

    def _vector_search(
        self,
        query: str,
        top_k: int,
        source_filter: Optional[str] = None,
        exclude_source_key: Optional[str] = None,
    ) -> list[tuple[int, float]]:
        """Vector search using a local VectorStore (thread-safe).

        Creates a fresh VectorStore inside the thread to avoid SQLite
        thread-safety issues with shared connections.

        Returns [(rowid, similarity_score)] sorted by similarity descending.
        """
        from src.memory.embeddings.service import generate_embedding
        from src.memory.vector.store import VectorStore

        vec = generate_embedding(query)
        # Create LOCAL store (not shared self._vector_store) for thread safety
        local_store = VectorStore(self._db_path)
        try:
            sf = source_filter if source_filter else None
            results = local_store.search(
                vec, k=top_k, source_filter=sf,
                exclude_source_key=exclude_source_key
            )
            return [(r.entry.id, 1.0 - r.distance) for r in results]
        finally:
            local_store.close()

    def format_for_prompt(
        self,
        results: list[HybridResult],
        query: str = "",
    ) -> str:
        """Format results as a system prompt block."""
        dicts = [r.to_dict() for r in results]
        return format_memories_for_prompt(dicts, query=query)

    def close(self):
        """Close the underlying vector store connection."""
        # No-op: each search creates its own local VectorStore for thread safety
