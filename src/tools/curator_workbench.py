"""Tool: curator_workbench - inspect memory candidates and graph context."""

from __future__ import annotations

from datetime import date
from typing import Any


DEFINITION: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "curator_workbench",
        "description": (
            "Workbench for nightly memory curation. Lists reviewable candidates, "
            "inspects missing metadata, shows graph context, and traces provenance."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "list",
                        "queue",
                        "runbook",
                        "inspect",
                        "trace",
                        "graph",
                        "explain",
                        "map",
                        "preview_hints",
                        "materialize_hints",
                        "upsert_relation",
                        "explain_relation",
                        "recall_packet",
                        "preview_weight_policy",
                        "write_weight_policy_draft",
                        "approve_weight_policy",
                        "audit_weight_policy",
                        "audit_weight_policy_suite",
                    ],
                    "description": "Workbench action.",
                    "default": "list",
                },
                "query": {
                    "type": "string",
                    "description": "Recall/query text, or a |/newline-separated audit suite override.",
                    "default": "",
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
                    "description": "Optional memory source filter for recall_packet.",
                    "default": "",
                },
                "root": {
                    "type": "string",
                    "description": "Optional project/artifact root. Defaults to the Kairos project root.",
                    "default": "",
                },
                "path": {
                    "type": "string",
                    "description": "Optional candidate JSONL path for inspect/trace.",
                    "default": "",
                },
                "candidate_id": {
                    "type": "string",
                    "description": "Candidate id for inspect/trace/graph/map or optional relation provenance.",
                    "default": "",
                },
                "item_id": {
                    "type": "string",
                    "description": "Queue item id for focused runbook output.",
                    "default": "",
                },
                "source_id": {
                    "type": "string",
                    "description": "Source id for upsert_relation, graph node lookup, or explain_relation.",
                    "default": "",
                },
                "target_id": {
                    "type": "string",
                    "description": "Target id for upsert_relation or graph node lookup.",
                    "default": "",
                },
                "memory_key": {
                    "type": "string",
                    "description": "Canonical memory key for graph action; expands to memory:<key>.",
                    "default": "",
                },
                "relation_type": {
                    "type": "string",
                    "description": "Relation type for upsert_relation or explain_relation.",
                    "default": "",
                },
                "relation_id": {
                    "type": "string",
                    "description": "Curated relation id for explain_relation.",
                    "default": "",
                },
                "weight": {
                    "type": "number",
                    "description": "Relation weight for upsert_relation.",
                    "default": 1.0,
                },
                "evidence": {
                    "type": "string",
                    "description": "Evidence text for upsert_relation.",
                    "default": "",
                },
                "reason": {
                    "type": "string",
                    "description": "Curator reason for upsert_relation.",
                    "default": "",
                },
                "entity_id": {
                    "type": "string",
                    "description": "Entity id for graph action.",
                    "default": "",
                },
                "status": {
                    "type": "string",
                    "description": "Status filter for list. Use empty string for all.",
                    "default": "pending",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum rows to return.",
                    "default": 20,
                },
                "depth": {
                    "type": "integer",
                    "description": "Graph depth, max 5.",
                    "default": 1,
                },
                "known_entities": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional known entities used to enrich recall graph context.",
                    "default": [],
                },
            },
        },
    },
}


async def _entity_repo_from_kwargs(kwargs: dict[str, Any]) -> Any:
    repos = kwargs.get("_repos")
    if repos is not None:
        repo = getattr(getattr(repos, "memory", None), "entity_graph", None)
        if repo is not None:
            return repo

    from src.memory.repos_memory.entity_repo import EntityRepository

    return EntityRepository()


def _memory_repo_from_kwargs(kwargs: dict[str, Any]) -> Any | None:
    repos = kwargs.get("_repos")
    if repos is None:
        return None
    return getattr(getattr(repos, "memory", None), "memory_index", None)


def _retriever_from_kwargs(kwargs: dict[str, Any]) -> Any | None:
    repos = kwargs.get("_repos")
    if repos is None:
        return None
    return getattr(getattr(repos, "memory", None), "hybrid_retriever", None)


def _root(kwargs: dict[str, Any]) -> str | None:
    root = str(kwargs.get("root") or "").strip()
    return root or None


def _path(kwargs: dict[str, Any]) -> str | None:
    path = str(kwargs.get("path") or "").strip()
    return path or None


def _build_current_curator_plan(root: str | None) -> dict[str, Any]:
    """Build the interactive curator queue for today's persisted artifacts.

    The scheduled morning report intentionally targets yesterday before 04:00,
    but interactive curator actions must see items written during the current
    calendar day.
    """
    from src.memory.synthesis.morning_plan import build_morning_plan

    return build_morning_plan(root=root, target_date=date.today())


