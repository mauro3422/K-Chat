"""Curator workbench helpers for reviewable memory candidates."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping

from src.memory.content_hash import content_hash
from src.memory.curator.recall_review import load_candidates, query_terms, suggest_metadata
from src.memory.embedding_identity import memory_candidate_embedding_identity
from src.memory.memory_db_path import resolve_memory_db_path
from src.memory.repos_memory.work_catalog_repo import MemoryWorkCatalogRepository
from src.memory.curator.workbench import CandidateSignals, missing_metadata, recommend_action


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def candidate_root(root: str | Path | None = None) -> Path:
    """Return the root directory containing candidate artifacts."""

    base = Path(root) if root is not None else _project_root()
    return base / "memory" / "candidates"


def discover_candidate_files(root: str | Path | None = None) -> list[Path]:
    """Find reviewable candidate JSONL artifacts."""

    base = candidate_root(root)
    if not base.exists():
        return []
    return sorted(base.rglob("*.jsonl"), reverse=True)


def load_candidate_records(
    root: str | Path | None = None,
    paths: Iterable[str | Path] | None = None,
) -> list[dict[str, Any]]:
    """Load candidate JSONL records and attach their artifact path."""

    candidate_paths = [Path(path) for path in paths] if paths is not None else discover_candidate_files(root)
    records: list[dict[str, Any]] = []
    for path in candidate_paths:
        for candidate in load_candidates(path):
            payload = dict(candidate)
            payload.setdefault("candidate_id", "")
            payload["_candidate_path"] = str(path)
            records.append(payload)
    return records


def candidate_embedding_text(candidate: Mapping[str, Any]) -> str:
    """Render a stable semantic text packet for candidate recall."""

    trace = source_trace(candidate)
    lines = [
        f"candidate_id: {candidate.get('candidate_id', '')}",
        f"source: {candidate.get('source', '')}",
        f"type: {candidate.get('type', '')}",
        f"status: {candidate.get('status', 'pending')}",
        f"relation_type: {candidate.get('relation_type', '')}",
        f"source_id: {candidate.get('source_id', '')}",
        f"target_id: {candidate.get('target_id', '')}",
        f"query: {candidate.get('query') or _pattern_summary(candidate.get('pattern'))}",
        f"excerpt: {candidate.get('result_excerpt', '')}",
    ]
    entities = _entity_names(candidate.get("entities"))
    if entities:
        lines.append(f"entities: {', '.join(entities)}")
    if trace.get("derived_from"):
        lines.append(f"derived_from: {', '.join(str(item) for item in trace['derived_from'])}")

    proposed = candidate.get("proposed_relations") if isinstance(candidate.get("proposed_relations"), list) else []
    for relation in proposed[:12]:
        if not isinstance(relation, Mapping):
            continue
        lines.append(
            "proposed_relation: "
            f"{relation.get('source_id', '')} "
            f"-[{relation.get('relation_type', '')}]-> "
            f"{relation.get('target_id', '')} "
            f"weight={relation.get('weight', '')} "
            f"provenance={relation.get('provenance', '')}"
        )

    provenance = candidate.get("provenance") if isinstance(candidate.get("provenance"), Mapping) else {}
    if provenance:
        lines.append(f"provenance: {json.dumps(dict(provenance), ensure_ascii=False, sort_keys=True)}")

    return "\n".join(line for line in lines if line.strip() and not line.endswith(": ")).strip()


def discover_candidate_embedding_items(
    root: str | Path | None = None,
    paths: Iterable[str | Path] | None = None,
) -> list[dict[str, Any]]:
    """Discover candidates as vectorizable semantic packets."""

    items: list[dict[str, Any]] = []
    for candidate in load_candidate_records(root=root, paths=paths):
        candidate_id = str(candidate.get("candidate_id") or "").strip()
        if not candidate_id:
            continue
        text = candidate_embedding_text(candidate)
        if not text:
            continue
        items.append(
            {
                "candidate_id": candidate_id,
                "path": str(candidate.get("_candidate_path") or candidate.get("artifact") or ""),
                "source": str(candidate.get("source") or ""),
                "status": str(candidate.get("status") or "pending"),
                "relation_type": str(candidate.get("relation_type") or ""),
                "text": text,
                "content_hash": content_hash(text, limit=12000),
            }
        )
    return items


def _candidate_catalog_is_processed(
    catalog: MemoryWorkCatalogRepository,
    item: Mapping[str, Any],
) -> bool:
    identity = memory_candidate_embedding_identity()
    return catalog.is_processed(
        source="memory_candidate",
        source_key=str(item.get("candidate_id") or ""),
        item_idx=-1,
        content_hash=str(item.get("content_hash") or ""),
        **identity.as_catalog_kwargs(),
    )


def _candidate_catalog_mark(
    catalog: MemoryWorkCatalogRepository,
    item: Mapping[str, Any],
    status: str,
    *,
    vec_rowid: int | None = None,
    reason: str = "",
    source_node_id: str = "",
) -> None:
    identity = memory_candidate_embedding_identity()
    catalog.mark(
        source="memory_candidate",
        source_key=str(item.get("candidate_id") or ""),
        item_idx=-1,
        content_hash=str(item.get("content_hash") or ""),
        status=status,
        vec_rowid=vec_rowid,
        reason=reason,
        metadata={
            "path": item.get("path", ""),
            "candidate_source": item.get("source", ""),
            "candidate_status": item.get("status", ""),
            "relation_type": item.get("relation_type", ""),
        },
        source_node_id=source_node_id,
        **identity.as_catalog_kwargs(),
    )


async def vectorize_memory_candidates(
    root: str | Path | None = None,
    paths: Iterable[str | Path] | None = None,
    store: Any = None,
    catalog: MemoryWorkCatalogRepository | None = None,
    source_node_id: str = "",
) -> dict[str, int]:
    """Embed reviewable candidates as ``source=memory_candidate``."""

    from src.memory.embeddings.service import generate_embeddings_batch

    items = discover_candidate_embedding_items(root=root, paths=paths)
    result = {
        "candidates": len(items),
        "embedded": 0,
        "deduped": 0,
        "unchanged": 0,
        "failed": 0,
    }
    if not items:
        return result

    own_store = False
    if store is None:
        from src.memory.vector.store import VectorStore

        store = VectorStore(resolve_memory_db_path())
        own_store = True
    catalog = catalog or MemoryWorkCatalogRepository(resolve_memory_db_path())

    if not source_node_id:
        from src.memory.provenance import resolve_local_node_id

        source_node_id = resolve_local_node_id()

    pending: list[dict[str, Any]] = []
    try:
        for item in items:
            try:
                if _candidate_catalog_is_processed(catalog, item):
                    result["unchanged"] += 1
                    continue
                existing = store._get_conn().execute(
                    "SELECT rowid FROM vec_meta WHERE content_hash = ?",
                    (item["content_hash"],),
                ).fetchone()
                if existing is not None:
                    _candidate_catalog_mark(
                        catalog,
                        item,
                        "deduped",
                        vec_rowid=int(existing[0]),
                        reason="content_hash",
                        source_node_id=source_node_id,
                    )
                    result["deduped"] += 1
                    continue
                pending.append(item)
            except Exception:
                result["failed"] += 1

        if pending:
            vectors = await asyncio.to_thread(
                generate_embeddings_batch,
                [str(item["text"])[:4000] for item in pending],
            )
            for item, vector in zip(pending, vectors):
                try:
                    rowid = store.insert(
                        vector,
                        source="memory_candidate",
                        source_key=str(item["candidate_id"]),
                        exchange_idx=-1,
                        text=str(item["text"])[:4000],
                        metadata={
                            "path": item.get("path", ""),
                            "candidate_source": item.get("source", ""),
                            "candidate_status": item.get("status", ""),
                            "relation_type": item.get("relation_type", ""),
                        },
                        hash=str(item["content_hash"]),
                        content_hash=str(item["content_hash"]),
                        source_node_id=source_node_id,
                    )
                    _candidate_catalog_mark(
                        catalog,
                        item,
                        "embedded",
                        vec_rowid=rowid,
                        source_node_id=source_node_id,
                    )
                    result["embedded"] += 1
                except Exception:
                    result["failed"] += 1
    finally:
        if own_store:
            store.close()

    return result


def find_candidate(
    candidate_id: str,
    root: str | Path | None = None,
    path: str | Path | None = None,
) -> dict[str, Any] | None:
    """Find a candidate by id, optionally constrained to one artifact."""

    paths = [path] if path else None
    for candidate in load_candidate_records(root=root, paths=paths):
        if candidate.get("candidate_id") == candidate_id:
            return candidate
    return None


def candidate_signals(candidate: Mapping[str, Any]) -> CandidateSignals:
    """Infer conservative scoring signals from a candidate artifact."""

    confidence = float(
        candidate.get("link_score")
        or candidate.get("confidence")
        or candidate.get("score")
        or 0.0
    )
    urgency = str(candidate.get("urgency") or "").lower()
    source = str(candidate.get("source") or "")
    reasons = candidate.get("link_reasons") or []
    pattern_type = str(candidate.get("pattern_type") or "")
    metadata = {
        "source_id": candidate.get("source_id", ""),
        "target_id": candidate.get("target_id", ""),
        "relation_type": candidate.get("relation_type", ""),
    }
    metadata_complete = not missing_metadata(metadata, ("source_id", "target_id", "relation_type"))
    reinforcement = int(candidate.get("reinforcement_count") or candidate.get("times") or 0)
    pattern = candidate.get("pattern")
    if isinstance(pattern, Mapping):
        reinforcement = max(reinforcement, int(pattern.get("times") or 0))

    contradiction = 0.85 if str(candidate.get("relation_type") or "") == "CONTRADICTS" else 0.0
    entities = candidate.get("entities")
    entity_count = len(entities) if isinstance(entities, list) else 0
    proposed_relations = candidate.get("proposed_relations")
    relation_count = len(proposed_relations) if isinstance(proposed_relations, list) else 0

    importance = 0.75 if urgency == "high" or pattern_type == "debug_session" else 0.5
    if source == "session_summary" and entity_count:
        importance = max(importance, 0.62)
    durability = 0.7 if source in {"remember", "tracer"} else 0.5
    source_quality = 0.75 if source == "remember" else 0.65 if source == "tracer" else 0.5
    if source == "session_summary":
        durability = max(durability, 0.58)
        source_quality = max(source_quality, 0.6)
    if entity_count:
        source_quality = min(1.0, source_quality + min(entity_count, 4) * 0.03)
    if relation_count:
        source_quality = min(1.0, source_quality + 0.04)
    if isinstance(reasons, list) and reasons:
        source_quality = min(1.0, source_quality + 0.05)

    return CandidateSignals(
        confidence=confidence,
        importance=importance,
        durability=durability,
        recency=0.8,
        reinforcement_count=reinforcement,
        contradiction_score=contradiction,
        source_quality=source_quality,
        metadata_complete=metadata_complete,
    )


def candidate_card(candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Build a compact, sortable view of a candidate."""

    signals = candidate_signals(candidate)
    recommendation = recommend_action(signals)
    artifact = candidate.get("_candidate_path") or candidate.get("artifact", "")
    candidate_id = candidate.get("candidate_id", "")
    metadata = {
        "source_id": candidate.get("source_id", ""),
        "target_id": candidate.get("target_id", ""),
        "relation_type": candidate.get("relation_type", ""),
    }
    return {
        "candidate_id": candidate_id,
        "status": candidate.get("status", "pending"),
        "type": candidate.get("type", ""),
        "source": candidate.get("source", ""),
        "artifact": artifact,
        "query": candidate.get("query") or _pattern_summary(candidate.get("pattern")),
        "relation_type": candidate.get("relation_type", ""),
        "target_needs_resolution": bool(candidate.get("target_needs_resolution")),
        "entities": _entity_names(candidate.get("entities")),
        "source_channels": candidate.get("source_channels") if isinstance(candidate.get("source_channels"), Mapping) else {},
        "source_sessions": candidate.get("source_sessions") if isinstance(candidate.get("source_sessions"), list) else [],
        "proposed_relation_count": _sequence_count(candidate.get("proposed_relations")),
        "metadata_missing": list(missing_metadata(metadata, ("source_id", "target_id", "relation_type"))),
        "recommendation": recommendation.action,
        "score": recommendation.score,
        "reasons": list(recommendation.reasons),
        "review_command": (
            f"curator_workbench action=explain path={artifact} candidate_id={candidate_id}"
            if artifact and candidate_id
            else ""
        ),
        "map_command": (
            f"curator_workbench action=map path={artifact} candidate_id={candidate_id}"
            if artifact and candidate_id and _sequence_count(candidate.get("proposed_relations"))
            else ""
        ),
        "promotion_command": (
            f"review_recall_candidate action=promote_ready path={artifact} candidate_id={candidate_id}"
            if artifact and candidate_id and str(candidate.get("status") or "") == "ready_for_promotion"
            else ""
        ),
        "relation_preview_command": (
            f"review_recall_candidate action=preview_relations path={artifact} candidate_id={candidate_id}"
            if artifact and candidate_id and str(candidate.get("status") or "") == "ready_for_promotion"
            else ""
        ),
    }


