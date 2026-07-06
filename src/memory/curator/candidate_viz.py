"""Visualization helpers for curator candidate relations."""

from __future__ import annotations

import json
from typing import Any, Iterable, Mapping


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


def _pattern_summary(pattern: Any) -> str:
    if not isinstance(pattern, Mapping):
        return ""
    for key in ("query", "source", "session_id", "type"):
        value = pattern.get(key)
        if value:
            return str(value)
    return json.dumps(dict(pattern), ensure_ascii=False, sort_keys=True)[:160]


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