def _format_card(card: dict[str, Any]) -> str:
    missing = ", ".join(card.get("metadata_missing") or [])
    missing_text = f" missing={missing}" if missing else ""
    relation = card.get("relation_type") or ""
    relation_text = f" relation={relation}" if relation else ""
    target_text = " target=pending" if card.get("target_needs_resolution") else ""
    query = str(card.get("query") or "").replace("\n", " ")[:120]
    return (
        f"- `{card.get('candidate_id', '')}` [{card.get('status', 'pending')}] "
        f"{card.get('recommendation', '')} score={card.get('score', 0)}"
        f"{missing_text}{relation_text}{target_text} source={card.get('source', '')} query={query}"
    )


def _format_queue_item(item: dict[str, Any]) -> str:
    command = str(item.get("recommended_command") or "").strip()
    command_text = f" command=`{command}`" if command else ""
    item_id = str(item.get("id") or "").strip()
    runbook_text = f" runbook=`curator_workbench action=runbook item_id={item_id}`" if item_id else ""
    reasons = ", ".join(str(reason) for reason in item.get("why") or [] if str(reason).strip())
    reasons_text = f" why={reasons}" if reasons else ""
    return (
        f"- **P{item.get('priority', 0)} {item.get('kind', '')}** `{item.get('id', '')}` "
        f"{item.get('next_action', '')}{command_text}{runbook_text}{reasons_text}"
    )


def _format_runbook_command(item: dict[str, Any], command: str, label: str) -> str:
    title = str(item.get("title") or item.get("kind") or "").strip()
    return (
        f"- **P{item.get('priority', 0)} {item.get('kind', '')}** "
        f"`{item.get('id', '')}` {label}: `{command}`"
        f"{f' - {title}' if title else ''}"
    )


def _is_preview_action(item: dict[str, Any], command: str) -> bool:
    action = str(item.get("next_action") or "")
    return action.startswith("preview") or "preview_" in command or " action=map" in command


def _runbook_actions(plan: dict[str, Any], limit: int, item_id: str = "") -> list[dict[str, Any]]:
    actions = list(plan.get("actions") or [])
    if item_id == "top":
        return actions[:1]
    if item_id:
        return [item for item in actions if str(item.get("id") or "") == item_id][:1]
    return actions[:limit]


def _render_curator_runbook(plan: dict[str, Any], limit: int, item_id: str = "") -> str:
    actions = _runbook_actions(plan, limit, item_id)
    if item_id and not actions:
        return f"[ERROR] curator queue item not found: {item_id}"
    pipeline = plan.get("pipeline_status") or {}
    lines = [
        "## Curator runbook",
        f"- status: `{pipeline.get('status', 'unknown')}`",
        f"- queue_items: `{len(actions)}`",
    ]

    focus_lines: list[str] = []
    inspection_lines: list[str] = []
    preview_lines: list[str] = []
    mutation_lines: list[str] = []
    fallback_lines: list[str] = []
    for item in actions:
        if item_id:
            detail = str(item.get("detail") or "").strip()
            reasons = ", ".join(str(reason) for reason in item.get("why") or [] if str(reason).strip())
            focus_lines.extend([
                f"- selector: `{item_id}`",
                f"- id: `{item.get('id', '')}`",
                f"- kind: `{item.get('kind', '')}`",
                f"- title: {item.get('title', '')}",
                f"- next_action: `{item.get('next_action', '')}`",
            ])
            if detail:
                focus_lines.append(f"- detail: {detail}")
            if reasons:
                focus_lines.append(f"- why: {reasons}")
        recommended = str(item.get("recommended_command") or "").strip()
        followup = str(item.get("followup_command") or "").strip()
        fallback = str(item.get("fallback_command") or "").strip()
        if recommended:
            if _is_preview_action(item, recommended):
                preview_lines.append(_format_runbook_command(item, recommended, "preview"))
            else:
                inspection_lines.append(_format_runbook_command(item, recommended, "inspect"))
        if followup:
            mutation_lines.append(_format_runbook_command(item, followup, "mutate"))
        if fallback:
            fallback_lines.append(_format_runbook_command(item, fallback, "fallback"))

    if focus_lines:
        lines.extend(["", "### Focus"])
        lines.extend(focus_lines)
    lines.extend(["", "### 1. Safe inspection"])
    lines.extend(inspection_lines or ["- no inspection commands queued"])
    lines.extend(["", "### 2. Preview before mutation"])
    lines.extend(preview_lines or ["- no preview commands queued"])
    lines.extend(["", "### 3. Explicit mutations"])
    lines.extend(mutation_lines or ["- no mutation follow-ups queued"])
    if fallback_lines:
        lines.extend(["", "### 4. Reject/fallback paths"])
        lines.extend(fallback_lines)

    weight_recommendations = list(plan.get("weight_recommendations") or [])
    if weight_recommendations:
        lines.extend([
            "",
            "### Weight policy gate",
            "- Audit: `curator_workbench action=audit_weight_policy_suite`",
            "- Draft only after audit: `curator_workbench action=write_weight_policy_draft`",
        ])

    return "\n".join(lines)


