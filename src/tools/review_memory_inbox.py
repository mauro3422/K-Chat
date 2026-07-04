"""Tool: review_memory_inbox - resolve grouped memory inbox items."""

from __future__ import annotations

from typing import Any

DEFINITION: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "review_memory_inbox",
        "description": (
            "Review grouped save_memory inbox items. Lists repeated facts, "
            "promotes a group to canonical memory, or rejects noisy items."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "inspect", "promote", "reject"],
                    "description": "Inbox review action.",
                    "default": "list",
                },
                "root": {
                    "type": "string",
                    "description": "Optional project root.",
                    "default": "",
                },
                "group_id": {
                    "type": "string",
                    "description": "Inbox group id or source inbox_id for promote/reject.",
                    "default": "",
                },
                "key": {
                    "type": "string",
                    "description": "Optional canonical key override when promoting.",
                    "default": "",
                },
                "value": {
                    "type": "string",
                    "description": "Optional canonical value override when promoting.",
                    "default": "",
                },
                "reason": {
                    "type": "string",
                    "description": "Reason for rejecting a group.",
                    "default": "",
                },
                "status": {
                    "type": "string",
                    "description": "Status filter for list.",
                    "default": "pending",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum groups to show.",
                    "default": 20,
                },
                "include_recall_context": {
                    "type": "boolean",
                    "description": "Include layered recall context in inspect output.",
                    "default": False,
                },
            },
        },
    },
}


def _root(kwargs: dict[str, Any]) -> str | None:
    root = str(kwargs.get("root") or kwargs.get("_root") or "").strip()
    return root or None


def _format_group(group: dict[str, Any]) -> str:
    value = str(group.get("value") or "").replace("\n", " ")[:140]
    return (
        f"- `{group.get('group_id', '')}` [{group.get('status', 'pending')}] "
        f"key={group.get('key', '')} reinforced={group.get('reinforcement_count', 1)} "
        f"ids={','.join(group.get('inbox_ids', []))} value={value}"
    )


def _format_inspect_group(
    group: dict[str, Any],
    canonical_matches: list[dict[str, Any]] | None = None,
) -> list[str]:
    group_id = str(group.get("group_id") or "")
    inbox_ids = [str(item) for item in group.get("inbox_ids") or []]
    artifacts = [str(item) for item in group.get("artifacts") or [] if str(item).strip()]
    key = str(group.get("key") or "")
    value = str(group.get("value") or "")
    lines = [
        f"## Memory inbox group `{group_id}`",
        f"- status: `{group.get('status', 'pending')}`",
        f"- key: `{key}`",
        f"- reinforcement_count: `{group.get('reinforcement_count', 1)}`",
        f"- inbox_ids: `{', '.join(inbox_ids)}`",
        f"- promote_command: `review_memory_inbox action=promote group_id={group_id}`",
        f"- reject_command: `review_memory_inbox action=reject group_id={group_id} reason=<reason>`",
        f"- recall_packet: `curator_workbench action=recall_packet query=\"{_command_query(key, value)}\"`",
    ]
    if artifacts:
        lines.append(f"- artifacts: `{', '.join(artifacts[:4])}`")
    if value:
        lines.extend(["", "### Candidate Value", value])
    lines.extend(["", "### Canonical Check"])
    matches = canonical_matches or []
    if matches:
        for match in matches[:5]:
            preview = str(match.get("value") or "").replace("\n", " ")[:180]
            updated = str(match.get("updated_at") or "")
            updated_text = f" updated={updated}" if updated else ""
            lines.append(f"- `{match.get('key', '')}`{updated_text}: {preview}")
    else:
        lines.append("- no exact canonical key/value match found")
    lines.extend([
        "",
        "### Decision Guidance",
        *_decision_guidance(group, key, value, group_id, has_canonical_match=bool(matches)),
    ])
    lines.extend([
        "",
        "### Relation Preview",
        f"- `inbox_group:{group_id}` -[PROMOTED_TO]-> `memory:{key}`",
    ])
    for inbox_id in inbox_ids[:10]:
        lines.append(f"- `inbox:{inbox_id}` -[PROMOTED_TO]-> `memory:{key}`")
    return lines


def _decision_guidance(
    group: dict[str, Any],
    key: str,
    value: str,
    group_id: str,
    *,
    has_canonical_match: bool = False,
) -> list[str]:
    reinforcement = int(group.get("reinforcement_count") or 1)
    has_key = bool(key.strip())
    has_value = bool(value.strip())
    if has_canonical_match:
        recommendation = "review_existing_canon"
        reason = "canonical_match_found"
    elif not has_key or not has_value:
        recommendation = "complete_or_reject"
        reason = "missing_key_or_value"
    elif reinforcement > 1:
        recommendation = "promote_if_context_confirms"
        reason = "reinforced_inbox_signal"
    else:
        recommendation = "inspect_context_before_promote"
        reason = "single_inbox_signal"
    return [
        f"- recommendation: `{recommendation}`",
        f"- reason: `{reason}`",
        "- check: `value is durable, not just session noise`",
        "- check: `existing canon does not already say this better`",
        "- check: `recall context does not contradict the candidate value`",
        f"- safe_next: `review_memory_inbox action=inspect group_id={group_id} include_recall_context=true`",
        f"- promote_if_confirmed: `review_memory_inbox action=promote group_id={group_id}`",
        "- after_promote_preview: `curator_workbench action=preview_hints`",
        "- after_promote_materialize: `curator_workbench action=materialize_hints`",
        f"- after_materialize_verify: `curator_workbench action=graph memory_key={key}`",
        f"- reject_if_noisy: `review_memory_inbox action=reject group_id={group_id} reason=<reason>`",
    ]