def list_candidate_cards(
    root: str | Path | None = None,
    status: str = "pending",
    limit: int = 20,
) -> list[dict[str, Any]]:
    """List candidate cards ordered by recommendation score."""

    records = load_candidate_records(root=root)
    cards = [
        candidate_card(candidate)
        for candidate in records
        if not status or str(candidate.get("status", "pending")) == status
    ]
    return sorted(cards, key=lambda item: float(item.get("score") or 0.0), reverse=True)[:limit]


async def inspect_candidate(
    candidate_id: str,
    entity_repo: Any | None = None,
    memory_repo: Any | None = None,
    retriever: Any | None = None,
    root: str | Path | None = None,
    path: str | Path | None = None,
    graph_depth: int = 1,
) -> dict[str, Any]:
    """Return a review packet with score, suggestions, graph hints, and trace."""

    candidate = find_candidate(candidate_id, root=root, path=path)
    if candidate is None:
        raise ValueError(f"candidate not found: {candidate_id}")

    card = candidate_card(candidate)
    suggestions: dict[str, Any] = {}
    if entity_repo is not None:
        suggestions = await suggest_metadata(
            candidate.get("_candidate_path") or path or "",
            candidate_id,
            entity_repo,
            limit=8,
        )

    graph: dict[str, list[dict[str, Any]]] = {}
    if entity_repo is not None:
        for field in ("source_id", "target_id"):
            entity_id = str(candidate.get(field) or suggestions.get(f"suggested_{field}") or "")
            if entity_id:
                graph[field] = await entity_repo.explore_graph(entity_id, depth=graph_depth)

    target_suggestions = await suggest_candidate_targets(
        candidate,
        memory_repo=memory_repo,
        retriever=retriever,
        limit=8,
    )
    candidate_neighbors = await suggest_candidate_neighbors(
        candidate,
        retriever=retriever,
        limit=8,
    )

    return {
        "candidate": candidate,
        "card": card,
        "suggestions": suggestions,
        "target_suggestions": target_suggestions,
        "candidate_neighbors": candidate_neighbors,
        "graph": graph,
        "trace": source_trace(candidate),
    }


