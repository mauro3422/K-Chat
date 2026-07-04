"""Tool: recall_memories - hybrid semantic search across stored memories."""

from __future__ import annotations

import logging
from typing import Any

from src.memory.retrieval.graph_context import format_graph_context
from src.utils.async_utils import run_in_thread

logger = logging.getLogger(__name__)

MEMORY_SOURCES = (
    "",
    "memory",
    "session",
    "session_summary",
    "transversal_synthesis",
    "memory_candidate",
    "memory_inbox",
)

DEFINITION: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "recall_memories",
        "description": (
            "Search your memory for anything related to a query. "
            "Uses hybrid search (semantic + keywords + entities) so it finds "
            "conceptually related memories even if the exact words do not match."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The query to search for in memory.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results (default: 5, max: 20).",
                    "default": 5,
                },
                "source": {
                    "type": "string",
                    "enum": list(MEMORY_SOURCES),
                    "description": (
                        "Filter by source: canon memory, sessions, summaries, "
                        "transversal synthesis, memory candidates, or empty for all."
                    ),
                    "default": "",
                },
                "min_score": {
                    "type": "number",
                    "description": "Minimum fusion score (0.0 to 1.0). Default: 0.2.",
                    "default": 0.2,
                },
                "include_graph_context": {
                    "type": "boolean",
                    "description": "Include related entity graph context when repositories are available.",
                    "default": False,
                },
                "known_entities": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Known entities already detected in the current turn.",
                    "default": [],
                },
            },
            "required": ["query"],
        },
    },
}


async def run(**kwargs) -> str:
    query = kwargs.get("query", "").strip()
    limit = min(kwargs.get("limit", 5), 20)
    source = kwargs.get("source", "")
    min_score = kwargs.get("min_score", 0.2)
    include_graph_context = kwargs.get("include_graph_context", False)
    known_entities = kwargs.get("known_entities") or []
    _repos = kwargs.get("_repos")

    if not query:
        return "[ERROR] query cannot be empty."

    try:
        retriever = _repos.memory.hybrid_retriever if _repos else None

        if retriever is None:
            return await _fallback_vector_search(query, limit, source, min_score)

        results = await retriever.search(
            query=query,
            top_k=limit * 2,
            source_filter=source or None,
        )
        filtered = [result for result in results if result.fusion_score >= min_score]

        if not filtered:
            return f'No se encontraron recuerdos relacionados a "{query}".'

        lines = [f'**Resultados para: "{query}"**\n']
        for index, result in enumerate(filtered[:limit], 1):
            lines.append(_format_hybrid_result(index, result))

        lines.append(
            f"\n_Encontrados {len(filtered)} resultados "
            f"(min. {int(min_score * 100)}% fusion)_"
        )
        if include_graph_context:
            graph_context = await format_graph_context(
                filtered[:limit],
                query=query,
                known_entities=known_entities,
                repos=_repos,
            )
            if graph_context:
                lines.extend(["", graph_context])

        return "\n".join(lines)

    except Exception as exc:
        logger.exception("recall_memories failed")
        return f"[ERROR] Failed to search memories: {exc}"


def _format_hybrid_result(index: int, result: Any) -> str:
    source_meta = _source_display(str(result.source or ""))
    signals = []
    if result.vector_score > 0.3:
        signals.append(f"vec{int(result.vector_score * 100)}%")
    if result.keyword_score > 0:
        signals.append(
            f"kw{int(result.keyword_score * 100) if result.keyword_score <= 1 else int(result.keyword_score)}"
        )
    if result.entity_score > 0:
        signals.append(f"ent{int(result.entity_score)}")
    sig_str = f" [{','.join(signals)}]" if signals else ""
    key_info = f"`{result.source_key}`" if result.source_key else ""
    return (
        f"{index}. {source_meta['marker']} [#{result.rank}{sig_str}] "
        f"{source_meta['label']} {source_meta['trust']} {key_info}\n"
        f"   _{result.text[:200]}_\n"
    )


def _source_display(source: str) -> dict[str, str]:
    labels = {
        "memory": ("[M]", "`canon`", "curated"),
        "session": ("[S]", "`session`", "episodic"),
        "session_summary": ("[SS]", "`session_summary`", "synthesis"),
        "transversal_synthesis": ("[T]", "`transversal_synthesis`", "cross-session"),
        "memory_candidate": ("[C]", "`memory_candidate`", "uncurated"),
        "memory_inbox": ("[I]", "`memory_inbox`", "temporary"),
    }
    marker, label, trust = labels.get(source, ("[?]", f"`{source or 'unknown'}`", "unknown"))
    return {"marker": marker, "label": label, "trust": trust}




async def _fallback_vector_search(query: str, limit: int, source: str, min_score: float) -> str:
    """Fallback to simple vector search when HybridRetriever is unavailable."""

    from src.memory.embeddings.service import generate_embedding
    from src.memory.memory_db_path import resolve_memory_db_path
    from src.memory.vector.store import VectorStore

    query_vec = await run_in_thread(generate_embedding, query)
    db_path = resolve_memory_db_path()
    store = VectorStore(db_path)
    try:
        results = store.search(
            query_embedding=query_vec,
            k=limit,
            source_filter=source if source else None,
        )
    finally:
        store.close()

    filtered = [result for result in results if result.score >= min_score]
    if not filtered:
        return f'No se encontraron recuerdos relacionados a "{query}".'

    lines = [f'**Resultados para: "{query}"**\n']
    for index, result in enumerate(filtered, 1):
        source_meta = _source_display(str(result.entry.source or ""))
        score_pct = int(result.score * 100)
        key_info = f"`{result.entry.source_key}`" if result.entry.source_key else ""
        lines.append(
            f"{index}. {source_meta['marker']} [{score_pct}%] "
            f"{source_meta['label']} {source_meta['trust']} {key_info}\n"
            f"   _{result.entry.text[:200]}_\n"
        )
    lines.append(
        f"\n_Encontrados {len(filtered)} resultados "
        f"(min. {int(min_score * 100)}% similitud)_"
    )
    return "\n".join(lines)
