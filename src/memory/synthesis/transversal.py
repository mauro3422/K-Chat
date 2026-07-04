"""Transversal synthesis across per-session summaries."""

from __future__ import annotations

import asyncio
import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping

from src.memory.content_hash import content_hash
from src.memory.curator.recall_review import load_candidates, write_candidates
from src.memory.embedding_identity import transversal_synthesis_embedding_identity
from src.memory.memory_db_path import resolve_memory_db_path
from src.memory.repos_memory.processing_catalog_repo import MemoryProcessingCatalogRepository
from src.memory.repos_memory.work_catalog_repo import MemoryWorkCatalogRepository
from src.memory.synthesis.session import discover_session_summary_artifacts


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _default_target_date(now: datetime | None = None) -> date:
    current = now or datetime.now()
    if current.hour < 4:
        return (current - timedelta(days=1)).date()
    return current.date()


def transversal_synthesis_path(
    target_date: date | str,
    root: str | Path | None = None,
    output_dir: str = "memory/transversal",
) -> Path:
    """Return the daily transversal synthesis artifact path."""

    date_str = target_date.isoformat() if isinstance(target_date, date) else str(target_date)
    year, month, day = date_str.split("-")
    base = Path(root) if root is not None else _project_root()
    return base / output_dir / year / month / f"{day}.md"


def transversal_synthesis_candidate_path(
    target_date: date | str,
    root: str | Path | None = None,
) -> Path:
    """Return the daily candidate path generated from transversal synthesis."""

    date_str = target_date.isoformat() if isinstance(target_date, date) else str(target_date)
    year, month, day = date_str.split("-")
    base = Path(root) if root is not None else _project_root()
    return base / "memory" / "candidates" / year / month / f"{day}.transversal_synthesis.jsonl"


def _extract_metadata(text: str) -> dict[str, Any]:
    marker = "<!-- metadata:"
    if marker not in text:
        return {}
    raw = text.split(marker, 1)[1].split("-->", 1)[0].strip()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _tokenize(text: str) -> list[str]:
    stop = {
        "assistant", "channel", "content", "extractive", "first", "last",
        "message", "messages", "metadata", "session", "snapshot", "summary",
        "user", "para", "pero", "como", "todo", "esta", "este", "esto",
        "sobre", "cuando", "porque", "tiene", "hacer", "desde", "entre",
    }
    tokens: list[str] = []
    for raw in re.findall(r"[A-Za-zÁÉÍÓÚáéíóúÑñ0-9_.-]{4,}", text or ""):
        token = raw.lower().strip("._-")
        if not token or token in stop or token.isdigit():
            continue
        tokens.append(token)
    return tokens


def _summary_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("<!--") or line.startswith("#"):
            continue
        if line.startswith("- "):
            line = line[2:].strip()
        lines.append(line)
    return lines


def _clip(text: str, limit: int = 500) -> str:
    clean = re.sub(r"\s+", " ", text or "").strip()
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1].rstrip() + "..."


def _infer_entities(text: str) -> list[str]:
    hints = {
        "Mauro": ("mauro",),
        "Kairos": ("kairos", "k-chat", "k chat"),
        "Codex": ("codex",),
        "Telegram": ("telegram",),
        "PC": (" pc ", "windows"),
        "laptop": ("laptop", "notebook"),
        "MEMORY.md": ("memory.md",),
        "memoria": ("memoria", "memory"),
        "embedding": ("embedding", "embeddings", "vector"),
        "grafo": ("grafo", "grafos", "graph"),
        "curador": ("curador", "curadores", "curaduria", "curaduría"),
        "pipeline": ("pipeline",),
    }
    lowered = f" {text.lower()} "
    entities = []
    for name, needles in hints.items():
        if any(needle in lowered for needle in needles):
            entities.append(name)
    return entities


def _date_matches(artifact: Mapping[str, Any], target: date) -> bool:
    metadata = artifact.get("metadata") if isinstance(artifact.get("metadata"), Mapping) else {}
    created_at = str(metadata.get("created_at") or "")
    if created_at.startswith(target.isoformat()):
        return True
    path = str(artifact.get("path") or "")
    return target.isoformat() in path