async def explain_candidate(
    candidate_id: str,
    entity_repo: Any | None = None,
    memory_repo: Any | None = None,
    retriever: Any | None = None,
    root: str | Path | None = None,
    path: str | Path | None = None,
    graph_depth: int = 1,
) -> dict[str, Any]:
    """Explain why a candidate exists and the safest next curator action."""

    packet = await inspect_candidate(
        candidate_id,
        entity_repo=entity_repo,
        memory_repo=memory_repo,
        retriever=retriever,
        root=root,
        path=path,
        graph_depth=graph_depth,
    )
    candidate = packet["candidate"]
    card = packet["card"]
    trace = packet["trace"]
    target_suggestions = packet.get("target_suggestions") or []
    candidate_neighbors = packet.get("candidate_neighbors") or []
    missing = list(card.get("metadata_missing") or [])
    status = str(card.get("status") or "pending")
    artifact = str(card.get("artifact") or trace.get("candidate_path") or "")
    relation_type = str(card.get("relation_type") or trace.get("relation_type") or "")

    evidence = _candidate_evidence(candidate, trace)
    next_action = _next_curator_action(
        candidate_id=candidate_id,
        artifact=artifact,
        status=status,
        missing=missing,
        target_needs_resolution=bool(card.get("target_needs_resolution")),
        target_suggestions=target_suggestions,
        relation_type=relation_type,
    )

    return {
        "candidate_id": candidate_id,
        "status": status,
        "summary": card.get("query", ""),
        "recommendation": card.get("recommendation", ""),
        "score": card.get("score", 0),
        "reasons": list(card.get("reasons") or []),
        "missing_metadata": missing,
        "relation_type": relation_type,
        "target_needs_resolution": bool(card.get("target_needs_resolution")),
        "target_suggestions": target_suggestions,
        "candidate_neighbors": candidate_neighbors,
        "proposed_relations": trace.get("proposed_relations") or [],
        "evidence": evidence,
        "source_trace": trace,
        "next_action": next_action,
    }


