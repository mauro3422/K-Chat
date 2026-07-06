"""Candidates derived from transversal synthesis artifacts."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping

from src.memory import paths as memory_paths
from src.memory.content_hash import content_hash
from src.memory.curator.recall_review import load_candidates, write_candidates

_project_root = memory_paths._project_root
_default_target_date = memory_paths._default_target_date


def _section_lines(text: str, heading: str) -> list[str]:
    marker = f"## {heading}"
    if marker not in text:
        return []
    section = text.split(marker, 1)[1]
    if "\n## " in section:
        section = section.split("\n## ", 1)[0]
    lines: list[str] = []
    for raw in section.splitlines():
        line = raw.rstrip()
        if line.strip():
            lines.append(line)
    return lines


def _topic_candidate_seed(line: str) -> str:
    if "`" in line:
        parts = line.split("`")
        if len(parts) >= 3:
            return parts[1].strip()
    return line.lstrip("- ").split(":", 1)[0].strip()


def _candidate_entities_for_transversal(text: str, topic: str) -> list[dict[str, Any]]:
    from src.memory.synthesis.transversal import _infer_entities

    entities = [
        {
            "name": name,
            "entity_type": "concept",
            "confidence": 0.65,
            "evidence": "transversal synthesis",
        }
        for name in _infer_entities(text)
    ]
    if topic and not any(entity["name"].lower() == topic.lower() for entity in entities):
        entities.append(
            {
                "name": topic,
                "entity_type": "topic",
                "confidence": 0.58,
                "evidence": "repeated transversal topic",
            }
        )
    return entities


def _transversal_candidate_relations(
    candidate_id: str,
    artifact: Mapping[str, Any],
    entities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    source_id = f"candidate:{candidate_id}"
    artifact_path = str(artifact.get("path") or "")
    relations: list[dict[str, Any]] = [
        {
            "source_id": source_id,
            "target_id": f"artifact:{content_hash(artifact_path, limit=10000)[:16]}",
            "relation_type": "DERIVED_FROM",
            "weight": 0.74,
            "provenance": "transversal_synthesis_artifact",
        },
        {
            "source_id": source_id,
            "target_id": "memory:semantic-neighbor",
            "relation_type": "LINKS_TO",
            "weight": 0.68,
            "provenance": "transversal_repeated_signal",
            "needs_resolution": True,
        },
    ]
    for source in artifact.get("metadata", {}).get("sources", []) if isinstance(artifact.get("metadata"), Mapping) else []:
        session_id = str(source.get("session_id") or "") if isinstance(source, Mapping) else ""
        if session_id:
            relations.append(
                {
                    "source_id": source_id,
                    "target_id": f"session:{session_id}",
                    "relation_type": "DERIVED_FROM",
                    "weight": 0.62,
                    "provenance": "transversal_source_session",
                }
            )
    for entity in entities:
        name = str(entity.get("name") or "").strip()
        if name:
            relations.append(
                {
                    "source_id": source_id,
                    "target_id": f"entity:{name.lower().replace(' ', '_')}",
                    "relation_type": "MENTIONS",
                    "weight": float(entity.get("confidence") or 0.5),
                    "provenance": "transversal_entity_hint",
                }
            )
    return relations


def _transversal_source_refs(artifact: Mapping[str, Any]) -> list[dict[str, str]]:
    metadata = artifact.get("metadata") if isinstance(artifact.get("metadata"), Mapping) else {}
    refs: list[dict[str, str]] = []
    for source in metadata.get("sources", []) if isinstance(metadata.get("sources"), list) else []:
        if not isinstance(source, Mapping):
            continue
        session_id = str(source.get("session_id") or "").strip()
        channel = str(source.get("channel") or "web").strip() or "web"
        if session_id:
            refs.append(
                {
                    "session_id": session_id,
                    "channel": channel,
                    "path": str(source.get("path") or ""),
                    "content_hash": str(source.get("content_hash") or ""),
                }
            )
    return refs


def _transversal_channels(artifact: Mapping[str, Any], sources: list[dict[str, str]]) -> dict[str, int]:
    metadata = artifact.get("metadata") if isinstance(artifact.get("metadata"), Mapping) else {}
    channels = metadata.get("channels") if isinstance(metadata.get("channels"), Mapping) else {}
    if channels:
        result: dict[str, int] = {}
        for key, value in channels.items():
            try:
                result[str(key)] = int(value)
            except (TypeError, ValueError):
                continue
        return dict(sorted(result.items()))

    counts: dict[str, int] = {}
    for source in sources:
        channel = str(source.get("channel") or "web")
        counts[channel] = counts.get(channel, 0) + 1
    return dict(sorted(counts.items()))


def candidates_from_transversal_synthesis_artifact(
    artifact: Mapping[str, Any],
    timestamp: str | None = None,
    limit: int = 8,
) -> list[dict[str, Any]]:
    """Create review candidates from repeated transversal signals."""

    from src.memory.synthesis.transversal import _clip, _is_actionable_topic

    text = str(artifact.get("text") or "")
    topic_lines = [
        line for line in _section_lines(text, "Repeated Topics")
        if line.startswith("- `") and "No repeated" not in line
        and _is_actionable_topic(_topic_candidate_seed(line))
    ][:limit]
    if not topic_lines:
        return []

    ts = timestamp or datetime.now().isoformat(timespec="seconds")
    date_key = str(artifact.get("date") or artifact.get("metadata", {}).get("date") or "")
    artifact_path = str(artifact.get("path") or "")
    source_refs = _transversal_source_refs(artifact)
    source_channels = _transversal_channels(artifact, source_refs)
    candidates: list[dict[str, Any]] = []
    for line in topic_lines:
        topic = _topic_candidate_seed(line)
        if not topic:
            continue
        evidence = [line]
        line_index = text.splitlines().index(line) if line in text.splitlines() else -1
        if line_index >= 0:
            for raw in text.splitlines()[line_index + 1 : line_index + 4]:
                if raw.startswith("  - "):
                    evidence.append(raw.strip())
                else:
                    break
        query = _clip(" ".join(item.lstrip("- ").strip() for item in evidence), 700)
        payload = {
            "type": "transversal_synthesis_candidate",
            "source": "transversal_synthesis",
            "date": date_key,
            "channel": "transversal",
            "query": query,
            "result_excerpt": _clip("\n".join(evidence), 1000),
            "source_artifact": artifact_path,
            "artifact": artifact_path,
            "content_hash": str(artifact.get("content_hash") or ""),
            "topic": topic,
            "source_channels": source_channels,
            "source_sessions": source_refs,
        }
        candidate_id = content_hash(json.dumps(payload, ensure_ascii=False, sort_keys=True), limit=100000)[:16]
        entities = _candidate_entities_for_transversal(" ".join(evidence), topic)
        candidates.append(
            {
                **payload,
                "candidate_id": candidate_id,
                "status": "pending",
                "created_at": ts,
                "confidence": 0.68,
                "relation_type": "LINKS_TO",
                "source_id": f"candidate:{candidate_id}",
                "target_id": "memory:semantic-neighbor",
                "target_needs_resolution": True,
                "link_score": 0.68,
                "link_reasons": ["transversal_repeated_topic", "semantic_target_required"],
                "entities": entities,
                "temporal": {
                    "first_seen": ts,
                    "last_seen": ts,
                    "status": "reinforced",
                },
                "provenance": {
                    "date": date_key,
                    "artifact": artifact_path,
                    "content_hash": str(artifact.get("content_hash") or ""),
                    "channels": source_channels,
                    "sources": source_refs,
                },
                "reinforcement_count": max(2, query.count("session")),
                "proposed_relations": _transversal_candidate_relations(candidate_id, artifact, entities),
            }
        )
    return candidates


def generate_transversal_synthesis_candidates(
    root: str | Path | None = None,
    target_date: date | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Materialize candidates derived from transversal synthesis artifacts."""

    from src.memory.synthesis.transversal import (
        discover_transversal_synthesis_artifacts,
        transversal_synthesis_candidate_path,
    )

    target = target_date or _default_target_date()
    path = transversal_synthesis_candidate_path(target, root=root)
    existing = load_candidates(path)
    by_id = {str(candidate.get("candidate_id")): dict(candidate) for candidate in existing}
    stale_ids: set[str] = set()
    created = 0
    for artifact in discover_transversal_synthesis_artifacts(root=root):
        if str(artifact.get("date") or "") != target.isoformat():
            continue
        fresh = candidates_from_transversal_synthesis_artifact(artifact, timestamp=timestamp)
        fresh_ids = {str(candidate.get("candidate_id") or "") for candidate in fresh}
        artifact_path = str(artifact.get("path") or "")
        for cid, candidate in by_id.items():
            if (
                str(candidate.get("source")) == "transversal_synthesis"
                and str(candidate.get("date") or "") == target.isoformat()
                and str(candidate.get("source_artifact") or candidate.get("artifact") or "") == artifact_path
                and cid not in fresh_ids
            ):
                stale_ids.add(cid)
        for candidate in fresh:
            cid = str(candidate.get("candidate_id") or "")
            if cid in by_id:
                continue
            by_id[cid] = candidate
            created += 1

    for cid in stale_ids:
        by_id.pop(cid, None)

    if by_id:
        write_candidates(path, list(by_id.values()))
    return {
        "path": str(path),
        "created": created,
        "total": len(by_id),
    }
