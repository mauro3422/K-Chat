"""Tool: review_recall_candidate - review active recall link candidates."""

from __future__ import annotations

from typing import Any

DEFINITION: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "review_recall_candidate",
        "description": (
            "Review recall link candidates materialized by the curator tracer. "
            "Can list, reject, apply a suggested target, mark missing metadata, "
            "complete metadata, or promote a reviewed candidate into the entity relation graph."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to a memory/candidates/*.recall_links.jsonl file.",
                },
                "action": {
                    "type": "string",
                    "enum": [
                        "list",
                        "suggest_metadata",
                        "apply_target",
                        "complete_metadata",
                        "preview_relations",
                        "reject",
                        "needs_metadata",
                        "link_neighbor",
                        "promote",
                        "promote_ready",
                    ],
                    "description": "Review action to perform.",
                    "default": "list",
                },
                "candidate_id": {
                    "type": "string",
                    "description": "Candidate id for reject/needs_metadata/promote.",
                    "default": "",
                },
                "reason": {
                    "type": "string",
                    "description": "Review reason for reject or needs_metadata.",
                    "default": "",
                },
                "missing_fields": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Missing metadata fields.",
                    "default": [],
                },
                "source_id": {
                    "type": "string",
                    "description": "Graph source entity/artifact id for metadata completion or promotion.",
                    "default": "",
                },
                "target_id": {
                    "type": "string",
                    "description": "Graph target entity/artifact id for apply_target, metadata completion, or promotion.",
                    "default": "",
                },
                "target_source": {
                    "type": "string",
                    "description": "Source of the selected target suggestion.",
                    "default": "",
                },
                "target_score": {
                    "type": "number",
                    "description": "Score of the selected target suggestion.",
                },
                "target_reason": {
                    "type": "string",
                    "description": "Reason attached to the selected target suggestion.",
                    "default": "",
                },
                "neighbor_candidate_id": {
                    "type": "string",
                    "description": "Neighbor candidate id for link_neighbor.",
                    "default": "",
                },
                "relation_type": {
                    "type": "string",
                    "description": "Relation type for metadata completion, promotion, or link_neighbor.",
                    "default": "",
                },
                "weight": {
                    "type": "number",
                    "description": "Optional relation weight.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum list results.",
                    "default": 20,
                },
            },
            "required": ["path"],
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


def _format_candidate(candidate: dict[str, Any]) -> str:
    return (
        f"- `{candidate.get('candidate_id', '')}` "
        f"[{candidate.get('status', 'pending')}] "
        f"{candidate.get('relation_type', '')} "
        f"score={candidate.get('link_score', 0)} "
        f"query={candidate.get('query', '')}"
    )


async def run(**kwargs) -> str:
    path = kwargs.get("path", "").strip()
    action = kwargs.get("action", "list")
    candidate_id = kwargs.get("candidate_id", "").strip()
    limit = min(int(kwargs.get("limit", 20)), 50)

    if not path:
        return "[ERROR] path cannot be empty."

    try:
        from src.memory.curator.recall_review import (
            apply_candidate_target,
            apply_candidate_neighbor_relation,
            complete_candidate_metadata,
            load_candidates,
            mark_needs_metadata,
            preview_candidate_relations,
            promote_candidate,
            promote_ready_candidate,
            reject_candidate,
            suggest_metadata,
        )

        if action == "list":
            candidates = load_candidates(path)
            if not candidates:
                return "No recall candidates found."
            lines = ["## Recall candidates"]
            lines.extend(_format_candidate(candidate) for candidate in candidates[:limit])
            return "\n".join(lines)

        if not candidate_id:
            return "[ERROR] candidate_id is required for this action."

        if action == "suggest_metadata":
            repo = await _entity_repo_from_kwargs(kwargs)
            suggestion = await suggest_metadata(path, candidate_id, repo, limit=limit)
            lines = [
                f"## Metadata suggestions for `{candidate_id}`",
                f"- relation_type: `{suggestion.get('relation_type', '')}`",
                f"- suggested_source_id: `{suggestion.get('suggested_source_id', '')}`",
                f"- suggested_target_id: `{suggestion.get('suggested_target_id', '')}`",
            ]
            missing = suggestion.get("missing_fields", [])
            if missing:
                lines.append(f"- missing: `{', '.join(missing)}`")
            entities = suggestion.get("entities", [])
            if entities:
                lines.append("")
                lines.append("### Entities")
                for entity in entities:
                    lines.append(
                        f"- `{entity.get('id', '')}` {entity.get('name', '')} "
                        f"({entity.get('entity_type', '')})"
                    )
            return "\n".join(lines)

        if action == "apply_target":
            updated = apply_candidate_target(
                path,
                candidate_id,
                kwargs.get("target_id", ""),
                source=kwargs.get("target_source", ""),
                score=kwargs.get("target_score"),
                reason=kwargs.get("target_reason", ""),
            )
            return (
                f"[OK] Applied target `{updated.get('target_id')}` to `{candidate_id}` "
                f"status={updated.get('status')}"
            )

        if action == "complete_metadata":
            updated = complete_candidate_metadata(
                path,
                candidate_id,
                source_id=kwargs.get("source_id", ""),
                target_id=kwargs.get("target_id", ""),
                relation_type=kwargs.get("relation_type", ""),
                weight=kwargs.get("weight"),
                reason=kwargs.get("reason", ""),
            )
            missing = updated.get("missing_fields") or []
            suffix = f" missing={', '.join(missing)}" if missing else ""
            return (
                f"[OK] Completed metadata for `{candidate_id}` "
                f"status={updated.get('status')}{suffix}"
            )

        if action == "preview_relations":
            preview = preview_candidate_relations(path, candidate_id)
            lines = [
                f"## Relation preview `{candidate_id}`",
                f"- status: `{preview.get('status', '')}`",
                f"- promote_command: `{preview.get('promote_command', '')}`",
                "",
                "### Primary",
            ]
            primary = preview.get("primary") or {}
            lines.append(
                f"- `{primary.get('source_id', '')}` "
                f"-[{primary.get('relation_type', '')} {primary.get('weight', '')}]-> "
                f"`{primary.get('target_id', '')}` "
                f"needs_resolution={primary.get('needs_resolution', False)}"
            )
            proposed = preview.get("proposed_relations") or []
            if proposed:
                lines.extend(["", "### Proposed Relations"])
                for relation in proposed[:limit]:
                    blocked = " blocked" if relation.get("needs_resolution") else ""
                    lines.append(
                        f"- `{relation.get('source_id', '')}` "
                        f"-[{relation.get('relation_type', '')}{blocked}]-> "
                        f"`{relation.get('target_id', '')}` "
                        f"weight={relation.get('weight', '')}"
                    )
                    evidence = str(relation.get("evidence") or "").strip()
                    if evidence:
                        lines.append(f"  evidence: {evidence[:220]}")
            lines.append("")
            lines.append(f"- promotable: `{len(preview.get('promotable_relations') or [])}`")
            lines.append(f"- blocked: `{len(preview.get('blocked_relations') or [])}`")
            return "\n".join(lines)

        if action == "reject":
            updated = reject_candidate(
                path,
                candidate_id,
                kwargs.get("reason", ""),
            )
            return f"[OK] Rejected `{candidate_id}`: {updated.get('review_reason', '')}"

        if action == "needs_metadata":
            missing = kwargs.get("missing_fields") or []
            updated = mark_needs_metadata(path, candidate_id, list(missing))
            return (
                f"[OK] `{candidate_id}` needs metadata: "
                f"{', '.join(updated.get('missing_fields', []))}"
            )

        if action == "link_neighbor":
            updated = apply_candidate_neighbor_relation(
                path,
                candidate_id,
                kwargs.get("neighbor_candidate_id", ""),
                relation_type=kwargs.get("relation_type", "REFINES"),
                reason=kwargs.get("reason", ""),
                score=kwargs.get("target_score"),
            )
            relation = (updated.get("candidate_neighbor_relations") or [])[-1]
            return (
                f"[OK] Linked `{candidate_id}` "
                f"-[{relation.get('relation_type', '')}]-> "
                f"`{kwargs.get('neighbor_candidate_id', '')}`"
            )

        if action == "promote":
            repo = await _entity_repo_from_kwargs(kwargs)
            updated = await promote_candidate(
                path,
                candidate_id,
                repo,
                source_id=kwargs.get("source_id", ""),
                target_id=kwargs.get("target_id", ""),
                relation_type=kwargs.get("relation_type", ""),
                weight=kwargs.get("weight"),
            )
            return (
                f"[OK] Promoted `{candidate_id}` to `{updated.get('relation_type')}` "
                f"({updated.get('source_id')} -> {updated.get('target_id')})"
            )

        if action == "promote_ready":
            repo = await _entity_repo_from_kwargs(kwargs)
            updated = await promote_ready_candidate(
                path,
                candidate_id,
                repo,
                weight=kwargs.get("weight"),
            )
            return (
                f"[OK] Promoted ready candidate `{candidate_id}` to `{updated.get('relation_type')}` "
                f"({updated.get('source_id')} -> {updated.get('target_id')})"
            )

        return f"[ERROR] unknown action: {action}"
    except Exception as exc:
        return f"[ERROR] Failed to review recall candidate: {exc}"
