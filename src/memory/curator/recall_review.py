"""Review and promote recall link candidates."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from src.memory.curator.curation_events import append_curation_decision


def load_candidates(path: str | Path) -> list[dict[str, Any]]:
    """Load a recall candidate JSONL file."""

    candidate_path = Path(path)
    if not candidate_path.exists():
        return []

    candidates: list[dict[str, Any]] = []
    with candidate_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                candidates.append(payload)
    return candidates


def write_candidates(path: str | Path, candidates: list[Mapping[str, Any]]) -> None:
    """Overwrite a recall candidate JSONL file."""

    candidate_path = Path(path)
    candidate_path.parent.mkdir(parents=True, exist_ok=True)
    with candidate_path.open("w", encoding="utf-8") as handle:
        for candidate in candidates:
            handle.write(json.dumps(dict(candidate), ensure_ascii=False, sort_keys=True) + "\n")


def _update_candidate(
    candidates: list[dict[str, Any]],
    candidate_id: str,
    updates: Mapping[str, Any],
) -> dict[str, Any]:
    for candidate in candidates:
        if candidate.get("candidate_id") == candidate_id:
            candidate.update(dict(updates))
            return candidate
    raise ValueError(f"candidate not found: {candidate_id}")


def _query_terms(query: str) -> list[str]:
    terms: list[str] = []
    for raw in query.replace("-", " ").replace("_", " ").split():
        term = raw.strip(".,;:!?()[]{}\"'`").strip()
        if len(term) >= 4 and term.lower() not in {"para", "como", "esto", "esta"}:
            terms.append(term)
    return terms[:6]


def query_terms(query: str) -> list[str]:
    """Return curator-friendly query terms for metadata/entity search."""

    return _query_terms(query)


def _candidate_provenance(candidate: Mapping[str, Any], path: str | Path) -> dict[str, Any]:
    return {
        "candidate_id": candidate.get("candidate_id", ""),
        "candidate_type": candidate.get("type", ""),
        "source": candidate.get("source", ""),
        "session_id": candidate.get("session_id", ""),
        "channel": candidate.get("channel", ""),
        "artifact": candidate.get("artifact", str(path)),
        "candidate_path": str(path),
        "timestamp": candidate.get("timestamp", ""),
        "created_at": candidate.get("created_at", ""),
    }


def _candidate_metadata(candidate: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "query": candidate.get("query", ""),
        "intent": candidate.get("intent", ""),
        "trigger": candidate.get("trigger", ""),
        "link_action": candidate.get("link_action", ""),
        "link_score": candidate.get("link_score", 0.0),
        "link_reasons": candidate.get("link_reasons", []),
    }


def preview_candidate_relations(path: str | Path, candidate_id: str) -> dict[str, Any]:
    """Preview primary and proposed graph relations before promotion."""

    candidates = load_candidates(path)
    candidate = next((c for c in candidates if c.get("candidate_id") == candidate_id), None)
    if candidate is None:
        raise ValueError(f"candidate not found: {candidate_id}")

    primary = {
        "source_id": str(candidate.get("source_id") or ""),
        "target_id": str(candidate.get("target_id") or ""),
        "relation_type": str(candidate.get("relation_type") or ""),
        "weight": float(candidate.get("weight") or candidate.get("link_score") or 0.0),
        "needs_resolution": _target_requires_resolution(candidate, str(candidate.get("target_id") or "")),
        "kind": "primary",
    }
    proposed = candidate.get("proposed_relations")
    proposed_items = [dict(item) for item in proposed if isinstance(item, Mapping)] if isinstance(proposed, list) else []
    promotable = []
    blocked = []
    for relation in proposed_items:
        source = str(relation.get("source_id") or "").strip()
        target = str(relation.get("target_id") or "").strip()
        rel_type = str(relation.get("relation_type") or "").strip()
        needs_resolution = bool(relation.get("needs_resolution"))
        if source and target and rel_type and not needs_resolution:
            promotable.append(relation)
        else:
            blocked.append(relation)

    return {
        "candidate_id": candidate_id,
        "status": candidate.get("status", ""),
        "primary": primary,
        "proposed_relations": proposed_items,
        "promotable_relations": promotable,
        "blocked_relations": blocked,
        "promote_command": (
            f"review_recall_candidate action=promote_ready path={path} candidate_id={candidate_id}"
            if str(candidate.get("status") or "") == "ready_for_promotion"
            else f"review_recall_candidate action=promote path={path} candidate_id={candidate_id}"
        ),
    }


async def _promote_proposed_relations(
    candidate: Mapping[str, Any],
    entity_repo: Any,
    path: str | Path,
    timestamp: str,
    *,
    primary: tuple[str, str, str],
) -> list[str]:
    proposed = candidate.get("proposed_relations")
    if not isinstance(proposed, list):
        return []

    promoted_ids: list[str] = []
    seen: set[tuple[str, str, str]] = {primary}
    for relation in proposed:
        if not isinstance(relation, Mapping):
            continue
        if relation.get("needs_resolution"):
            continue
        source = str(relation.get("source_id") or "").strip()
        target = str(relation.get("target_id") or "").strip()
        rel_type = str(relation.get("relation_type") or "").strip()
        if not source or not target or not rel_type:
            continue
        identity = (source, target, rel_type)
        if identity in seen:
            continue
        seen.add(identity)
        rel_weight = float(relation.get("weight") or candidate.get("link_score") or 1.0)
        await entity_repo.upsert_relation(
            source_id=source,
            target_id=target,
            relation_type=rel_type,
            weight=rel_weight,
            timestamp=timestamp,
        )
        if hasattr(entity_repo, "upsert_curated_relation"):
            relation_id = await entity_repo.upsert_curated_relation(
                source_id=source,
                target_id=target,
                relation_type=rel_type,
                weight=rel_weight,
                candidate_id=str(candidate.get("candidate_id") or ""),
                provenance={
                    **_candidate_provenance(candidate, path),
                    "relation_provenance": relation.get("provenance", ""),
                },
                evidence=str(relation.get("evidence") or candidate.get("query") or candidate.get("result_excerpt") or ""),
                metadata={
                    **_candidate_metadata(candidate),
                    "proposed_relation": dict(relation),
                },
                timestamp=timestamp,
            )
            promoted_ids.append(relation_id)
    return promoted_ids


def _target_requires_resolution(candidate: Mapping[str, Any], target_id: str) -> bool:
    if candidate.get("target_needs_resolution") is True:
        return True
    return target_id in {"memory:canonical", "memory:semantic-neighbor"}


def _is_resolved_memory_target(target_id: str) -> bool:
    return target_id.startswith("memory:") and target_id not in {
        "memory:canonical",
        "memory:semantic-neighbor",
    }


async def _promote_canonical_trace_relation(
    candidate: Mapping[str, Any],
    entity_repo: Any,
    path: str | Path,
    timestamp: str,
    *,
    target_id: str,
    weight: float,
) -> str:
    """Persist candidate -> canonical memory trace when target is concrete."""

    if not _is_resolved_memory_target(target_id):
        return ""

    candidate_id = str(candidate.get("candidate_id") or "")
    if not candidate_id:
        return ""
    source_id = f"candidate:{candidate_id}"
    await entity_repo.upsert_relation(
        source_id=source_id,
        target_id=target_id,
        relation_type="PROMOTED_TO",
        weight=weight,
        timestamp=timestamp,
    )
    if not hasattr(entity_repo, "upsert_curated_relation"):
        return ""
    return await entity_repo.upsert_curated_relation(
        source_id=source_id,
        target_id=target_id,
        relation_type="PROMOTED_TO",
        weight=weight,
        candidate_id=candidate_id,
        provenance={
            **_candidate_provenance(candidate, path),
            "relation_provenance": "promotion_trace",
        },
        evidence=str(candidate.get("query") or candidate.get("result_excerpt") or ""),
        metadata={
            **_candidate_metadata(candidate),
            "canonical_target": target_id,
        },
        timestamp=timestamp,
    )


def _decision_root(path: str | Path) -> Path:
    candidate_path = Path(path).resolve()
    parts = candidate_path.parts
    if "memory" in parts:
        return Path(*parts[: parts.index("memory")])
    return candidate_path.parents[4] if len(candidate_path.parents) >= 5 else candidate_path.parent


def _append_candidate_decision(
    path: str | Path,
    candidate: Mapping[str, Any],
    action: str,
    timestamp: str,
    **extra: Any,
) -> dict[str, Any]:
    payload = {
        "kind": "memory_candidate",
        "action": action,
        "candidate_id": candidate.get("candidate_id", ""),
        "candidate_type": candidate.get("type", ""),
        "source": candidate.get("source", ""),
        "status": candidate.get("status", ""),
        "relation_type": candidate.get("relation_type", ""),
        "source_id": candidate.get("source_id", ""),
        "target_id": candidate.get("target_id", ""),
        "query": candidate.get("query", ""),
        "candidate_path": str(path),
        **extra,
    }
    return append_curation_decision(payload, root=_decision_root(path), timestamp=timestamp)


async def suggest_metadata(
    path: str | Path,
    candidate_id: str,
    entity_repo: Any,
    limit: int = 8,
) -> dict[str, Any]:
    """Suggest graph metadata for a recall candidate without mutating it."""

    candidates = load_candidates(path)
    candidate = next((c for c in candidates if c.get("candidate_id") == candidate_id), None)
    if candidate is None:
        raise ValueError(f"candidate not found: {candidate_id}")

    query = str(candidate.get("query") or "")
    searches = [query, *query_terms(query)] if query else []
    seen: set[str] = set()
    entities: list[dict[str, Any]] = []
    for search in searches:
        if not search:
            continue
        for entity in await entity_repo.search_entities(search, limit=limit):
            entity_id = str(entity.get("id") or entity.get("entity_id") or "")
            if not entity_id or entity_id in seen:
                continue
            seen.add(entity_id)
            entities.append(entity)
            if len(entities) >= limit:
                break
        if len(entities) >= limit:
            break

    relation_type = str(candidate.get("relation_type") or "RECALLS")
    return {
        "candidate_id": candidate_id,
        "relation_type": relation_type,
        "query": query,
        "entities": entities,
        "suggested_source_id": entities[0].get("id", "") if entities else "",
        "suggested_target_id": entities[1].get("id", "") if len(entities) > 1 else "",
        "missing_fields": [
            field for field, value in (
                ("source_id", candidate.get("source_id") or (entities[0].get("id") if entities else "")),
                ("target_id", candidate.get("target_id") or (entities[1].get("id") if len(entities) > 1 else "")),
                ("relation_type", relation_type),
            )
            if not value
        ],
    }


def reject_candidate(
    path: str | Path,
    candidate_id: str,
    reason: str,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Mark a recall candidate as rejected."""

    ts = timestamp or datetime.now().isoformat(timespec="seconds")
    candidates = load_candidates(path)
    updated = _update_candidate(
        candidates,
        candidate_id,
        {
            "status": "rejected",
            "reviewed_at": ts,
            "review_reason": reason,
        },
    )
    write_candidates(path, candidates)
    updated["decision_event"] = _append_candidate_decision(
        path,
        updated,
        "reject",
        ts,
        reason=reason,
    )
    write_candidates(path, candidates)
    return updated