def _format_entity(item: dict[str, Any]) -> str:
    rel = item.get("relation_type") or ""
    rel_text = f" [{rel}]" if rel else ""
    weight = item.get("weight", "")
    weight_text = f" weight={weight}" if weight not in {"", None} else ""
    return f"- `{item.get('id', '')}` {item.get('name', '')} ({item.get('entity_type', '')}){rel_text}{weight_text}"


def _format_curated_relation(relation: dict[str, Any]) -> list[str]:
    lines = [
        (
            f"- `{relation.get('relation_id', '')}` "
            f"`{relation.get('source_id', '')}` "
            f"-[{relation.get('relation_type', '')}]-> "
            f"`{relation.get('target_id', '')}` weight={relation.get('weight', '')}"
        )
    ]
    if relation.get("candidate_id"):
        lines.append(f"  - candidate_id: `{relation.get('candidate_id')}`")
    evidence = str(relation.get("evidence") or "").strip()
    if evidence:
        lines.append(f"  - evidence: {evidence[:240]}")
    provenance = relation.get("provenance") if isinstance(relation.get("provenance"), dict) else {}
    if provenance:
        bits = ", ".join(f"{key}={value}" for key, value in sorted(provenance.items())[:6])
        lines.append(f"  - provenance: {bits}")
    metadata = relation.get("metadata") if isinstance(relation.get("metadata"), dict) else {}
    if metadata:
        bits = ", ".join(f"{key}={value}" for key, value in sorted(metadata.items())[:6])
        lines.append(f"  - metadata: {bits}")
    return lines


def _graph_node_id(kwargs: dict[str, Any], entity_id: str) -> str:
    if entity_id:
        return entity_id
    memory_key = str(kwargs.get("memory_key") or "").strip()
    if memory_key:
        return memory_key if memory_key.startswith("memory:") else f"memory:{memory_key}"
    for field in ("source_id", "target_id"):
        node_id = str(kwargs.get(field) or "").strip()
        if node_id:
            return node_id
    return ""


def _render_graph_mermaid(root_id: str, items: list[dict[str, Any]]) -> str:
    if not root_id or not items:
        return "flowchart LR\n  empty[\"No graph context\"]"

    nodes: dict[str, str] = {root_id: "n0"}
    for item in items:
        node_id = str(item.get("id") or "").strip()
        if node_id and node_id not in nodes:
            nodes[node_id] = f"n{len(nodes)}"

    lines = ["flowchart LR"]
    for node_id, mermaid_id in nodes.items():
        node_type = node_id.split(":", 1)[0] if ":" in node_id else "node"
        label = _mermaid_label(f"{node_type}\\n{node_id}")
        lines.append(f"  {mermaid_id}[\"{label}\"]")

    for item in items:
        source = str(item.get("source_id") or root_id).strip()
        target = str(item.get("target_id") or item.get("id") or "").strip()
        if not source or not target:
            continue
        if source not in nodes:
            nodes[source] = f"n{len(nodes)}"
        if target not in nodes:
            nodes[target] = f"n{len(nodes)}"
        relation = str(item.get("relation_type") or "RELATED")
        weight = item.get("weight", "")
        weight_text = f" {weight}" if weight not in {"", None} else ""
        label = _mermaid_label(f"{relation}{weight_text}")
        lines.append(f"  {nodes[source]} -->|\"{label}\"| {nodes[target]}")
    return "\n".join(lines)


def _mermaid_label(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace('"', "'")
        .replace("\r", " ")
        .replace("\n", "<br/>")
    )


def _weight_policy_regression_queries(query: str) -> list[str]:
    """Return curator-approved queries for retrieval weight regression checks."""

    explicit = [
        item.strip()
        for chunk in query.splitlines()
        for item in chunk.split("|")
        if item.strip()
    ]
    if explicit:
        return explicit
    return [
        "Que recuerda Kairos sobre Mauro y sus preferencias?",
        "Que decisiones arquitectonicas tomamos sobre memoria por capas?",
        "Que bugs recientes afectan el sistema de memoria o retrieval?",
        "Que tareas pendientes hay para los curadores de memoria?",
        "Que conexiones hay entre embeddings, grafo y memoria canonica?",
    ]