def select_transversal_inputs(
    artifacts: Iterable[Mapping[str, Any]],
    target_date: date,
) -> list[dict[str, Any]]:
    """Select summary artifacts that belong to the transversal synthesis date."""

    selected: list[dict[str, Any]] = []
    for artifact in artifacts:
        if _date_matches(artifact, target_date):
            selected.append(dict(artifact))
    return selected


def build_transversal_synthesis(
    artifacts: Iterable[Mapping[str, Any]],
    target_date: date,
) -> dict[str, Any]:
    """Build a deterministic cross-session synthesis payload."""

    selected = select_transversal_inputs(artifacts, target_date)
    token_sessions: dict[str, set[str]] = defaultdict(set)
    token_counts: Counter[str] = Counter()
    entity_sessions: dict[str, set[str]] = defaultdict(set)
    entity_counts: Counter[str] = Counter()
    evidence: dict[str, list[dict[str, str]]] = defaultdict(list)
    channels: Counter[str] = Counter()

    for artifact in selected:
        session_id = str(artifact.get("session_id") or "")
        channel = str(artifact.get("channel") or "web")
        text = str(artifact.get("text") or "")
        channels[channel] += 1
        lines = _summary_lines(text)
        for token in _tokenize(text):
            token_counts[token] += 1
            if session_id:
                token_sessions[token].add(session_id)
            if len(evidence[token]) < 3:
                source_line = next((line for line in lines if token in line.lower()), "")
                if source_line:
                    evidence[token].append(
                        {
                            "session_id": session_id,
                            "channel": channel,
                            "line": source_line,
                        }
                    )
        for entity in _infer_entities(text):
            entity_counts[entity] += 1
            if session_id:
                entity_sessions[entity].add(session_id)

    repeated_topics = []
    for token, count in token_counts.most_common():
        sessions = sorted(token_sessions.get(token, set()))
        if len(sessions) < 2 and count < 3:
            continue
        repeated_topics.append(
            {
                "topic": token,
                "mentions": count,
                "session_count": len(sessions),
                "sessions": sessions,
                "evidence": evidence.get(token, []),
            }
        )
        if len(repeated_topics) >= 12:
            break

    repeated_entities = []
    for entity, count in entity_counts.most_common():
        sessions = sorted(entity_sessions.get(entity, set()))
        if len(sessions) < 2 and count < 2:
            continue
        repeated_entities.append(
            {
                "name": entity,
                "mentions": count,
                "session_count": len(sessions),
                "sessions": sessions,
            }
        )
        if len(repeated_entities) >= 12:
            break

    input_hash = content_hash(
        "\n".join(
            f"{item.get('session_id', '')}:{item.get('content_hash', '')}:{item.get('path', '')}"
            for item in selected
        ),
        limit=200000,
    )
    return {
        "date": target_date.isoformat(),
        "input_hash": input_hash,
        "session_count": len(selected),
        "channels": dict(sorted(channels.items())),
        "sources": [
            {
                "session_id": str(item.get("session_id") or ""),
                "channel": str(item.get("channel") or "web"),
                "path": str(item.get("path") or ""),
                "content_hash": str(item.get("content_hash") or ""),
            }
            for item in selected
        ],
        "repeated_topics": repeated_topics,
        "repeated_entities": repeated_entities,
    }


