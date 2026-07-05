"""Extractive per-session synthesis artifacts."""

from __future__ import annotations

import asyncio
import logging
import hashlib
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping

import aiosqlite

from src.memory import paths as memory_paths
from src.memory.content_hash import content_hash
from src.memory.embedding_identity import session_summary_embedding_identity
from src.memory.memory_db_path import resolve_memory_db_path
from src.memory.curator.recall_review import load_candidates, write_candidates
from src.memory.repos_memory.processing_catalog_repo import MemoryProcessingCatalogRepository
from src.memory.repos_memory.work_catalog_repo import MemoryWorkCatalogRepository

logger = logging.getLogger(__name__)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _default_target_date(now: datetime | None = None) -> date:
    current = now or datetime.now()
    if current.hour < 4:
        return (current - timedelta(days=1)).date()
    return current.date()


def session_summary_path(
    session_id: str,
    channel: str = "web",
    target: date | str | None = None,
    root: str | Path | None = None,
) -> Path:
    """Return the Markdown artifact path for a session summary.

    Now lives in ``memory/YYYY/MM/DD/session--{channel}--{id}.md``.
    """
    return memory_paths.session_summary_path(session_id, channel=channel, target=target, root=root)


def session_summary_candidate_path(
    target_date: date | str | None = None,
    root: str | Path | None = None,
) -> Path:
    """Return the daily candidate path generated from session summaries."""
    return memory_paths.session_summary_candidate_path(target=target_date, root=root)


async def _has_column(db: aiosqlite.Connection, table: str, column: str) -> bool:
    cursor = await db.execute(f"PRAGMA table_info({table})")
    rows = await cursor.fetchall()
    return any(row[1] == column for row in rows)


async def _table_columns(db: aiosqlite.Connection, table: str) -> set[str]:
    cursor = await db.execute(f"PRAGMA table_info({table})")
    rows = await cursor.fetchall()
    return {str(row[1]) for row in rows}


def _normalize_session_channel(row: Mapping[str, Any]) -> str:
    for key in ("channel", "source_channel", "origin_channel"):
        value = str(row.get(key) or "").strip().lower()
        if value:
            return re.sub(r"[^a-z0-9_.-]+", "_", value).strip("_") or "web"

    source = str(row.get("source") or "").strip().lower()
    if source in {"telegram", "web", "cli", "codex", "desktop"}:
        return source

    if row.get("telegram_chat_id"):
        return "telegram"

    return "web"


async def get_sessions_for_summary_date(db_path: str, date_str: str) -> list[dict[str, Any]]:
    """Return session rows for a target date, with best-effort channel metadata."""

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        table_columns = await _table_columns(db, "sessions")
        columns = "session_id, name, created_at"
        for optional in ("channel", "source_channel", "origin_channel", "source", "telegram_chat_id"):
            if optional in table_columns:
                columns += f", {optional}"
        cursor = await db.execute(
            f"SELECT {columns} FROM sessions WHERE date(created_at) = ? ORDER BY created_at",
            (date_str,),
        )
        sessions = []
        for row in await cursor.fetchall():
            item = dict(row)
            item["channel"] = _normalize_session_channel(item)
            sessions.append(item)
        return sessions


async def get_session_messages_for_summary(
    db_path: str,
    session_id: str,
    limit: int = 500,
) -> list[dict[str, Any]]:
    """Return messages for a session as dictionaries."""

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, role, content, created_at FROM messages "
            "WHERE session_id = ? ORDER BY id ASC LIMIT ?",
            (session_id, limit),
        )
        return [dict(row) for row in await cursor.fetchall()]


def _message_digest(messages: Iterable[dict[str, Any]]) -> str:
    chunks = [
        f"{item.get('role', '')}\n{item.get('created_at', '')}\n{item.get('content', '')}"
        for item in messages
    ]
    return content_hash("\n\n---\n\n".join(chunks), limit=100000)


def _clip(text: str, limit: int = 260) -> str:
    clean = re.sub(r"\s+", " ", text or "").strip()
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1].rstrip() + "..."


