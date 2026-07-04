"""Tool: remember - active recall over memory with curator link hints."""

from __future__ import annotations

import logging
from typing import Any

from src.memory.curator.workbench import (
    LinkSignals,
    recommend_link_relation,
    should_recall,
)

logger = logging.getLogger(__name__)

DEFINITION: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "remember",
        "description": (
            "Actively recall related memories for the current chat. "
            "Use it when the user asks if you remember something, when a known "
            "entity appears with a memory/planning signal, or when you need to "
            "link a new candidate to prior memories."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What to remember or connect.",
                },
                "intent": {
                    "type": "string",
                    "enum": ["auto", "recall", "link", "verify"],
                    "description": (
                        "auto only searches when policy triggers; recall/link/verify "
                        "perform the search and add intent-specific guidance."
                    ),
                    "default": "recall",
                },
                "known_entities": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Known entities detected in the message.",
                    "default": [],
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum recall results (default: 5, max: 20).",
                    "default": 5,
                },
                "source": {
                    "type": "string",
                    "enum": [
                        "",
                        "memory",
                        "session",
                        "session_summary",
                        "transversal_synthesis",
                        "memory_candidate",
                        "memory_inbox",
                    ],
                    "description": "Filter by memory source, or empty for all layers.",
                    "default": "",
                },
                "min_score": {
                    "type": "number",
                    "description": "Minimum recall score.",
                    "default": 0.2,
                },
                "semantic_score": {
                    "type": "number",
                    "description": "Optional semantic similarity signal for link recommendation.",
                    "default": 0.0,
                },
                "entity_overlap": {
                    "type": "number",
                    "description": "Optional entity overlap signal for link recommendation.",
                    "default": 0.0,
                },
                "keyword_overlap": {
                    "type": "number",
                    "description": "Optional keyword overlap signal for link recommendation.",
                    "default": 0.0,
                },
                "contradiction_score": {
                    "type": "number",
                    "description": "Optional contradiction signal for link recommendation.",
                    "default": 0.0,
                },
                "record_event": {
                    "type": "boolean",
                    "description": "Persist a JSONL recall event for later curation.",
                    "default": True,
                },
            },
            "required": ["query"],
        },
    },
}


async def run(**kwargs) -> str:
    query = kwargs.get("query", "").strip()
    intent = kwargs.get("intent", "recall")
    known_entities = kwargs.get("known_entities") or []
    limit = min(kwargs.get("limit", 5), 20)
    source = kwargs.get("source", "")
    min_score = kwargs.get("min_score", 0.2)
    record_event = kwargs.get("record_event", True)
    _repos = kwargs.get("_repos")
    _root = kwargs.get("_root")

    if not query:
        return "[ERROR] query cannot be empty."

    try:
        policy = should_recall(query, known_entities=known_entities)
        event: dict[str, Any] = {
            "query": query,
            "intent": intent,
            "trigger": policy.reason,
            "known_entities": list(known_entities),
            "source": source,
            "min_score": min_score,
            "limit": limit,
        }
        if intent == "auto" and not policy.should_recall:
            if record_event:
                from src.memory.curator.recall_events import append_recall_event

                append_recall_event(
                    {**event, "status": "skipped", "reason": policy.reason},
                    root=_root,
                )
            return (
                "No active recall triggered.\n"
                f"- reason: `{policy.reason}`\n"
                "- next: continue without adding memory context."
            )

        from src.tools.recall_memories import run as recall_run

        recalled = await recall_run(
            query=query,
            limit=limit,
            source=source,
            min_score=min_score,
            include_graph_context=True,
            known_entities=known_entities,
            _repos=_repos,
        )
        semantic_hints = await _semantic_relation_hints(
            query=query,
            limit=limit,
            source=source,
            min_score=min_score,
            repos=_repos,
        )

        lines = [
            f"## Remember: {query}",
            f"- trigger: `{policy.reason}`",
            f"- intent: `{intent}`",
            "",
            recalled,
        ]
        if semantic_hints:
            event["semantic_relation_hints"] = semantic_hints
            lines.extend([
                "",
                "## Semantic relation hints",
            ])
            for hint in semantic_hints:
                evidence = str(hint.get("evidence", "")).replace('"', "'")
                command = (
                    "curator_workbench action=upsert_relation "
                    f"source_id={hint.get('source_id', '')} "
                    f"target_id={hint.get('target_id', '')} "
                    f"relation_type={hint.get('relation_type', '')} "
                    f"weight={hint.get('weight', 1.0)} "
                    f"evidence=\"{evidence}\" "
                    "reason=\"active recall semantic neighbor\""
                )
                lines.append(
                    f"- `{hint.get('source_id', '')}` "
                    f"-[{hint.get('relation_type', '')} {hint.get('weight', '')}]-> "
                    f"`{hint.get('target_id', '')}` command=`{command}`"
                )

        if intent in {"link", "verify"}:
            recommendation = recommend_link_relation(
                LinkSignals(
                    semantic_score=kwargs.get("semantic_score", 0.0),
                    entity_overlap=kwargs.get("entity_overlap", 0.0),
                    keyword_overlap=kwargs.get("keyword_overlap", 0.0),
                    source_quality=1.0 if policy.should_recall else 0.5,
                    contradiction_score=kwargs.get("contradiction_score", 0.0),
                )
            )
            event.update({
                "link_action": recommendation.action,
                "link_score": recommendation.score,
                "link_reasons": list(recommendation.reasons),
            })
            lines.extend([
                "",
                "## Link hint",
                f"- action: `{recommendation.action}`",
                f"- score: `{recommendation.score}`",
                f"- reasons: `{', '.join(recommendation.reasons) or 'none'}`",
            ])

        if intent == "verify":
            lines.extend([
                "",
                "## Verification policy",
                "- do not overwrite canon automatically;",
                "- create `CONTRADICTS` when recalled context conflicts;",
                "- create `REFINES` when the new fact narrows prior memory.",
            ])

        if record_event:
            from src.memory.curator.recall_events import append_recall_event

            event_path = append_recall_event(
                {
                    **event,
                    "status": "recalled",
                    "result_excerpt": recalled[:500],
                },
                root=_root,
            )
            lines.extend([
                "",
                "## Recall event",
                f"- artifact: `{event_path}`",
            ])

        return "\n".join(lines)
    except Exception as exc:
        logger.exception("remember failed")
        return f"[ERROR] Failed to remember: {exc}"


async def _semantic_relation_hints(
    *,
    query: str,
    limit: int,
    source: str,
    min_score: float,
    repos: Any | None,
) -> list[dict[str, Any]]:
    """Return reviewable semantic graph hints for active recall."""

    retriever = getattr(getattr(repos, "memory", None), "hybrid_retriever", None) if repos is not None else None
    if retriever is None:
        return []
    from src.memory.retrieval.graph_context import semantic_relation_hints

    results = await retriever.search(
        query=query,
        top_k=limit,
        source_filter=source or None,
    )
    return semantic_relation_hints(
        [result for result in results if result.fusion_score >= min_score],
        max_hints=min(limit, 5),
    )