def render_transversal_synthesis(payload: Mapping[str, Any]) -> str:
    """Render a transversal synthesis payload as Markdown with metadata."""

    metadata = {
        "channels": payload.get("channels") if isinstance(payload.get("channels"), Mapping) else {},
        "date": payload.get("date", ""),
        "input_hash": payload.get("input_hash", ""),
        "session_count": payload.get("session_count", 0),
        "source": "transversal_synthesis",
        "sources": payload.get("sources") if isinstance(payload.get("sources"), list) else [],
    }
    lines = [
        f"<!-- metadata: {json.dumps(metadata, ensure_ascii=False, sort_keys=True)} -->",
        f"# Transversal Synthesis - {payload.get('date', '')}",
        "",
        "## Scope",
        "",
        f"- Sessions: {payload.get('session_count', 0)}",
    ]
    channels = payload.get("channels") if isinstance(payload.get("channels"), Mapping) else {}
    if channels:
        channel_text = ", ".join(f"{name}: {count}" for name, count in sorted(channels.items()))
        lines.append(f"- Channels: {channel_text}")

    lines.extend(["", "## Repeated Topics", ""])
    topics = payload.get("repeated_topics") if isinstance(payload.get("repeated_topics"), list) else []
    if topics:
        for topic in topics:
            sessions = ", ".join(str(item) for item in topic.get("sessions", []))
            lines.append(
                f"- `{topic.get('topic', '')}`: {topic.get('mentions', 0)} mentions "
                f"across {topic.get('session_count', 0)} sessions ({sessions})"
            )
            for item in topic.get("evidence", [])[:2]:
                lines.append(
                    f"  - {item.get('channel', 'web')}:{item.get('session_id', '')} "
                    f"{item.get('line', '')}"
                )
    else:
        lines.append("- No repeated topics detected yet.")

    lines.extend(["", "## Repeated Entities", ""])
    entities = payload.get("repeated_entities") if isinstance(payload.get("repeated_entities"), list) else []
    if entities:
        for entity in entities:
            sessions = ", ".join(str(item) for item in entity.get("sessions", []))
            lines.append(
                f"- {entity.get('name', '')}: {entity.get('mentions', 0)} mentions "
                f"across {entity.get('session_count', 0)} sessions ({sessions})"
            )
    else:
        lines.append("- No repeated entities detected yet.")

    lines.extend(["", "## Sources", ""])
    sources = payload.get("sources") if isinstance(payload.get("sources"), list) else []
    if sources:
        for source in sources:
            lines.append(
                f"- `{source.get('session_id', '')}` ({source.get('channel', 'web')}): "
                f"{source.get('path', '')}"
            )
    else:
        lines.append("- No session summaries available for this date.")
    return "\n".join(lines).rstrip() + "\n"


