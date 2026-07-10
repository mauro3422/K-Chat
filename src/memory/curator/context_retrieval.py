"""Relevant-memory retrieval for session curation prompts."""

from __future__ import annotations

import logging
import re
import sqlite3
import unicodedata
from pathlib import Path
from typing import Protocol


class CuratorContextRetrieverProtocol(Protocol):
    async def retrieve(self, query: str, *, session_id: str = "") -> str: ...


class HybridCuratorContextRetriever:
    """Retrieve canonical memories with hybrid search and lexical fallback."""

    def __init__(
        self,
        db_path: str,
        memory_path: str | Path,
        *,
        top_k: int = 6,
        max_chars: int = 5000,
    ) -> None:
        self._db_path = str(db_path)
        self._memory_path = str(memory_path)
        self._top_k = max(1, top_k)
        self._max_chars = max(500, max_chars)

    async def retrieve(self, query: str, *, session_id: str = "") -> str:
        if self._has_canonical_vectors():
            try:
                from src.memory.retrieval.hybrid_retriever import HybridRetriever
                from src.memory.retrieval.token_budget import TokenBudgetConfig

                retriever = HybridRetriever(
                    self._db_path,
                    token_budget=TokenBudgetConfig(
                        max_tokens=max(500, self._max_chars // 4),
                        per_result_tokens=200,
                        max_results=self._top_k,
                        truncate_to_chars=600,
                    ),
                )
                try:
                    results = await retriever.search(
                        query[:2000],
                        top_k=self._top_k,
                        source_filter="memory",
                        apply_budget=True,
                        session_id=session_id,
                    )
                    if results:
                        return retriever.format_for_prompt(results, query=query[:500])[: self._max_chars]
                finally:
                    retriever.close()
            except Exception:
                logging.getLogger(__name__).info(
                    "Curator hybrid context retrieval failed; using lexical fallback",
                    exc_info=True,
                )
        return self._lexical_fallback(query)

    def _has_canonical_vectors(self) -> bool:
        try:
            with sqlite3.connect(self._db_path) as conn:
                row = conn.execute(
                    "SELECT 1 FROM vec_meta WHERE source='memory' LIMIT 1"
                ).fetchone()
            return row is not None
        except (OSError, sqlite3.Error):
            return False

    def _lexical_fallback(self, query: str) -> str:
        from src.memory.operations._helpers import _parse_memory_md

        query_tokens = _tokens(query)
        if not query_tokens:
            return ""
        ranked: list[tuple[float, str, str]] = []
        for key, value in _parse_memory_md(self._memory_path).items():
            memory_tokens = _tokens(f"{key} {value}")
            overlap = query_tokens & memory_tokens
            if not overlap:
                continue
            score = len(overlap) / max(1, len(query_tokens))
            ranked.append((score, key, value))
        ranked.sort(key=lambda item: (-item[0], item[1]))

        lines = ["RELEVANT CANONICAL MEMORIES:"]
        for _, key, value in ranked[: self._top_k]:
            candidate = f"- {key}: {value}"
            if len("\n".join([*lines, candidate])) > self._max_chars:
                break
            lines.append(candidate)
        return "\n".join(lines) if len(lines) > 1 else ""


def _tokens(value: str) -> set[str]:
    from src.memory.analysis.corpus import STOP

    normalized = unicodedata.normalize("NFKD", value.casefold())
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    return {
        token
        for token in re.findall(r"[a-z0-9]+", normalized)
        if len(token) >= 3 and token not in STOP
    }