def _candidate_evidence(candidate: Mapping[str, Any], trace: Mapping[str, Any]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for key in ("query", "source", "session_id", "channel", "artifact", "source_artifact"):
        value = candidate.get(key) or trace.get(key)
        if value:
            evidence.append({"field": key, "value": str(value)})

    pattern = candidate.get("pattern")
    if isinstance(pattern, Mapping):
        for key in ("type", "query", "source", "target", "session_id"):
            value = pattern.get(key)
            if value:
                evidence.append({"field": f"pattern.{key}", "value": str(value)})

    for derived in trace.get("derived_from") or []:
        evidence.append({"field": "derived_from", "value": str(derived)})

    return _dedupe_evidence(evidence)


def _dedupe_evidence(items: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, Any]] = []
    for item in items:
        field = str(item.get("field") or "")
        value = str(item.get("value") or "")
        key = (field, value)
        if not field or not value or key in seen:
            continue
        seen.add(key)
        result.append({"field": field, "value": value})
    return result


def _next_curator_action(
    *,
    candidate_id: str,
    artifact: str,
    status: str,
    missing: list[str],
    target_needs_resolution: bool,
    target_suggestions: list[dict[str, Any]],
    relation_type: str,
) -> dict[str, Any]:
    base = f"path={artifact} candidate_id={candidate_id}".strip()
    if status == "ready_for_promotion":
        return {
            "action": "promote_ready",
            "reason": "metadata_resolved",
            "command": f"review_recall_candidate action=promote_ready {base}",
        }

    if target_needs_resolution:
        target_id = str(target_suggestions[0].get("target_id") or "") if target_suggestions else ""
        command = f"review_recall_candidate action=apply_target {base}"
        if target_id:
            command = f"{command} target_id={target_id}"
        return {
            "action": "apply_target",
            "reason": "target_needs_resolution",
            "command": command,
        }

    if missing:
        return {
            "action": "suggest_metadata",
            "reason": "missing_metadata",
            "command": f"review_recall_candidate action=suggest_metadata {base}",
            "followup_action": "complete_metadata",
            "followup_command": (
                f"review_recall_candidate action=complete_metadata {base} "
                "source_id=<source_id> target_id=<target_id> relation_type=<relation_type>"
            ),
            "missing": missing,
        }

    if relation_type:
        return {
            "action": "promote",
            "reason": "metadata_complete",
            "command": f"review_recall_candidate action=promote {base} relation={relation_type}",
        }

    return {
        "action": "inspect",
        "reason": "needs_human_review",
        "command": f"curator_workbench action=inspect {base}",
    }


