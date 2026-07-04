"""JSONL artifacts for active recall events."""

from __future__ import annotations

import json
import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def recall_event_path(timestamp: str, root: str | Path | None = None) -> Path:
    """Return the daily JSONL path for recall/link events."""

    date = timestamp[:10] if timestamp else datetime.now().date().isoformat()
    year, month, day = date.split("-")
    base = Path(root) if root is not None else _project_root()
    return base / "memory" / "recall" / year / month / f"{day}.jsonl"


def recall_candidate_path(timestamp: str, root: str | Path | None = None) -> Path:
    """Return the daily JSONL path for materialized recall candidates."""

    date = timestamp[:10] if timestamp else datetime.now().date().isoformat()
    year, month, day = date.split("-")
    base = Path(root) if root is not None else _project_root()
    return base / "memory" / "candidates" / year / month / f"{day}.recall_links.jsonl"


def append_recall_event(
    event: Mapping[str, Any],
    root: str | Path | None = None,
    timestamp: str | None = None,
) -> Path:
    """Append a recall event artifact and return the path written."""

    ts = timestamp or datetime.now().isoformat(timespec="seconds")
    path = recall_event_path(ts, root=root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"timestamp": ts, **dict(event)}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    return path


def _parse_timestamp(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _candidate_id(event: Mapping[str, Any]) -> str:
    raw = "|".join(
        str(event.get(name, ""))
        for name in ("timestamp", "query", "intent", "link_action")
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _artifact_id(path: str) -> str:
    digest = hashlib.sha256(path.encode("utf-8")).hexdigest()[:16]
    return f"artifact:{digest}"


def _normalize_entity_id(name: str) -> str:
    normalized = re.sub(r"[^a-z0-9_.-]+", "_", name.lower()).strip("_")
    return f"entity:{normalized or 'unknown'}"


def _event_entities(event: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw_entities = event.get("known_entities") or event.get("entities") or []
    if not isinstance(raw_entities, list):
        return []

    entities: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_entities:
        if isinstance(raw, Mapping):
            name = str(raw.get("name") or raw.get("entity") or "").strip()
            entity_type = str(raw.get("entity_type") or raw.get("type") or "unknown")
            confidence = float(raw.get("confidence") or 0.65)
            evidence = str(raw.get("evidence") or "recall event")
        else:
            name = str(raw).strip()
            entity_type = "unknown"
            confidence = 0.65
            evidence = "recall event"
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        entities.append(
            {
                "name": name,
                "entity_type": entity_type,
                "confidence": confidence,
                "evidence": evidence,
            }
        )
    return entities


def _event_target_policy(event: Mapping[str, Any], relation_type: str) -> dict[str, Any]:
    target_id = str(event.get("target_id") or "").strip()
    if target_id:
        return {"target_id": target_id, "target_needs_resolution": False}

    for key in ("memory_key", "source_key"):
        value = str(event.get(key) or "").strip()
        if value:
            return {"target_id": f"memory:{value}", "target_needs_resolution": False}

    if relation_type == "CONTRADICTS":
        return {"target_id": "memory:canonical", "target_needs_resolution": True}

    if event.get("result_excerpt") or event.get("link_action"):
        return {"target_id": "memory:semantic-neighbor", "target_needs_resolution": True}

    return {"target_id": "memory:canonical", "target_needs_resolution": True}


def _candidate_temporal_metadata(timestamp: str) -> dict[str, str]:
    return {
        "first_seen": timestamp,
        "last_seen": timestamp,
        "status": "new",
    }


def _recall_candidate_relations(
    candidate_id: str,
    event: Mapping[str, Any],
    *,
    relation_type: str,
    target_id: str,
    target_needs_resolution: bool,
    entities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    source_id = f"candidate:{candidate_id}"
    relations: list[dict[str, Any]] = []

    artifact = str(event.get("_artifact") or event.get("artifact") or "").strip()
    if artifact:
        relations.append(
            {
                "source_id": source_id,
                "target_id": _artifact_id(artifact),
                "relation_type": "DERIVED_FROM",
                "weight": 0.62,
                "provenance": "recall_event_artifact",
            }
        )

    session_id = str(event.get("session_id") or "").strip()
    if session_id:
        relations.append(
            {
                "source_id": source_id,
                "target_id": f"session:{session_id}",
                "relation_type": "DERIVED_FROM",
                "weight": 0.66,
                "provenance": "recall_event_session",
            }
        )

    if target_id:
        relations.append(
            {
                "source_id": source_id,
                "target_id": target_id,
                "relation_type": relation_type,
                "weight": float(event.get("link_score") or 0.5),
                "provenance": str(event.get("trigger") or "active_recall"),
                "needs_resolution": target_needs_resolution,
            }
        )

    for entity in entities:
        name = str(entity.get("name") or "").strip()
        if not name:
            continue
        relations.append(
            {
                "source_id": source_id,
                "target_id": _normalize_entity_id(name),
                "relation_type": "MENTIONS",
                "weight": float(entity.get("confidence") or 0.5),
                "provenance": "recall_entity_hint",
            }
        )

    semantic_hints = event.get("semantic_relation_hints") or []
    if isinstance(semantic_hints, list):
        for hint in semantic_hints:
            if not isinstance(hint, Mapping):
                continue
            hint_source = str(hint.get("source_id") or "").strip()
            hint_target = str(hint.get("target_id") or "").strip()
            hint_relation = str(hint.get("relation_type") or "").strip().upper()
            if not hint_source or not hint_target or not hint_relation:
                continue
            relations.append(
                {
                    "source_id": hint_source,
                    "target_id": hint_target,
                    "relation_type": hint_relation,
                    "weight": float(hint.get("weight") or 0.5),
                    "provenance": str(hint.get("provenance") or "active_recall_semantic_neighbor"),
                    "evidence": str(hint.get("evidence") or ""),
                }
            )

    return relations


def iter_recall_events(
    root: str | Path | None = None,
    lookback_days: int = 7,
) -> list[dict[str, Any]]:
    """Load recall JSONL events inside the lookback window."""

    base = Path(root) if root is not None else _project_root()
    recall_root = base / "memory" / "recall"
    if not recall_root.exists():
        return []

    cutoff = datetime.now().timestamp() - max(lookback_days, 0) * 86400
    events: list[dict[str, Any]] = []
    for path in sorted(recall_root.rglob("*.jsonl")):
        if path.stat().st_mtime < cutoff:
            continue
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict):
                    payload["_artifact"] = str(path)
                    events.append(payload)
    return events


def recall_relation_type(action: str) -> str:
    """Map remember link hints to graph relation names."""

    normalized = (action or "").strip().lower()
    if normalized == "links_to":
        return "LINKS_TO"
    if normalized == "semantically_related":
        return "SEMANTICALLY_RELATED"
    if normalized == "contradicts":
        return "CONTRADICTS"
    return "RECALLS"


def recall_candidates_from_events(
    events: list[Mapping[str, Any]],
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Convert recall events into curator-friendly relation candidates."""

    candidates: list[dict[str, Any]] = []
    for event in events:
        status = event.get("status")
        if status == "skipped":
            continue

        link_action = str(event.get("link_action") or "")
        relation_type = recall_relation_type(link_action)
        candidate_id = _candidate_id(event)
        timestamp = str(event.get("timestamp") or "")
        entities = _event_entities(event)
        target_policy = _event_target_policy(event, relation_type)
        target_id = str(target_policy["target_id"])
        target_needs_resolution = bool(target_policy["target_needs_resolution"])
        artifact = str(event.get("_artifact") or event.get("artifact") or "")
        session_id = str(event.get("session_id") or "")
        channel = str(event.get("channel") or "recall")
        candidate = {
            "type": "recall_link_candidate",
            "candidate_id": candidate_id,
            "status": "pending",
            "source": "remember",
            "source_id": f"candidate:{candidate_id}",
            "target_id": target_id,
            "target_needs_resolution": target_needs_resolution,
            "relation_type": relation_type,
            "query": event.get("query", ""),
            "intent": event.get("intent", ""),
            "trigger": event.get("trigger", ""),
            "link_action": link_action,
            "link_score": float(event.get("link_score") or 0.0),
            "link_reasons": event.get("link_reasons", []),
            "artifact": artifact,
            "source_artifact": artifact,
            "timestamp": timestamp,
            "channel": channel,
            "session_id": session_id,
            "result_excerpt": event.get("result_excerpt", ""),
            "entities": entities,
            "temporal": _candidate_temporal_metadata(timestamp),
            "provenance": {
                "timestamp": timestamp,
                "artifact": artifact,
                "session_id": session_id,
                "channel": channel,
                "intent": event.get("intent", ""),
                "trigger": event.get("trigger", ""),
                "source": event.get("source", "remember"),
            },
            "proposed_relations": _recall_candidate_relations(
                candidate_id,
                event,
                relation_type=relation_type,
                target_id=target_id,
                target_needs_resolution=target_needs_resolution,
                entities=entities,
            ),
        }
        candidates.append(candidate)

    def sort_key(item: Mapping[str, Any]) -> tuple[float, str]:
        ts = _parse_timestamp(str(item.get("timestamp", "")))
        timestamp = ts.isoformat() if ts else ""
        return (float(item.get("link_score") or 0.0), timestamp)

    return sorted(candidates, key=sort_key, reverse=True)[:limit]


def detect_recall_candidates(
    root: str | Path | None = None,
    lookback_days: int = 7,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Read active recall artifacts and return curator candidates."""

    events = iter_recall_events(root=root, lookback_days=lookback_days)
    return recall_candidates_from_events(events, limit=limit)


def write_recall_candidates(
    candidates: list[Mapping[str, Any]],
    root: str | Path | None = None,
    timestamp: str | None = None,
) -> Path | None:
    """Write a daily candidate snapshot for curator review."""

    if not candidates:
        return None

    ts = timestamp or datetime.now().isoformat(timespec="seconds")
    path = recall_candidate_path(ts, root=root)
    path.parent.mkdir(parents=True, exist_ok=True)

    unique: dict[str, Mapping[str, Any]] = {}
    for candidate in candidates:
        candidate_id = str(candidate.get("candidate_id") or "")
        if not candidate_id:
            candidate_id = hashlib.sha256(
                json.dumps(dict(candidate), ensure_ascii=False, sort_keys=True).encode("utf-8")
            ).hexdigest()[:16]
        payload = {
            "candidate_id": candidate_id,
            "status": candidate.get("status", "pending"),
            "created_at": ts,
            **dict(candidate),
        }
        unique[candidate_id] = payload

    ordered = sorted(
        unique.values(),
        key=lambda item: (
            float(item.get("link_score") or 0.0),
            str(item.get("timestamp") or ""),
        ),
        reverse=True,
    )
    with path.open("w", encoding="utf-8") as handle:
        for item in ordered:
            handle.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")
    return path