def _command_query(key: str, value: str) -> str:
    query = f"{key} {value}".strip().replace('"', "'")
    return query[:180]


async def _recall_context(kwargs: dict[str, Any], group: dict[str, Any], limit: int) -> str:
    key = str(group.get("key") or "")
    value = str(group.get("value") or "")
    query = _command_query(key, value)
    if not query:
        return ""
    from src.tools.recall_memories import run as recall_run

    return await recall_run(
        query=query,
        limit=min(limit, 8),
        source="",
        min_score=0.2,
        include_graph_context=True,
        known_entities=[],
        _repos=kwargs.get("_repos"),
    )


async def _canonical_matches(kwargs: dict[str, Any], group: dict[str, Any], limit: int = 5) -> list[dict[str, Any]]:
    repo = _memory_index_repo(kwargs)
    if repo is None:
        return []
    key = str(group.get("key") or "").strip()
    value = str(group.get("value") or "").strip()
    queries = [item for item in (key, value) if item]
    matches: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for query in queries:
        try:
            rows = await repo.search(query)
        except Exception:
            continue
        for row in rows or []:
            row_key = str(row.get("key") or "")
            if not row_key or row_key in seen_keys:
                continue
            seen_keys.add(row_key)
            matches.append(dict(row))
            if len(matches) >= limit:
                return matches
    return matches


def _memory_index_repo(kwargs: dict[str, Any]) -> Any | None:
    repos = kwargs.get("_repos")
    memory = getattr(repos, "memory", None) if repos is not None else None
    repo = getattr(memory, "memory_index", None) if memory is not None else None
    if repo is not None:
        return repo
    try:
        from src.memory.repos_memory.memory_index_repo import GlobalMemoryIndexRepository

        return GlobalMemoryIndexRepository()
    except Exception:
        return None


async def _canonical_writer(kwargs: dict[str, Any], key: str, value: str) -> Any:
    from src.tools.save_memory import run as save_memory_run

    return await save_memory_run(
        key=key,
        value=value,
        scope="canonical",
        _repos=kwargs.get("_repos"),
        _root=_root(kwargs),
        _force_local_write=bool(kwargs.get("_force_local_write", False)),
    )


async def run(**kwargs) -> str:
    action = str(kwargs.get("action") or "list")
    group_id = str(kwargs.get("group_id") or "").strip()
    limit = min(int(kwargs.get("limit", 20)), 50)

    try:
        from src.memory.curator.inbox_review import (
            find_inbox_group,
            list_inbox_groups,
            promote_inbox_group,
            reject_inbox_group,
        )

        if action == "list":
            groups = list_inbox_groups(
                root=_root(kwargs),
                status=str(kwargs.get("status", "pending")),
                limit=limit,
            )
            if not groups:
                return "No memory inbox groups found."
            lines = ["## Memory inbox groups"]
            lines.extend(_format_group(group) for group in groups)
            return "\n".join(lines)

        if not group_id:
            return "[ERROR] group_id is required."

        if action == "inspect":
            group = find_inbox_group(
                group_id,
                root=_root(kwargs),
                status=str(kwargs.get("status", "pending")),
            )
            if group is None:
                return f"[ERROR] inbox group not found: {group_id}"
            canonical_matches = await _canonical_matches(kwargs, group, limit=5)
            lines = _format_inspect_group(group, canonical_matches=canonical_matches)
            if bool(kwargs.get("include_recall_context", False)):
                context = await _recall_context(kwargs, group, limit)
                if context:
                    lines.extend(["", "### Recall Context", context])
            return "\n".join(lines)

        if action == "promote":
            updated = await promote_inbox_group(
                group_id,
                lambda key, value: _canonical_writer(kwargs, key, value),
                root=_root(kwargs),
                key=str(kwargs.get("key") or ""),
                value=str(kwargs.get("value") or ""),
            )
            return (
                f"[OK] Promoted inbox group `{updated.get('group_id')}` "
                f"to `{updated.get('key')}` target=`{updated.get('target_id', '')}` "
                f"relations={len(updated.get('relation_hints') or [])} "
                f"updated={updated.get('updated_count')} "
                f"next=`{updated.get('preview_command', '')}` "
                f"then=`{updated.get('materialize_command', '')}` "
                f"verify=`{updated.get('verify_graph_command', '')}`"
            )

        if action == "reject":
            updated = reject_inbox_group(
                group_id,
                str(kwargs.get("reason") or ""),
                root=_root(kwargs),
            )
            return (
                f"[OK] Rejected inbox group `{updated.get('group_id')}` "
                f"updated={updated.get('updated_count')}"
            )

        return f"[ERROR] unknown action: {action}"
    except Exception as exc:
        return f"[ERROR] Failed to review memory inbox: {exc}"