async def run(**kwargs) -> str:
    action = str(kwargs.get("action") or "list")
    limit = min(int(kwargs.get("limit", 20)), 50)
    depth = min(int(kwargs.get("depth", 1)), 5)
    candidate_id = str(kwargs.get("candidate_id") or "").strip()
    entity_id = str(kwargs.get("entity_id") or "").strip()
    query = str(kwargs.get("query") or "").strip()

    try:
        from src.memory.curator.candidate_workbench import (
            explain_candidate,
            find_candidate,
            inspect_candidate,
            candidate_relation_map,
            list_candidate_cards,
            source_trace,
        )

        if action == "recall_packet":
            if not query:
                return "[ERROR] query is required."
            from src.tools.recall_memories import run as recall_run
            from src.memory.retrieval.graph_context import semantic_relation_hints

            source = str(kwargs.get("source") or "")
            min_score = float(kwargs.get("min_score", 0.2) or 0.2)
            recalled = await recall_run(
                query=query,
                limit=limit,
                source=source,
                min_score=min_score,
                include_graph_context=True,
                known_entities=kwargs.get("known_entities") or [],
                _repos=kwargs.get("_repos"),
            )
            semantic_hints: list[dict[str, Any]] = []
            retriever = _retriever_from_kwargs(kwargs)
            if retriever is not None:
                recall_results = await retriever.search(
                    query=query,
                    top_k=limit,
                    source_filter=source or None,
                )
                semantic_hints = semantic_relation_hints(
                    [result for result in recall_results if result.fusion_score >= min_score],
                    max_hints=min(limit, 5),
                )
            plan = _build_current_curator_plan(_root(kwargs))
            actions = list(plan.get("actions") or [])[: min(limit, 5)]
            lines = [
                f"## Recall packet `{query}`",
                recalled,
                "",
                "## Semantic relation hints",
            ]
            if semantic_hints:
                for hint in semantic_hints:
                    evidence = str(hint.get("evidence", "")).replace('"', "'")
                    command = (
                        "curator_workbench action=upsert_relation "
                        f"source_id={hint.get('source_id', '')} "
                        f"target_id={hint.get('target_id', '')} "
                        f"relation_type={hint.get('relation_type', '')} "
                        f"weight={hint.get('weight', 1.0)} "
                        f"evidence=\"{evidence}\" "
                        "reason=\"semantic recall neighbor\""
                    )
                    lines.append(
                        f"- `{hint.get('source_id', '')}` "
                        f"-[{hint.get('relation_type', '')} {hint.get('weight', '')}]-> "
                        f"`{hint.get('target_id', '')}` command=`{command}`"
                    )
            else:
                lines.append("- no semantic relation hints")
            lines.extend([
                "",
                "## Curator next steps",
            ])
            if actions:
                lines.extend(_format_queue_item(item) for item in actions)
            else:
                lines.append("- no queued curator action")
            return "\n".join(lines)

        if action in {
            "preview_weight_policy",
            "write_weight_policy_draft",
            "approve_weight_policy",
            "audit_weight_policy",
            "audit_weight_policy_suite",
        }:
            from src.memory.retrieval.source_policy import (
                approve_weight_policy_draft,
                build_weight_policy_draft,
                compare_policy_rankings,
                write_weight_policy_draft,
            )

            if action == "audit_weight_policy":
                if not query:
                    return "[ERROR] query is required."
                retriever = _retriever_from_kwargs(kwargs)
                if retriever is None:
                    return "[ERROR] hybrid retriever is required for weight policy audit."
                results = await retriever.search(
                    query=query,
                    top_k=limit,
                    source_filter=str(kwargs.get("source") or "") or None,
                )
                audit = compare_policy_rankings(results, root=_root(kwargs), limit=limit)
                lines = [
                    f"## Retrieval weight policy audit `{query}`",
                    f"- approved_policy_version: `{audit.get('approved_policy_version', '')}`",
                    f"- approved_policy_status: `{audit.get('approved_policy_status', '')}`",
                    f"- has_approved_policy: `{audit.get('has_approved_policy', False)}`",
                ]
                rows = audit.get("rows") or []
                if rows:
                    lines.extend(["", "### Ranking impact"])
                    for row in rows[:limit]:
                        lines.append(
                            f"- {row.get('builtin_rank')} -> {row.get('approved_rank')} "
                            f"`{row.get('source', '')}` `{row.get('source_key', '')}` "
                            f"builtin={row.get('builtin_score', '')} approved={row.get('approved_score', '')} "
                            f"delta={row.get('delta', '')}"
                        )
                else:
                    lines.append("- no results to compare")
                return "\n".join(lines)

            if action == "audit_weight_policy_suite":
                retriever = _retriever_from_kwargs(kwargs)
                if retriever is None:
                    return "[ERROR] hybrid retriever is required for weight policy audit."
                queries = _weight_policy_regression_queries(query)
                source_filter = str(kwargs.get("source") or "") or None
                lines = [
                    "## Retrieval weight policy regression suite",
                    f"- queries: `{len(queries)}`",
                    f"- source_filter: `{source_filter or 'all'}`",
                ]
                changed_queries = 0
                empty_queries = 0
                rank_changed_queries = 0
                score_changed_queries = 0
                max_abs_delta = 0.0
                for index, regression_query in enumerate(queries[:limit], 1):
                    results = await retriever.search(
                        query=regression_query,
                        top_k=limit,
                        source_filter=source_filter,
                    )
                    audit = compare_policy_rankings(results, root=_root(kwargs), limit=limit)
                    rows = audit.get("rows") or []
                    if not rows:
                        empty_queries += 1
                    rank_changes = [row for row in rows if int(row.get("rank_delta") or 0) != 0]
                    score_deltas = [row for row in rows if float(row.get("delta") or 0.0) != 0.0]
                    if rank_changes:
                        rank_changed_queries += 1
                    if score_deltas:
                        score_changed_queries += 1
                    for row in rows:
                        max_abs_delta = max(max_abs_delta, abs(float(row.get("delta") or 0.0)))
                    if rank_changes or score_deltas:
                        changed_queries += 1
                    lines.extend([
                        "",
                        f"### {index}. `{regression_query}`",
                        f"- results: `{len(rows)}`",
                        f"- rank_changes: `{len(rank_changes)}`",
                        f"- score_deltas: `{len(score_deltas)}`",
                    ])
                    for row in rows[: min(3, limit)]:
                        lines.append(
                            f"- {row.get('builtin_rank')} -> {row.get('approved_rank')} "
                            f"`{row.get('source', '')}` `{row.get('source_key', '')}` "
                            f"builtin={row.get('builtin_score', '')} approved={row.get('approved_score', '')} "
                            f"delta={row.get('delta', '')}"
                        )
                if empty_queries or rank_changed_queries:
                    verdict = "review_required"
                    next_action = "Next: revisar queries vacias/cambios de rank antes de aprobar cualquier draft de pesos."
                elif score_changed_queries:
                    verdict = "score_shift_only"
                    next_action = "Next: revisar deltas de score; el ranking no cambio en la suite."
                else:
                    verdict = "no_policy_impact"
                    next_action = "Next: no hay impacto observable en esta suite; se puede revisar el draft con menor riesgo."
                lines.insert(3, f"- changed_queries: `{changed_queries}`")
                lines.insert(4, f"- empty_queries: `{empty_queries}`")
                lines.insert(5, f"- rank_changed_queries: `{rank_changed_queries}`")
                lines.insert(6, f"- score_changed_queries: `{score_changed_queries}`")
                lines.insert(7, f"- max_abs_delta: `{round(max_abs_delta, 4)}`")
                lines.insert(8, f"- verdict: `{verdict}`")
                lines.append("")
                lines.append(next_action)
                return "\n".join(lines)

            if action == "approve_weight_policy":
                approved = approve_weight_policy_draft(
                    root=_root(kwargs),
                    approved_by=str(kwargs.get("reason") or "curator"),
                    reason=str(kwargs.get("evidence") or ""),
                )
                changes = approved.get("changes") or []
                lines = [
                    "## Approved retrieval weight policy",
                    f"- version: `{approved.get('version', '')}`",
                    f"- path: `{approved.get('path', '')}`",
                    f"- changes: `{len(changes)}`",
                ]
                return "\n".join(lines)

            plan = _build_current_curator_plan(_root(kwargs))
            recommendations = list(plan.get("weight_recommendations") or [])
            actionable = [item for item in recommendations if float(item.get("delta") or 0.0) != 0.0]
            draft = (
                write_weight_policy_draft(actionable, root=_root(kwargs))
                if action == "write_weight_policy_draft"
                else build_weight_policy_draft(actionable, root=_root(kwargs))
            )
            changes = draft.get("changes") or []
            title = "Written retrieval weight policy draft" if action == "write_weight_policy_draft" else "Preview retrieval weight policy draft"
            lines = [
                f"## {title}",
                f"- version: `{draft.get('version', '')}`",
                f"- status: `{draft.get('status', '')}`",
                f"- apply_policy: `{draft.get('apply_policy', '')}`",
                f"- path: `{draft.get('path', '')}`",
                f"- changes: `{len(changes)}`",
            ]
            if changes:
                lines.append("")
                lines.append("### Changes")
                for change in changes[:limit]:
                    lines.append(
                        f"- `{change.get('layer', '')}` "
                        f"{change.get('current_weight', '')} -> {change.get('proposed_weight', '')} "
                        f"delta={change.get('delta', '')}"
                    )
            return "\n".join(lines)

        if action == "list":
            cards = list_candidate_cards(
                root=_root(kwargs),
                status=str(kwargs.get("status", "pending")),
                limit=limit,
            )
            if not cards:
                return "No curator candidates found."
            lines = ["## Curator candidates"]
            lines.extend(_format_card(card) for card in cards)
            return "\n".join(lines)

        if action == "queue":
            plan = _build_current_curator_plan(_root(kwargs))
            actions = list(plan.get("actions") or [])[:limit]
            if not actions:
                return "No curator queue items found."
            pipeline = plan.get("pipeline_status") or {}
            lines = [
                "## Curator queue",
                f"- status: `{pipeline.get('status', 'unknown')}`",
            ]
            lines.extend(_format_queue_item(item) for item in actions)
            return "\n".join(lines)

        if action == "runbook":
            return _render_curator_runbook(
                _build_current_curator_plan(_root(kwargs)),
                limit,
                item_id=str(kwargs.get("item_id") or "").strip(),
            )

        if action in {"inspect", "trace"} and not candidate_id:
            return "[ERROR] candidate_id is required."

        if action == "trace":
            candidate = find_candidate(candidate_id, root=_root(kwargs), path=_path(kwargs))
            if candidate is None:
                return f"[ERROR] candidate not found: {candidate_id}"
            trace = source_trace(candidate)
            lines = [f"## Source trace `{candidate_id}`"]
            for key, value in trace.items():
                if key == "derived_from":
                    continue
                lines.append(f"- {key}: `{value}`")
            derived = trace.get("derived_from") or []
            if derived:
                lines.append("")
                lines.append("### Derived From")
                lines.extend(f"- `{item}`" for item in derived)
            return "\n".join(lines)

        if action == "inspect":
            repo = await _entity_repo_from_kwargs(kwargs)
            packet = await inspect_candidate(
                candidate_id,
                repo,
                memory_repo=_memory_repo_from_kwargs(kwargs),
                retriever=_retriever_from_kwargs(kwargs),
                root=_root(kwargs),
                path=_path(kwargs),
                graph_depth=depth,
            )
            card = packet["card"]
            lines = [
                f"## Candidate `{candidate_id}`",
                _format_card(card),
            ]
            suggestions = packet.get("suggestions") or {}
            missing = suggestions.get("missing_fields") or card.get("metadata_missing") or []
            if missing:
                lines.append(f"- missing: `{', '.join(missing)}`")
            if suggestions:
                lines.append(f"- suggested_source_id: `{suggestions.get('suggested_source_id', '')}`")
                lines.append(f"- suggested_target_id: `{suggestions.get('suggested_target_id', '')}`")
                lines.append(f"- relation_type: `{suggestions.get('relation_type', '')}`")
                entities = suggestions.get("entities") or []
                if entities:
                    lines.append("")
                    lines.append("### Entity Suggestions")
                    lines.extend(_format_entity(entity) for entity in entities[:limit])
            target_suggestions = packet.get("target_suggestions") or []
            if target_suggestions:
                lines.append("")
                lines.append("### Target Suggestions")
                for item in target_suggestions[:limit]:
                    lines.append(
                        f"- `{item.get('target_id', '')}` score={item.get('score', 0)} "
                        f"source={item.get('source', '')} reason={item.get('reason', '')}"
                    )
            candidate_neighbors = packet.get("candidate_neighbors") or []
            if candidate_neighbors:
                lines.append("")
                lines.append("### Candidate Neighbors")
                for item in candidate_neighbors[:limit]:
                    lines.append(
                        f"- `{item.get('target_id', '')}` score={item.get('score', 0)} "
                        f"source={item.get('source', '')} reason={item.get('reason', '')}"
                    )
                    if item.get("refine_command"):
                        lines.append(f"  refine: `{item.get('refine_command')}`")
                    if item.get("duplicate_command"):
                        lines.append(f"  duplicate: `{item.get('duplicate_command')}`")
            graph = packet.get("graph") or {}
            for field, items in graph.items():
                if items:
                    lines.append("")
                    lines.append(f"### Graph {field}")
                    lines.extend(_format_entity(item) for item in items[:limit])
            return "\n".join(lines)

        if action == "explain":
            if not candidate_id:
                return "[ERROR] candidate_id is required."
            repo = await _entity_repo_from_kwargs(kwargs)
            explanation = await explain_candidate(
                candidate_id,
                entity_repo=repo,
                memory_repo=_memory_repo_from_kwargs(kwargs),
                retriever=_retriever_from_kwargs(kwargs),
                root=_root(kwargs),
                path=_path(kwargs),
                graph_depth=depth,
            )
            lines = [
                f"## Candidate explanation `{candidate_id}`",
                f"- status: `{explanation.get('status', '')}`",
                f"- recommendation: `{explanation.get('recommendation', '')}` score={explanation.get('score', 0)}",
                f"- relation_type: `{explanation.get('relation_type', '')}`",
                f"- target_needs_resolution: `{explanation.get('target_needs_resolution', False)}`",
            ]
            missing = explanation.get("missing_metadata") or []
            if missing:
                lines.append(f"- missing_metadata: `{', '.join(missing)}`")
            reasons = explanation.get("reasons") or []
            if reasons:
                lines.append("")
                lines.append("### Reasons")
                lines.extend(f"- {reason}" for reason in reasons[:limit])
            evidence = explanation.get("evidence") or []
            if evidence:
                lines.append("")
                lines.append("### Evidence")
                for item in evidence[:limit]:
                    lines.append(f"- {item.get('field', '')}: `{item.get('value', '')}`")
            proposed = explanation.get("proposed_relations") or []
            if proposed:
                lines.append("")
                lines.append("### Proposed Relations")
                for relation in proposed[:limit]:
                    lines.append(
                        f"- `{relation.get('source_id', '')}` "
                        f"-[{relation.get('relation_type', '')}]-> "
                        f"`{relation.get('target_id', '')}`"
                    )
            candidate_neighbors = explanation.get("candidate_neighbors") or []
            if candidate_neighbors:
                lines.append("")
                lines.append("### Candidate Neighbors")
                for item in candidate_neighbors[:limit]:
                    lines.append(
                        f"- `{item.get('target_id', '')}` score={item.get('score', 0)} "
                        f"source={item.get('source', '')} reason={item.get('reason', '')}"
                    )
                    if item.get("refine_command"):
                        lines.append(f"  refine: `{item.get('refine_command')}`")
                    if item.get("duplicate_command"):
                        lines.append(f"  duplicate: `{item.get('duplicate_command')}`")
            next_action = explanation.get("next_action") or {}
            if next_action:
                lines.append("")
                lines.append("### Next Action")
                lines.append(f"- action: `{next_action.get('action', '')}`")
                lines.append(f"- reason: `{next_action.get('reason', '')}`")
                lines.append(f"- command: `{next_action.get('command', '')}`")
                if next_action.get("followup_action"):
                    lines.append(f"- followup_action: `{next_action.get('followup_action', '')}`")
                    lines.append(f"- followup_command: `{next_action.get('followup_command', '')}`")
            return "\n".join(lines)

        if action == "map":
            if not candidate_id:
                return "[ERROR] candidate_id is required."
            candidate = find_candidate(candidate_id, root=_root(kwargs), path=_path(kwargs))
            if candidate is None:
                return f"[ERROR] candidate not found: {candidate_id}"
            relation_map = candidate_relation_map(candidate, limit=limit)
            edges = relation_map.get("edges") or []
            nodes = relation_map.get("nodes") or []
            lines = [
                f"## Candidate relation map `{candidate_id}`",
                f"- nodes: `{len(nodes)}`",
                f"- edges: `{len(edges)}`",
            ]
            if edges:
                lines.append("")
                lines.append("### Edges")
                for edge in edges[:limit]:
                    pending = " pending" if edge.get("needs_resolution") else ""
                    lines.append(
                        f"- `{edge.get('source_id', '')}` "
                        f"-[{edge.get('relation_type', '')}{pending}]-> "
                        f"`{edge.get('target_id', '')}`"
                    )
            lines.append("")
            lines.append("### Mermaid")
            lines.append("```mermaid")
            lines.append(str(relation_map.get("mermaid") or "flowchart LR"))
            lines.append("```")
            return "\n".join(lines)

        if action in {"preview_hints", "materialize_hints"}:
            from src.memory.curator.curation_events import materialize_relation_hints

            repo = await _entity_repo_from_kwargs(kwargs)
            result = await materialize_relation_hints(
                repo,
                root=_root(kwargs),
                limit=limit,
                dry_run=action == "preview_hints",
            )
            lines = [
                "## Preview relation hints" if action == "preview_hints" else "## Materialized relation hints",
                f"- dry_run: `{result.get('dry_run', False)}`",
                f"- previewed: `{result.get('previewed', 0)}`",
                f"- materialized: `{result.get('materialized', 0)}`",
                f"- skipped: `{result.get('skipped', 0)}`",
            ]
            relations = result.get("relations") or []
            if relations:
                lines.append("")
                lines.append("### Relations")
                for relation in relations[:limit]:
                    lines.append(
                        f"- `{relation.get('source_id', '')}` "
                        f"-[{relation.get('relation_type', '')}]-> "
                        f"`{relation.get('target_id', '')}`"
                    )
            return "\n".join(lines)

        if action == "upsert_relation":
            from src.memory.curator.curation_events import upsert_curator_relation

            repo = await _entity_repo_from_kwargs(kwargs)
            relation = await upsert_curator_relation(
                repo,
                source_id=str(kwargs.get("source_id") or ""),
                target_id=str(kwargs.get("target_id") or ""),
                relation_type=str(kwargs.get("relation_type") or ""),
                weight=float(kwargs.get("weight", 1.0) or 1.0),
                evidence=str(kwargs.get("evidence") or ""),
                reason=str(kwargs.get("reason") or ""),
                candidate_id=candidate_id,
                root=_root(kwargs),
            )
            lines = [
                "## Upserted curator relation",
                (
                    f"- `{relation.get('source_id', '')}` "
                    f"-[{relation.get('relation_type', '')}]-> "
                    f"`{relation.get('target_id', '')}` weight={relation.get('weight', 0)}"
                ),
            ]
            if relation.get("curated_relation_id"):
                lines.append(f"- curated_relation_id: `{relation.get('curated_relation_id')}`")
            if relation.get("decision_event", {}).get("artifact"):
                lines.append(f"- decision: `{relation['decision_event']['artifact']}`")
            return "\n".join(lines)

        if action == "explain_relation":
            repo = await _entity_repo_from_kwargs(kwargs)
            relation_id = str(kwargs.get("relation_id") or "").strip()
            source_id = str(kwargs.get("source_id") or "").strip()
            target_id = str(kwargs.get("target_id") or "").strip()
            relation_type = str(kwargs.get("relation_type") or "").strip().upper()
            if relation_id or (source_id and target_id and relation_type):
                if not hasattr(repo, "get_curated_relation"):
                    return "[ERROR] repository cannot read curated relations."
                relation = await repo.get_curated_relation(
                    relation_id,
                    source_id=source_id,
                    target_id=target_id,
                    relation_type=relation_type,
                    candidate_id=candidate_id,
                )
                if relation is None:
                    return "No curated relation found."
                lines = ["## Curated relation"]
                lines.extend(_format_curated_relation(relation))
                return "\n".join(lines)

            node_id = _graph_node_id(kwargs, entity_id)
            if not node_id:
                return "[ERROR] relation_id or source/target/relation_type or graph node is required."
            if not hasattr(repo, "list_curated_relations_for_node"):
                return "[ERROR] repository cannot list curated relations."
            relations = await repo.list_curated_relations_for_node(node_id, limit=limit)
            if not relations:
                return f"No curated relations for `{node_id}`."
            lines = [f"## Curated relations for `{node_id}`"]
            for relation in relations[:limit]:
                lines.extend(_format_curated_relation(relation))
            return "\n".join(lines)

        if action == "graph":
            repo = await _entity_repo_from_kwargs(kwargs)
            if not entity_id and candidate_id:
                packet = await inspect_candidate(
                    candidate_id,
                    repo,
                    memory_repo=_memory_repo_from_kwargs(kwargs),
                    retriever=_retriever_from_kwargs(kwargs),
                    root=_root(kwargs),
                    path=_path(kwargs),
                    graph_depth=depth,
                )
                graph = packet.get("graph") or {}
                if not graph:
                    return f"No graph context for `{candidate_id}`."
                lines = [f"## Candidate graph `{candidate_id}`"]
                for field, items in graph.items():
                    lines.append(f"### {field}")
                    lines.extend(_format_entity(item) for item in items[:limit])
                return "\n".join(lines)
            node_id = _graph_node_id(kwargs, entity_id)
            if not node_id:
                return "[ERROR] entity_id, memory_key, source_id, target_id, or candidate_id is required for graph."
            items = await repo.explore_graph(node_id, depth=depth)
            if not items:
                return f"No graph context for `{node_id}`."
            lines = [f"## Graph `{node_id}`"]
            lines.extend(_format_entity(item) for item in items[:limit])
            lines.append("")
            lines.append("### Mermaid")
            lines.append("```mermaid")
            lines.append(_render_graph_mermaid(node_id, items[:limit]))
            lines.append("```")
            return "\n".join(lines)

        return f"[ERROR] unknown action: {action}"
    except Exception as exc:
        return f"[ERROR] curator_workbench failed: {exc}"