def discover_transversal_synthesis_artifacts(
    root: str | Path | None = None,
    output_dir: str = "memory/transversal",
) -> list[dict[str, Any]]:
    """Discover transversal synthesis artifacts."""

    base = (Path(root) if root is not None else _project_root()) / output_dir
    if not base.exists():
        return []
    artifacts: list[dict[str, Any]] = []
    for path in sorted(base.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        metadata = _extract_metadata(text)
        date_key = str(metadata.get("date") or path.stem)
        artifacts.append(
            {
                "date": date_key,
                "path": str(path),
                "text": text,
                "content_hash": content_hash(text, limit=200000),
                "metadata": metadata,
            }
        )
    return artifacts


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

    text = str(artifact.get("text") or "")
    topic_lines = [
        line for line in _section_lines(text, "Repeated Topics")
        if line.startswith("- `") and "No repeated" not in line
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
    output_dir: str = "memory/transversal",
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Materialize candidates derived from transversal synthesis artifacts."""

    target = target_date or _default_target_date()
    path = transversal_synthesis_candidate_path(target, root=root)
    existing = load_candidates(path)
    by_id = {str(candidate.get("candidate_id")): dict(candidate) for candidate in existing}
    created = 0
    for artifact in discover_transversal_synthesis_artifacts(root=root, output_dir=output_dir):
        if str(artifact.get("date") or "") != target.isoformat():
            continue
        for candidate in candidates_from_transversal_synthesis_artifact(artifact, timestamp=timestamp):
            cid = str(candidate.get("candidate_id") or "")
            if cid in by_id:
                continue
            by_id[cid] = candidate
            created += 1

    if by_id:
        write_candidates(path, list(by_id.values()))
    return {
        "path": str(path),
        "created": created,
        "total": len(by_id),
    }


def generate_transversal_synthesis(
    root: str | Path | None = None,
    target_date: date | None = None,
    session_summary_dir: str = "memory/session_summaries",
    output_dir: str = "memory/transversal",
) -> dict[str, Any]:
    """Generate an idempotent daily synthesis across session summaries."""

    target = target_date or _default_target_date()
    artifacts = discover_session_summary_artifacts(root=root, output_dir=session_summary_dir)
    payload = build_transversal_synthesis(artifacts, target)
    rendered = render_transversal_synthesis(payload)
    digest = content_hash(rendered, limit=200000)
    path = transversal_synthesis_path(target, root=root, output_dir=output_dir)
    catalog = MemoryProcessingCatalogRepository(resolve_memory_db_path())
    unchanged = path.exists() and catalog.is_processed(
        source="transversal_synthesis",
        source_key=target.isoformat(),
        item_idx=-1,
        stage="generated",
        content_hash=digest,
    )
    if not unchanged:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8")
        catalog.mark(
            source="transversal_synthesis",
            source_key=target.isoformat(),
            item_idx=-1,
            stage="generated",
            content_hash=digest,
            status="processed",
            processor="generate_transversal_synthesis",
            metadata={
                "path": str(path),
                "session_count": payload.get("session_count", 0),
                "input_hash": payload.get("input_hash", ""),
            },
        )
    return {
        "path": str(path),
        "changed": not unchanged,
        "content_hash": digest,
        "session_count": payload.get("session_count", 0),
        "repeated_topic_count": len(payload.get("repeated_topics", [])),
        "repeated_entity_count": len(payload.get("repeated_entities", [])),
    }


def _transversal_catalog_is_processed(
    catalog: MemoryWorkCatalogRepository,
    artifact: Mapping[str, Any],
) -> bool:
    identity = transversal_synthesis_embedding_identity()
    return catalog.is_processed(
        source="transversal_synthesis",
        source_key=str(artifact.get("date") or ""),
        item_idx=-1,
        content_hash=str(artifact.get("content_hash") or ""),
        **identity.as_catalog_kwargs(),
    )


def _transversal_catalog_mark(
    catalog: MemoryWorkCatalogRepository,
    artifact: Mapping[str, Any],
    status: str,
    *,
    vec_rowid: int | None = None,
    reason: str = "",
    source_node_id: str = "",
) -> None:
    identity = transversal_synthesis_embedding_identity()
    catalog.mark(
        source="transversal_synthesis",
        source_key=str(artifact.get("date") or ""),
        item_idx=-1,
        content_hash=str(artifact.get("content_hash") or ""),
        status=status,
        vec_rowid=vec_rowid,
        reason=reason,
        metadata={"path": artifact.get("path", "")},
        source_node_id=source_node_id,
        **identity.as_catalog_kwargs(),
    )


async def vectorize_transversal_synthesis_artifacts(
    root: str | Path | None = None,
    output_dir: str = "memory/transversal",
    store: Any = None,
    catalog: MemoryWorkCatalogRepository | None = None,
    source_node_id: str = "",
) -> dict[str, int]:
    """Embed transversal synthesis artifacts as ``source=transversal_synthesis``."""

    from src.memory.embeddings.service import generate_embeddings_batch

    artifacts = discover_transversal_synthesis_artifacts(root=root, output_dir=output_dir)
    result = {
        "artifacts": len(artifacts),
        "embedded": 0,
        "deduped": 0,
        "unchanged": 0,
        "failed": 0,
    }
    if not artifacts:
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

    candidates: list[dict[str, Any]] = []
    try:
        for artifact in artifacts:
            try:
                if _transversal_catalog_is_processed(catalog, artifact):
                    result["unchanged"] += 1
                    continue
                existing = store._get_conn().execute(
                    "SELECT rowid FROM vec_meta WHERE content_hash = ?",
                    (artifact["content_hash"],),
                ).fetchone()
                if existing is not None:
                    _transversal_catalog_mark(
                        catalog,
                        artifact,
                        "deduped",
                        vec_rowid=int(existing[0]),
                        reason="content_hash",
                        source_node_id=source_node_id,
                    )
                    result["deduped"] += 1
                    continue
                candidates.append(artifact)
            except Exception:
                result["failed"] += 1

        if candidates:
            vectors = await asyncio.to_thread(
                generate_embeddings_batch,
                [str(item["text"])[:4000] for item in candidates],
            )
            for artifact, vector in zip(candidates, vectors):
                try:
                    rowid = store.insert(
                        vector,
                        source="transversal_synthesis",
                        source_key=str(artifact["date"]),
                        exchange_idx=-1,
                        text=str(artifact["text"])[:4000],
                        metadata={"path": artifact.get("path", "")},
                        hash=str(artifact["content_hash"]),
                        content_hash=str(artifact["content_hash"]),
                        source_node_id=source_node_id,
                    )
                    _transversal_catalog_mark(
                        catalog,
                        artifact,
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