def _candidate_id(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(dict(payload), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _keywords(messages: list[dict[str, Any]], limit: int = 10) -> list[str]:
    stop = {
        "para", "pero", "como", "todo", "esta", "este", "esto", "tiene",
        "sobre", "cuando", "porque", "then", "with", "that", "this", "from",
    }
    # Code-related tokens to exclude from conversational keywords
    code_tokens = {
        "none", "import", "_deps", "self", "return", "logger", "config",
        "async", "await", "true", "false", "class", "function", "const",
        "var", "let", "def", "type", "null", "undefined", "lambda",
        "raise", "except", "finally", "yield", "global", "nonlocal",
        "print", "len", "str", "int", "dict", "list", "tuple", "set",
        "range", "enumerate", "zip", "map", "filter", "sorted",
        "property", "staticmethod", "classmethod", "super", "object",
        "value", "values", "items", "keys", "key",
    }
    counts: dict[str, int] = {}
    for message in messages:
        # Only extract keywords from user messages (less code noise)
        if message.get("role") != "user":
            continue
        for word in re.findall(r"[A-Za-zÁÉÍÓÚáéíóúÑñ0-9_]{4,}", message.get("content") or ""):
            normalized = word.lower()
            if normalized in stop or normalized in code_tokens:
                continue
            counts[normalized] = counts.get(normalized, 0) + 1
    # Fallback: if no user messages, extract from assistant but filter code
    if not counts:
        for message in messages:
            if message.get("role") != "assistant":
                continue
            for word in re.findall(r"[A-Za-zÁÉÍÓÚáéíóúÑñ0-9_]{4,}", message.get("content") or ""):
                normalized = word.lower()
                if normalized in stop or normalized in code_tokens:
                    continue
                counts[normalized] = counts.get(normalized, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [word for word, _ in ranked[:limit]]


def build_session_summary(
    session: dict[str, Any],
    messages: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a deterministic summary payload for one session."""

    user_messages = [m for m in messages if m.get("role") == "user"]
    assistant_messages = [m for m in messages if m.get("role") == "assistant"]
    first_user = _clip(user_messages[0].get("content", "")) if user_messages else ""
    last_user = _clip(user_messages[-1].get("content", "")) if user_messages else ""
    last_assistant = _clip(assistant_messages[-1].get("content", "")) if assistant_messages else ""
    return {
        "session_id": session.get("session_id", ""),
        "name": session.get("name") or "",
        "channel": session.get("channel") or "web",
        "created_at": session.get("created_at") or "",
        "message_count": len(messages),
        "user_message_count": len(user_messages),
        "assistant_message_count": len(assistant_messages),
        "content_hash": _message_digest(messages),
        "keywords": _keywords(messages),
        "first_user": first_user,
        "last_user": last_user,
        "last_assistant": last_assistant,
    }


def render_session_summary(summary: dict[str, Any]) -> str:
    """Render a per-session summary as Markdown with metadata."""

    title = summary.get("name") or summary.get("session_id", "")[:12] or "Session"
    metadata = {
        "session_id": summary.get("session_id", ""),
        "channel": summary.get("channel", "web"),
        "created_at": summary.get("created_at", ""),
        "content_hash": summary.get("content_hash", ""),
        "message_count": summary.get("message_count", 0),
    }
    lines = [
        f"<!-- metadata: {json.dumps(metadata, ensure_ascii=False, sort_keys=True)} -->",
        f"# Session Summary - {title}",
        "",
        "## Snapshot",
        "",
        f"- Session: `{summary.get('session_id', '')}`",
        f"- Channel: {summary.get('channel', 'web')}",
        f"- Messages: {summary.get('message_count', 0)}",
        f"- User messages: {summary.get('user_message_count', 0)}",
        f"- Assistant messages: {summary.get('assistant_message_count', 0)}",
    ]
    if summary.get("keywords"):
        lines.append(f"- Keywords: {', '.join(summary['keywords'])}")
    lines.extend(["", "## Extractive Notes", ""])
    for label, key in (
        ("First user message", "first_user"),
        ("Last user message", "last_user"),
        ("Last assistant message", "last_assistant"),
    ):
        if summary.get(key):
            lines.append(f"- **{label}**: {summary[key]}")
    if not any(summary.get(key) for key in ("first_user", "last_user", "last_assistant")):
        lines.append("- No message content available.")
    return "\n".join(lines).rstrip() + "\n"


async def generate_session_summaries(
    db_path: str,
    target_date: date | None = None,
    root: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Generate idempotent extractive summaries for sessions on a date."""

    target = target_date or _default_target_date()
    date_str = target.isoformat()
    sessions = await get_sessions_for_summary_date(db_path, date_str)
    catalog = MemoryProcessingCatalogRepository(resolve_memory_db_path())
    results: list[dict[str, Any]] = []
    for session in sessions:
        session_id = str(session.get("session_id") or "")
        messages = await get_session_messages_for_summary(db_path, session_id)
        # Skip sessions with no messages — empty summaries add noise
        if not messages:
            continue
        summary = build_session_summary(session, messages)
        digest = str(summary["content_hash"])
        path = session_summary_path(
            session_id,
            channel=str(summary.get("channel") or "web"),
            target=target,
            root=root,
        )
        unchanged = path.exists() and catalog.is_processed(
            source="session_summary",
            source_key=session_id,
            item_idx=-1,
            stage="generated",
            content_hash=digest,
        )
        if not unchanged:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(render_session_summary(summary), encoding="utf-8")
            catalog.mark(
                source="session_summary",
                source_key=session_id,
                item_idx=-1,
                stage="generated",
                content_hash=digest,
                status="processed",
                processor="generate_session_summaries",
                metadata={
                    "channel": summary.get("channel", "web"),
                    "message_count": summary.get("message_count", 0),
                    "path": str(path),
                },
            )
        results.append({**summary, "path": str(path), "changed": not unchanged})
    return results


def load_session_summary_previews(
    session_ids: Iterable[str],
    root: str | Path | None = None,
    line_limit: int = 8,
) -> dict[str, dict[str, Any]]:
    """Load existing summary previews for a set of session IDs.

    Scans ``memory/*/*/*/session--*.md`` for matching session summaries.
    """

    base = Path(root) if root is not None else _project_root()
    previews: dict[str, dict[str, Any]] = {}
    candidates_dir = base / "memory"
    if not candidates_dir.exists():
        return previews
    wanted = set(session_ids)
    for path in sorted(candidates_dir.glob("*/*/*/session--*.md")):
        text = path.read_text(encoding="utf-8")
        metadata = _extract_metadata(text)
        session_id = str(metadata.get("session_id") or path.stem)
        if session_id not in wanted:
            continue
        lines = []
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("<!--"):
                continue
            lines.append(line)
            if len(lines) >= line_limit:
                break
        previews[session_id] = {"path": str(path), "metadata": metadata, "preview": lines}
    return previews


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


def discover_session_summary_artifacts(
    root: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Discover session summary Markdown artifacts under ``memory/*/*/*/session--*.md``."""

    base = Path(root) if root is not None else _project_root()
    artifacts: list[dict[str, Any]] = []
    for path in sorted(base.glob("memory/*/*/*/session--*.md")):
        text = path.read_text(encoding="utf-8")
        metadata = _extract_metadata(text)
        session_id = str(metadata.get("session_id") or path.stem)
        channel = str(metadata.get("channel") or "web")
        artifacts.append(
            {
                "session_id": session_id,
                "channel": channel,
                "path": str(path),
                "text": text,
                "content_hash": content_hash(text, limit=100000),
                "metadata": metadata,
            }
        )
    return artifacts


def _candidate_signal_lines(text: str) -> list[str]:
    signal_words = (
        "prefiere", "quiere", "decidio", "decidió", "decisión", "decision", "bug",
        "error", "falla", "pendiente", "plan", "roadmap", "memoria",
        "embedding", "curador", "curaduria", "curaduría", "pipeline", "telegram", "laptop",
    )
    lines: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("<!--") or line.startswith("#"):
            continue
        low = line.lower()
        if any(word in low for word in signal_words):
            lines.append(line)
        if len(lines) >= 8:
            break
    return lines


def _candidate_entity_hints(lines: list[str], artifact: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Infer lightweight entity hints for curator review."""

    text = " ".join(lines)
    hints = (
        ("Mauro", "person", ("mauro",)),
        ("Kairos", "project", ("kairos", "k-chat")),
        ("k-chat", "project", ("k-chat", "k chat")),
        ("Codex", "agent", ("codex",)),
        ("Telegram", "channel", ("telegram",)),
        ("PC", "device", ("pc",)),
        ("laptop", "device", ("laptop", "notebook")),
        ("MEMORY.md", "artifact", ("memory.md", "memory")),
        ("memoria", "concept", ("memoria", "memory")),
        ("embedding", "technology", ("embedding", "embeddings", "vector")),
        ("grafo", "concept", ("grafo", "grafos", "graph")),
        ("curador", "role", ("curador", "curadores", "curaduria")),
        ("pipeline", "system", ("pipeline",)),
    )
    lowered = text.lower()
    entities: list[dict[str, Any]] = []
    for name, entity_type, needles in hints:
        if any(needle in lowered for needle in needles):
            entities.append(
                {
                    "name": name,
                    "entity_type": entity_type,
                    "confidence": 0.7,
                    "evidence": next((line for line in lines if any(needle in line.lower() for needle in needles)), lines[0]),
                }
            )

    channel = str(artifact.get("channel") or "")
    if channel and not any(item["name"] == channel for item in entities):
        entities.append(
            {
                "name": channel,
                "entity_type": "channel",
                "confidence": 0.55,
                "evidence": "session metadata",
            }
        )
    return entities


def _candidate_temporal_metadata(timestamp: str) -> dict[str, str]:
    return {
        "first_seen": timestamp,
        "last_seen": timestamp,
        "status": "new",
    }


def _candidate_relation_policy(lines: list[str], session_id: str) -> dict[str, Any]:
    """Infer the curator-facing relation intent from summary language."""

    text = " ".join(lines).lower()
    rules = (
        (
            "CONTRADICTS",
            "memory:canonical",
            0.68,
            "summary_contradiction_signal",
            (
                "contradice",
                "contradiccion",
                "contradicción",
                "conflicto",
                "ya no",
                "en vez de",
                "cambio de decision",
                "cambio de decisión",
            ),
        ),
        (
            "REFINES",
            "memory:canonical",
            0.66,
            "summary_refinement_signal",
            (
                "refina",
                "refinar",
                "ajusta",
                "ajustar",
                "precisa",
                "mas especifico",
                "más específico",
                "mejorar metadata",
                "metadata",
            ),
        ),
        (
            "LINKS_TO",
            "memory:semantic-neighbor",
            0.64,
            "summary_link_signal",
            (
                "relaciona",
                "relacionar",
                "conecta",
                "conectar",
                "enlaza",
                "enlazar",
                "link",
                "transversal",
                "semantica",
                "semántica",
            ),
        ),
    )
    for relation_type, target_id, confidence, reason, needles in rules:
        if any(needle in text for needle in needles):
            return {
                "relation_type": relation_type,
                "target_id": target_id,
                "confidence": confidence,
                "reason": reason,
                "target_needs_resolution": True,
            }
    return {
        "relation_type": "DERIVED_FROM",
        "target_id": f"session:{session_id}" if session_id else "session:unknown",
        "confidence": 0.62,
        "reason": "session_summary_signal",
        "target_needs_resolution": False,
    }


def _candidate_relation_hints(
    candidate_id: str,
    session_id: str,
    artifact_path: str,
    entities: list[dict[str, Any]],
    policy: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Propose graph edges without mutating the graph."""

    session_node = f"session:{session_id}" if session_id else "session:unknown"
    relations: list[dict[str, Any]] = [
        {
            "source_id": f"candidate:{candidate_id}",
            "target_id": session_node,
            "relation_type": "DERIVED_FROM",
            "weight": 0.72,
            "provenance": "session_summary_candidate",
        }
    ]
    policy_relation = str(policy.get("relation_type") or "")
    policy_target = str(policy.get("target_id") or "")
    if policy_relation and policy_relation != "DERIVED_FROM" and policy_target:
        relations.append(
            {
                "source_id": f"candidate:{candidate_id}",
                "target_id": policy_target,
                "relation_type": policy_relation,
                "weight": float(policy.get("confidence") or 0.5),
                "provenance": str(policy.get("reason") or "session_summary_relation_signal"),
                "needs_resolution": bool(policy.get("target_needs_resolution")),
            }
        )
    if artifact_path:
        relations.append(
            {
                "source_id": f"candidate:{candidate_id}",
                "target_id": f"artifact:{hashlib.sha256(artifact_path.encode('utf-8')).hexdigest()[:16]}",
                "relation_type": "DERIVED_FROM",
                "weight": 0.62,
                "provenance": "session_summary_artifact",
            }
        )
    for entity in entities:
        name = str(entity.get("name") or "").strip()
        if not name:
            continue
        relations.append(
            {
                "source_id": session_node,
                "target_id": f"entity:{name.lower().replace(' ', '_')}",
                "relation_type": "MENTIONS",
                "weight": float(entity.get("confidence") or 0.5),
                "provenance": "session_summary_signal",
            }
        )
    return relations


def candidates_from_session_summary_artifact(
    artifact: Mapping[str, Any],
    timestamp: str | None = None,
) -> list[dict[str, Any]]:
    """Create conservative review candidates from a summary artifact."""

    text = str(artifact.get("text") or "")
    lines = _candidate_signal_lines(text)
    if not lines:
        return []

    ts = timestamp or datetime.now().isoformat(timespec="seconds")
    session_id = str(artifact.get("session_id") or "")
    channel = str(artifact.get("channel") or "web")
    artifact_path = str(artifact.get("path") or "")
    query = " ".join(line.lstrip("- ").strip() for line in lines[:3])
    entities = _candidate_entity_hints(lines, artifact)
    policy = _candidate_relation_policy(lines, session_id)
    payload = {
        "type": "session_summary_candidate",
        "source": "session_summary",
        "session_id": session_id,
        "channel": channel,
        "query": _clip(query, 500),
        "result_excerpt": _clip("\n".join(lines), 900),
        "source_artifact": artifact_path,
        "artifact": artifact_path,
        "content_hash": str(artifact.get("content_hash") or ""),
    }
    candidate_id = _candidate_id(payload)
    return [
        {
            **payload,
            "candidate_id": candidate_id,
            "status": "pending",
            "created_at": ts,
            "confidence": float(policy["confidence"]),
            "relation_type": str(policy["relation_type"]),
            "source_id": f"candidate:{candidate_id}",
            "target_id": str(policy["target_id"]),
            "target_needs_resolution": bool(policy["target_needs_resolution"]),
            "link_score": float(policy["confidence"]),
            "link_reasons": [str(policy["reason"]), "summary_entity_hints"],
            "entities": entities,
            "temporal": _candidate_temporal_metadata(ts),
            "provenance": {
                "session_id": session_id,
                "channel": channel,
                "artifact": artifact_path,
                "content_hash": str(artifact.get("content_hash") or ""),
            },
            "proposed_relations": _candidate_relation_hints(
                candidate_id,
                session_id,
                artifact_path,
                entities,
                policy,
            ),
        }
    ]


def generate_session_summary_candidates(
    root: str | Path | None = None,
    target_date: date | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Materialize reviewable candidates derived from session summaries."""

    target = target_date or _default_target_date()
    path = session_summary_candidate_path(target, root=root)
    existing = load_candidates(path)
    by_id = {str(candidate.get("candidate_id")): dict(candidate) for candidate in existing}
    created = 0
    for artifact in discover_session_summary_artifacts(root=root):
        for candidate in candidates_from_session_summary_artifact(artifact, timestamp=timestamp):
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


def _summary_catalog_is_processed(
    catalog: MemoryWorkCatalogRepository,
    artifact: Mapping[str, Any],
) -> bool:
    identity = session_summary_embedding_identity()
    return catalog.is_processed(
        source="session_summary",
        source_key=str(artifact.get("session_id") or ""),
        item_idx=-1,
        content_hash=str(artifact.get("content_hash") or ""),
        **identity.as_catalog_kwargs(),
    )


def _summary_catalog_mark(
    catalog: MemoryWorkCatalogRepository,
    artifact: Mapping[str, Any],
    status: str,
    *,
    vec_rowid: int | None = None,
    reason: str = "",
    source_node_id: str = "",
) -> None:
    identity = session_summary_embedding_identity()
    catalog.mark(
        source="session_summary",
        source_key=str(artifact.get("session_id") or ""),
        item_idx=-1,
        content_hash=str(artifact.get("content_hash") or ""),
        status=status,
        vec_rowid=vec_rowid,
        reason=reason,
        metadata={
            "path": artifact.get("path", ""),
            "channel": artifact.get("channel", "web"),
        },
        source_node_id=source_node_id,
        **identity.as_catalog_kwargs(),
    )


async def vectorize_session_summary_artifacts(
    root: str | Path | None = None,
    store: Any = None,
    catalog: MemoryWorkCatalogRepository | None = None,
    source_node_id: str = "",
) -> dict[str, int]:
    """Embed session summary artifacts as ``source=session_summary``."""

    from src.memory.embeddings.service import generate_embeddings_batch

    artifacts = discover_session_summary_artifacts(root=root)
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
                if _summary_catalog_is_processed(catalog, artifact):
                    result["unchanged"] += 1
                    continue
                existing = store._get_conn().execute(
                    "SELECT rowid FROM vec_meta WHERE content_hash = ?",
                    (artifact["content_hash"],),
                ).fetchone()
                if existing is not None:
                    _summary_catalog_mark(
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
                logger.exception("Failed to check dedup for artifact %s", artifact.get("session_id", "?"))
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
                        source="session_summary",
                        source_key=str(artifact["session_id"]),
                        exchange_idx=-1,
                        text=str(artifact["text"])[:4000],
                        metadata={
                            "path": artifact.get("path", ""),
                            "channel": artifact.get("channel", "web"),
                        },
                        hash=str(artifact["content_hash"]),
                        content_hash=str(artifact["content_hash"]),
                        source_node_id=source_node_id,
                    )
                    _summary_catalog_mark(
                        catalog,
                        artifact,
                        "embedded",
                        vec_rowid=rowid,
                        source_node_id=source_node_id,
                    )
                    result["embedded"] += 1
                except Exception:
                    logger.exception("Failed to insert embedding for artifact %s", artifact.get("session_id", "?"))
                    result["failed"] += 1
    finally:
        if own_store:
            store.close()

    return result
