"""Tool: recall_memories — hybrid semantic search across all stored memories.

Uses 3 signals fused: vector similarity + keyword matching + entity graph.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

DEFINITION: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "recall_memories",
        "description": (
            "Search your memory for anything related to a query. "
            "Uses hybrid search (semantic + keywords + entities) so it finds "
            "conceptually related memories even if the exact words don't match."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The query to search for in memory."
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results (default: 5, max: 20).",
                    "default": 5
                },
                "source": {
                    "type": "string",
                    "enum": ["", "memory", "session"],
                    "description": "Filter by source: 'memory', 'session', or empty for both (default: '').",
                    "default": ""
                },
                "min_score": {
                    "type": "number",
                    "description": "Minimum fusion score (0.0 to 1.0). Default: 0.2.",
                    "default": 0.2
                }
            },
            "required": ["query"]
        }
    }
}


async def run(**kwargs) -> str:
    query = kwargs.get("query", "").strip()
    limit = min(kwargs.get("limit", 5), 20)
    source = kwargs.get("source", "")
    min_score = kwargs.get("min_score", 0.2)
    _repos = kwargs.get("_repos")

    if not query:
        return "[ERROR] query cannot be empty."

    try:
        # Use HybridRetriever via DI
        retriever = _repos.memory.hybrid_retriever if _repos else None

        if retriever is None:
            # Fallback: simple vector search
            return await _fallback_vector_search(query, limit, source, min_score)

        results = await retriever.search(
            query=query,
            top_k=limit * 2,
            source_filter=source or None,
        )

        # Filter by min_score
        filtered = [r for r in results if r.fusion_score >= min_score]

        if not filtered:
            return f"No se encontraron recuerdos relacionados a \"{query}\"."

        lines = [f"📖 **Resultados para: \"{query}\"**\n"]
        for i, r in enumerate(filtered[:limit], 1):
            source_icon = "🧠" if r.source == "memory" else "💬"
            rank_display = r.rank

            # Show signal breakdown
            signals = []
            if r.vector_score > 0.3:
                signals.append(f"vec{int(r.vector_score*100)}%")
            if r.keyword_score > 0:
                signals.append(f"kw{int(r.keyword_score*100) if r.keyword_score <= 1 else int(r.keyword_score)}")
            if r.entity_score > 0:
                signals.append(f"ent{int(r.entity_score)}")
            sig_str = f" [{','.join(signals)}]" if signals else ""

            text_preview = r.text[:200]
            key_info = f"`{r.source_key}`" if r.source_key else ""
            lines.append(
                f"{i}. {source_icon} [#{rank_display}{sig_str}] {key_info}\n"
                f"   _{text_preview}_\n"
            )

        lines.append(f"\n_Encontrados {len(filtered)} resultados (mín. {int(min_score*100)}% fusión)_")
        return "\n".join(lines)

    except Exception as e:
        logger.exception("recall_memories failed")
        return f"[ERROR] Failed to search memories: {e}"


async def _fallback_vector_search(query: str, limit: int, source: str, min_score: float) -> str:
    """Fallback to simple vector search when HybridRetriever is unavailable."""
    import asyncio
    from src.memory.embeddings.service import generate_embedding
    from src.memory.memory_db_path import resolve_memory_db_path
    from src.memory.vector.store import VectorStore

    query_vec = await asyncio.to_thread(generate_embedding, query)
    db_path = resolve_memory_db_path()
    store = VectorStore(db_path)
    try:
        source_filter = source if source else None
        results = store.search(
            query_embedding=query_vec,
            k=limit,
            source_filter=source_filter,
        )
    finally:
        store.close()

    filtered = [r for r in results if r.score >= min_score]
    if not filtered:
        return f"No se encontraron recuerdos relacionados a \"{query}\"."

    lines = [f"📖 **Resultados para: \"{query}\"**\n"]
    for i, r in enumerate(filtered, 1):
        source_icon = "🧠" if r.entry.source == "memory" else "💬"
        score_pct = int(r.score * 100)
        text_preview = r.entry.text[:200]
        key_info = f"`{r.entry.source_key}`" if r.entry.source_key else ""
        lines.append(
            f"{i}. {source_icon} [{score_pct}%] {key_info}\n"
            f"   _{text_preview}_\n"
        )
    lines.append(f"\n_Encontrados {len(filtered)} resultados (mín. {int(min_score*100)}% similitud)_")
    return "\n".join(lines)