async def suggest_candidate_targets(
    candidate: Mapping[str, Any],
    memory_repo: Any | None = None,
    retriever: Any | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Suggest concrete memory targets for unresolved relation candidates."""

    if not candidate.get("target_needs_resolution"):
        return []

    query = str(candidate.get("query") or _pattern_summary(candidate.get("pattern"))).strip()
    if not query:
        return []

    suggestions: list[dict[str, Any]] = []
    if memory_repo is not None:
        suggestions.extend(await _canonical_target_suggestions(query, memory_repo, limit=limit))

    if retriever is not None:
        suggestions.extend(await _semantic_target_suggestions(query, retriever, limit=limit))

    return _dedupe_target_suggestions(suggestions)[:limit]


async def suggest_candidate_neighbors(
    candidate: Mapping[str, Any],
    retriever: Any | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Suggest semantically nearby uncurated candidates for curator comparison."""

    if retriever is None:
        return []

    candidate_id = str(candidate.get("candidate_id") or "").strip()
    candidate_path = str(candidate.get("_candidate_path") or candidate.get("artifact") or "").strip()
    query = str(candidate.get("query") or _pattern_summary(candidate.get("pattern"))).strip()
    if not query:
        query = candidate_embedding_text(candidate)[:800]
    if not query:
        return []

    results = await retriever.search(query=query, top_k=limit + 2, source_filter="memory_candidate")
    neighbors: list[dict[str, Any]] = []
    for result in results:
        source_key = str(getattr(result, "source_key", "") or "").strip()
        if not source_key or source_key == candidate_id:
            continue
        neighbors.append(
            {
                "candidate_id": source_key,
                "target_id": f"candidate:{source_key}",
                "source": "semantic_candidate",
                "rowid": getattr(result, "rowid", ""),
                "score": float(getattr(result, "fusion_score", getattr(result, "score", 0.0)) or 0.0),
                "reason": "semantic_candidate_neighbor",
                "text_preview": str(getattr(result, "text", ""))[:220],
                "refine_command": (
                    f"review_recall_candidate action=link_neighbor path={candidate_path} "
                    f"candidate_id={candidate_id} neighbor_candidate_id={source_key} relation_type=REFINES"
                    if candidate_path and candidate_id
                    else ""
                ),
                "duplicate_command": (
                    f"review_recall_candidate action=link_neighbor path={candidate_path} "
                    f"candidate_id={candidate_id} neighbor_candidate_id={source_key} relation_type=DUPLICATES"
                    if candidate_path and candidate_id
                    else ""
                ),
            }
        )
        if len(neighbors) >= limit:
            break
    return neighbors


def source_trace(candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Extract the provenance chain available in a candidate artifact."""

    pattern = candidate.get("pattern") if isinstance(candidate.get("pattern"), Mapping) else {}
    return {
        "candidate_id": candidate.get("candidate_id", ""),
        "candidate_path": candidate.get("_candidate_path") or candidate.get("artifact", ""),
        "source": candidate.get("source", ""),
        "session_id": candidate.get("session_id") or pattern.get("session_id", ""),
        "channel": candidate.get("channel", ""),
        "timestamp": candidate.get("timestamp") or candidate.get("created_at", ""),
        "artifact": candidate.get("artifact", ""),
        "relation_type": candidate.get("relation_type", ""),
        "target_id": candidate.get("target_id", ""),
        "target_needs_resolution": bool(candidate.get("target_needs_resolution")),
        "entities": _entity_names(candidate.get("entities")),
        "proposed_relations": candidate.get("proposed_relations") if isinstance(candidate.get("proposed_relations"), list) else [],
        "source_channels": candidate.get("source_channels") if isinstance(candidate.get("source_channels"), Mapping) else {},
        "source_sessions": candidate.get("source_sessions") if isinstance(candidate.get("source_sessions"), list) else [],
        "derived_from": _derived_from(candidate),
    }


def candidate_relation_map(candidate: Mapping[str, Any], limit: int = 40) -> dict[str, Any]:
    """Build a curator-facing graph preview from proposed candidate relations."""

    relations = candidate.get("proposed_relations")
    proposed = relations if isinstance(relations, list) else []
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []

    for relation in proposed[:limit]:
        if not isinstance(relation, Mapping):
            continue
        source_id = str(relation.get("source_id") or "").strip()
        target_id = str(relation.get("target_id") or "").strip()
        relation_type = str(relation.get("relation_type") or "").strip()
        if not source_id or not target_id or not relation_type:
            continue
        nodes.setdefault(source_id, _relation_node(source_id))
        nodes.setdefault(target_id, _relation_node(target_id))
        edges.append(
            {
                "source_id": source_id,
                "target_id": target_id,
                "relation_type": relation_type,
                "weight": relation.get("weight", ""),
                "needs_resolution": bool(relation.get("needs_resolution")),
                "provenance": relation.get("provenance", ""),
            }
        )

    if not nodes and candidate.get("source_id") and candidate.get("target_id"):
        source_id = str(candidate.get("source_id") or "")
        target_id = str(candidate.get("target_id") or "")
        relation_type = str(candidate.get("relation_type") or "")
        nodes[source_id] = _relation_node(source_id)
        nodes[target_id] = _relation_node(target_id)
        edges.append(
            {
                "source_id": source_id,
                "target_id": target_id,
                "relation_type": relation_type,
                "weight": candidate.get("link_score") or candidate.get("confidence") or "",
                "needs_resolution": bool(candidate.get("target_needs_resolution")),
                "provenance": candidate.get("source", ""),
            }
        )

    return {
        "candidate_id": candidate.get("candidate_id", ""),
        "nodes": sorted(nodes.values(), key=lambda item: str(item["id"])),
        "edges": edges,
        "mermaid": render_candidate_relation_mermaid(nodes.values(), edges),
    }


def render_candidate_relation_mermaid(
    nodes: Iterable[Mapping[str, Any]],
    edges: Iterable[Mapping[str, Any]],
) -> str:
    """Render a Mermaid graph for proposed curator relations."""

    node_items = list(nodes)
    edge_items = list(edges)
    if not node_items and not edge_items:
        return "flowchart LR\n  empty[\"No proposed relations\"]"

    node_ids = {str(node.get("id") or ""): f"n{idx}" for idx, node in enumerate(node_items)}
    lines = ["flowchart LR"]
    for node in node_items:
        node_id = str(node.get("id") or "")
        mermaid_id = node_ids.get(node_id, "")
        if not mermaid_id:
            continue
        label = _mermaid_label(f"{node.get('type', 'node')}\\n{node_id}")
        lines.append(f"  {mermaid_id}[\"{label}\"]")

    for edge in edge_items:
        source_id = str(edge.get("source_id") or "")
        target_id = str(edge.get("target_id") or "")
        source = node_ids.get(source_id)
        target = node_ids.get(target_id)
        if not source or not target:
            continue
        relation_type = str(edge.get("relation_type") or "RELATED")
        suffix = " needs_resolution" if edge.get("needs_resolution") else ""
        label = _mermaid_label(f"{relation_type}{suffix}")
        lines.append(f"  {source} -->|\"{label}\"| {target}")
    return "\n".join(lines)


def _relation_node(node_id: str) -> dict[str, Any]:
    prefix = node_id.split(":", 1)[0] if ":" in node_id else "node"
    return {
        "id": node_id,
        "type": prefix,
        "label": node_id.split(":", 1)[1] if ":" in node_id else node_id,
    }


def _mermaid_label(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace('"', "'")
        .replace("\r", " ")
        .replace("\n", "<br/>")
    )


def _derived_from(candidate: Mapping[str, Any]) -> list[str]:
    derived: list[str] = []
    for key in ("artifact", "_candidate_path", "source_artifact"):
        value = candidate.get(key)
        if value:
            derived.append(str(value))
    for source in candidate.get("source_sessions", []) if isinstance(candidate.get("source_sessions"), list) else []:
        if not isinstance(source, Mapping):
            continue
        session_id = str(source.get("session_id") or "").strip()
        channel = str(source.get("channel") or "web").strip() or "web"
        if session_id:
            derived.append(f"{channel}:{session_id}")
    pattern = candidate.get("pattern")
    if isinstance(pattern, Mapping):
        for key in ("session_id", "source", "target", "query"):
            value = pattern.get(key)
            if value:
                derived.append(f"{key}:{value}")
    return list(dict.fromkeys(derived))


def _pattern_summary(pattern: Any) -> str:
    if not isinstance(pattern, Mapping):
        return ""
    for key in ("query", "source", "session_id", "type"):
        value = pattern.get(key)
        if value:
            return str(value)
    return json.dumps(dict(pattern), ensure_ascii=False, sort_keys=True)[:160]


def _entity_names(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    names: list[str] = []
    for item in value:
        if isinstance(item, Mapping):
            name = str(item.get("name") or "").strip()
            if name:
                names.append(name)
    return names


def _sequence_count(value: Any) -> int:
    return len(value) if isinstance(value, list) else 0


async def _canonical_target_suggestions(
    query: str,
    memory_repo: Any,
    limit: int,
) -> list[dict[str, Any]]:
    tokens = _tokens(query)
    if not tokens:
        return []

    rows = await memory_repo.get_all()
    scored: list[dict[str, Any]] = []
    for row in rows:
        key = str(row.get("key") or "")
        value = str(row.get("value") or "")
        haystack = f"{key} {value}"
        overlap = _overlap_score(tokens, _tokens(haystack))
        if overlap <= 0:
            continue
        scored.append(
            {
                "target_id": f"memory:{key}",
                "source": "memory_index",
                "key": key,
                "score": overlap,
                "reason": "canonical_token_overlap",
                "text_preview": value[:220],
            }
        )
    return sorted(scored, key=lambda item: float(item["score"]), reverse=True)[:limit]


async def _semantic_target_suggestions(
    query: str,
    retriever: Any,
    limit: int,
) -> list[dict[str, Any]]:
    results = await retriever.search(query=query, top_k=limit, source_filter="memory")
    suggestions: list[dict[str, Any]] = []
    for result in results:
        source_key = str(getattr(result, "source_key", "") or "")
        if not source_key:
            continue
        suggestions.append(
            {
                "target_id": f"memory:{source_key}",
                "source": "semantic_memory",
                "key": source_key,
                "rowid": getattr(result, "rowid", ""),
                "score": float(getattr(result, "fusion_score", getattr(result, "score", 0.0)) or 0.0),
                "reason": "semantic_memory_match",
                "text_preview": str(getattr(result, "text", ""))[:220],
            }
        )
    return suggestions


def _dedupe_target_suggestions(suggestions: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_target: dict[str, dict[str, Any]] = {}
    for suggestion in suggestions:
        target_id = str(suggestion.get("target_id") or "")
        if not target_id:
            continue
        current = by_target.get(target_id)
        candidate = dict(suggestion)
        if current is None or float(candidate.get("score") or 0.0) > float(current.get("score") or 0.0):
            by_target[target_id] = candidate
    return sorted(by_target.values(), key=lambda item: float(item.get("score") or 0.0), reverse=True)


def _tokens(text: str) -> set[str]:
    stopwords = {
        "para", "pero", "como", "este", "esta", "estos", "estas", "sobre",
        "desde", "hacia", "entre", "porque", "cuando", "donde", "debe",
        "deben", "tiene", "tener", "hacer", "cosas", "algo", "todo",
        "the", "and", "with", "that", "this",
    }
    return {
        token
        for token in re.findall(r"[a-zA-Z0-9_áéíóúñÁÉÍÓÚÑ.-]{3,}", text.lower())
        if token not in stopwords
    }


def _overlap_score(query_tokens: set[str], target_tokens: set[str]) -> float:
    if not query_tokens or not target_tokens:
        return 0.0
    hits = len(query_tokens & target_tokens)
    if hits == 0:
        return 0.0
    coverage = hits / len(query_tokens)
    specificity = hits / max(len(target_tokens), 1)
    return round(min(1.0, coverage * 0.75 + specificity * 0.25), 3)


def query_terms_for_candidate(candidate: Mapping[str, Any]) -> list[str]:
    """Expose query tokenization for tests and future UI filters."""

    return query_terms(str(candidate.get("query") or _pattern_summary(candidate.get("pattern"))))