def mark_needs_metadata(
    path: str | Path,
    candidate_id: str,
    missing_fields: list[str],
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Mark a recall candidate as blocked on curator metadata."""

    ts = timestamp or datetime.now().isoformat(timespec="seconds")
    candidates = load_candidates(path)
    updated = _update_candidate(
        candidates,
        candidate_id,
        {
            "status": "needs_metadata",
            "reviewed_at": ts,
            "missing_fields": list(missing_fields),
        },
    )
    write_candidates(path, candidates)
    updated["decision_event"] = _append_candidate_decision(
        path,
        updated,
        "needs_metadata",
        ts,
        missing_fields=list(missing_fields),
    )
    write_candidates(path, candidates)
    return updated


def _merge_primary_relation(
    candidate: Mapping[str, Any],
    *,
    source_id: str,
    target_id: str,
    relation_type: str,
    weight: float | None,
    timestamp: str,
) -> list[Any]:
    proposed = candidate.get("proposed_relations")
    relations = list(proposed) if isinstance(proposed, list) else []
    if not source_id or not target_id or not relation_type:
        return relations

    primary = {
        "source_id": source_id,
        "target_id": target_id,
        "relation_type": relation_type,
        "needs_resolution": False,
        "provenance": "curator_metadata_complete",
        "reviewed_at": timestamp,
    }
    if weight is not None:
        primary["weight"] = float(weight)

    identity = (source_id, target_id, relation_type)
    replaced = False
    merged: list[Any] = []
    for relation in relations:
        if not isinstance(relation, dict):
            merged.append(relation)
            continue
        rel_copy = dict(relation)
        rel_identity = (
            str(rel_copy.get("source_id") or ""),
            str(rel_copy.get("target_id") or ""),
            str(rel_copy.get("relation_type") or ""),
        )
        candidate_source = f"candidate:{candidate.get('candidate_id', '')}"
        placeholder_target = rel_copy.get("target_id") in {"memory:canonical", "memory:semantic-neighbor"}
        matches_placeholder = (
            rel_copy.get("needs_resolution")
            and str(rel_copy.get("source_id") or "") in {source_id, candidate_source}
            and str(rel_copy.get("relation_type") or "") == relation_type
            and placeholder_target
        )
        if rel_identity == identity or matches_placeholder:
            rel_copy.update(primary)
            replaced = True
        merged.append(rel_copy)

    if not replaced:
        merged.append(primary)
    return merged


def complete_candidate_metadata(
    path: str | Path,
    candidate_id: str,
    source_id: str = "",
    target_id: str = "",
    relation_type: str = "",
    weight: float | None = None,
    reason: str = "",
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Apply curator metadata without promoting the candidate yet."""

    ts = timestamp or datetime.now().isoformat(timespec="seconds")
    candidates = load_candidates(path)
    candidate = next((c for c in candidates if c.get("candidate_id") == candidate_id), None)
    if candidate is None:
        raise ValueError(f"candidate not found: {candidate_id}")

    source = str(source_id or candidate.get("source_id") or "").strip()
    target = str(target_id or candidate.get("target_id") or "").strip()
    rel_type = str(relation_type or candidate.get("relation_type") or "").strip().upper()
    rel_weight = float(weight if weight is not None else candidate.get("weight") or candidate.get("link_score") or 0.0)

    missing = [
        name for name, value in (
            ("source_id", source),
            ("target_id", target),
            ("relation_type", rel_type),
        )
        if not value
    ]
    if target_id:
        needs_resolution = target in {"memory:canonical", "memory:semantic-neighbor"}
    else:
        needs_resolution = bool(target and _target_requires_resolution(candidate, target))
    if needs_resolution and "target_id" not in missing:
        missing.append("target_id")
    status = "ready_for_promotion" if not missing else "needs_metadata"

    completed_fields = [
        name for name, value in (
            ("source_id", source_id),
            ("target_id", target_id),
            ("relation_type", relation_type),
            ("weight", weight),
        )
        if value not in {"", None}
    ]
    updates: dict[str, Any] = {
        "status": status,
        "reviewed_at": ts,
        "source_id": source,
        "target_id": target,
        "relation_type": rel_type,
        "target_needs_resolution": needs_resolution,
        "missing_fields": missing,
        "completed_metadata": {
            "source_id": source,
            "target_id": target,
            "relation_type": rel_type,
            "weight": rel_weight,
            "reason": reason,
            "completed_at": ts,
        },
    }
    if weight is not None:
        updates["weight"] = rel_weight
    if not missing:
        updates["proposed_relations"] = _merge_primary_relation(
            candidate,
            source_id=source,
            target_id=target,
            relation_type=rel_type,
            weight=rel_weight if weight is not None else None,
            timestamp=ts,
        )

    updated = _update_candidate(candidates, candidate_id, updates)
    write_candidates(path, candidates)
    updated["decision_event"] = _append_candidate_decision(
        path,
        updated,
        "complete_metadata",
        ts,
        completed_fields=completed_fields,
        missing_fields=missing,
        completed_metadata=updates["completed_metadata"],
        reason=reason,
    )
    write_candidates(path, candidates)
    return updated


def apply_candidate_target(
    path: str | Path,
    candidate_id: str,
    target_id: str,
    source: str = "",
    score: float | None = None,
    reason: str = "",
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Apply a curator-selected target suggestion to a candidate."""

    if not target_id:
        raise ValueError("target_id cannot be empty")

    ts = timestamp or datetime.now().isoformat(timespec="seconds")
    candidates = load_candidates(path)
    candidate = next((c for c in candidates if c.get("candidate_id") == candidate_id), None)
    if candidate is None:
        raise ValueError(f"candidate not found: {candidate_id}")

    source_id = str(candidate.get("source_id") or "")
    relation_type = str(candidate.get("relation_type") or "")
    missing = [
        name for name, value in (
            ("source_id", source_id),
            ("relation_type", relation_type),
        )
        if not value
    ]
    status = "ready_for_promotion" if not missing else "needs_metadata"
    updates: dict[str, Any] = {
        "target_id": target_id,
        "target_needs_resolution": False,
        "status": status,
        "reviewed_at": ts,
        "selected_target": {
            "target_id": target_id,
            "source": source,
            "score": score,
            "reason": reason,
            "selected_at": ts,
        },
    }
    if missing:
        updates["missing_fields"] = missing
    else:
        updates["missing_fields"] = []

    proposed = candidate.get("proposed_relations")
    if isinstance(proposed, list):
        updated_relations: list[Any] = []
        for relation in proposed:
            if not isinstance(relation, dict):
                updated_relations.append(relation)
                continue
            rel_copy = dict(relation)
            if rel_copy.get("needs_resolution") and rel_copy.get("target_id") in {
                "memory:canonical",
                "memory:semantic-neighbor",
            }:
                rel_copy["target_id"] = target_id
                rel_copy["needs_resolution"] = False
                rel_copy["resolved_at"] = ts
            updated_relations.append(rel_copy)
        updates["proposed_relations"] = updated_relations

    updated = _update_candidate(candidates, candidate_id, updates)
    write_candidates(path, candidates)
    updated["decision_event"] = _append_candidate_decision(
        path,
        updated,
        "apply_target",
        ts,
        selected_target=updates["selected_target"],
    )
    write_candidates(path, candidates)
    return updated


def apply_candidate_neighbor_relation(
    path: str | Path,
    candidate_id: str,
    neighbor_candidate_id: str,
    relation_type: str = "REFINES",
    reason: str = "",
    score: float | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Record a curator relation between two review candidates."""

    if not neighbor_candidate_id:
        raise ValueError("neighbor_candidate_id cannot be empty")

    normalized_relation = (relation_type or "REFINES").strip().upper()
    allowed = {"REFINES", "DUPLICATES", "SUPPORTS", "CONTRADICTS", "RELATED_TO"}
    if normalized_relation not in allowed:
        raise ValueError(f"unsupported neighbor relation_type: {relation_type}")

    ts = timestamp or datetime.now().isoformat(timespec="seconds")
    candidates = load_candidates(path)
    candidate = next((c for c in candidates if c.get("candidate_id") == candidate_id), None)
    if candidate is None:
        raise ValueError(f"candidate not found: {candidate_id}")
    if not any(c.get("candidate_id") == neighbor_candidate_id for c in candidates):
        raise ValueError(f"neighbor candidate not found: {neighbor_candidate_id}")

    relation = {
        "source_id": f"candidate:{candidate_id}",
        "target_id": f"candidate:{neighbor_candidate_id}",
        "relation_type": normalized_relation,
        "weight": float(score if score is not None else 0.7),
        "provenance": "curator_neighbor_review",
        "reason": reason,
        "reviewed_at": ts,
    }
    existing_relations = candidate.get("candidate_neighbor_relations")
    neighbor_relations = list(existing_relations) if isinstance(existing_relations, list) else []
    identity = (relation["source_id"], relation["target_id"], relation["relation_type"])
    if not any(
        isinstance(item, Mapping)
        and (
            item.get("source_id"),
            item.get("target_id"),
            item.get("relation_type"),
        ) == identity
        for item in neighbor_relations
    ):
        neighbor_relations.append(relation)

    updates: dict[str, Any] = {
        "reviewed_at": ts,
        "candidate_neighbor_relations": neighbor_relations,
    }
    if normalized_relation == "DUPLICATES":
        updates["status"] = "duplicate"
        updates["duplicate_of"] = neighbor_candidate_id
        updates["review_reason"] = reason or "semantic_candidate_duplicate"

    updated = _update_candidate(candidates, candidate_id, updates)
    write_candidates(path, candidates)
    updated["decision_event"] = _append_candidate_decision(
        path,
        updated,
        "link_neighbor",
        ts,
        neighbor_candidate_id=neighbor_candidate_id,
        neighbor_relation=relation,
        relation_hints=[relation],
        reason=reason,
    )
    write_candidates(path, candidates)
    return updated


async def promote_candidate(
    path: str | Path,
    candidate_id: str,
    entity_repo: Any,
    source_id: str = "",
    target_id: str = "",
    relation_type: str = "",
    weight: float | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Promote a reviewed recall candidate into the entity graph."""

    ts = timestamp or datetime.now().isoformat(timespec="seconds")
    candidates = load_candidates(path)
    candidate = next((c for c in candidates if c.get("candidate_id") == candidate_id), None)
    if candidate is None:
        raise ValueError(f"candidate not found: {candidate_id}")

    source = source_id or str(candidate.get("source_id") or "")
    target = target_id or str(candidate.get("target_id") or "")
    rel_type = relation_type or str(candidate.get("relation_type") or "")
    missing = [
        name for name, value in (
            ("source_id", source),
            ("target_id", target),
            ("relation_type", rel_type),
        )
        if not value
    ]
    if missing:
        mark_needs_metadata(path, candidate_id, missing, timestamp=ts)
        raise ValueError(f"missing metadata: {', '.join(missing)}")
    if _target_requires_resolution(candidate, target):
        mark_needs_metadata(path, candidate_id, ["target_id"], timestamp=ts)
        raise ValueError("target metadata needs resolution")

    rel_weight = float(weight if weight is not None else candidate.get("link_score") or 1.0)
    await entity_repo.upsert_relation(
        source_id=source,
        target_id=target,
        relation_type=rel_type,
        weight=rel_weight,
        timestamp=ts,
    )
    relation_id = ""
    if hasattr(entity_repo, "upsert_curated_relation"):
        relation_id = await entity_repo.upsert_curated_relation(
            source_id=source,
            target_id=target,
            relation_type=rel_type,
            weight=rel_weight,
            candidate_id=candidate_id,
            provenance=_candidate_provenance(candidate, path),
            evidence=str(candidate.get("query") or candidate.get("result_excerpt") or ""),
            metadata=_candidate_metadata(candidate),
            timestamp=ts,
        )
    proposed_relation_ids = await _promote_proposed_relations(
        candidate,
        entity_repo,
        path,
        ts,
        primary=(source, target, rel_type),
    )
    promoted_to_relation_id = await _promote_canonical_trace_relation(
        candidate,
        entity_repo,
        path,
        ts,
        target_id=target,
        weight=rel_weight,
    )
    updated = _update_candidate(
        candidates,
        candidate_id,
        {
            "status": "promoted",
            "reviewed_at": ts,
            "promoted_to": "memory_curated_relations" if relation_id else "entity_relations",
            "curated_relation_id": relation_id,
            "source_id": source,
            "target_id": target,
            "relation_type": rel_type,
            "weight": rel_weight,
            "promoted_proposed_relation_ids": proposed_relation_ids,
            "promoted_to_relation_id": promoted_to_relation_id,
        },
    )
    write_candidates(path, candidates)
    updated["decision_event"] = _append_candidate_decision(
        path,
        updated,
        "promote",
        ts,
        promoted_to=updated.get("promoted_to", ""),
        curated_relation_id=relation_id,
        promoted_proposed_relation_ids=proposed_relation_ids,
        promoted_to_relation_id=promoted_to_relation_id,
        weight=rel_weight,
    )
    write_candidates(path, candidates)
    return updated


async def promote_ready_candidate(
    path: str | Path,
    candidate_id: str,
    entity_repo: Any,
    weight: float | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Promote a candidate only after curator metadata has been resolved."""

    candidates = load_candidates(path)
    candidate = next((c for c in candidates if c.get("candidate_id") == candidate_id), None)
    if candidate is None:
        raise ValueError(f"candidate not found: {candidate_id}")
    if str(candidate.get("status") or "pending") != "ready_for_promotion":
        raise ValueError("candidate is not ready_for_promotion")
    return await promote_candidate(
        path,
        candidate_id,
        entity_repo,
        weight=weight,
        timestamp=timestamp,
    )
