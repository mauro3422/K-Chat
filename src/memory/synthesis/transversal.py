"""Transversal synthesis across per-session summaries."""

from __future__ import annotations

import asyncio
import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping

from src.memory import paths as memory_paths
from src.memory.content_hash import content_hash
from src.memory.curator.candidate_quality import evaluate_candidate_signal
from src.memory.curator.recall_review import load_candidates, write_candidates
from src.memory.embedding_identity import transversal_synthesis_embedding_identity
from src.memory.memory_db_path import resolve_memory_db_path
from src.memory.repos_memory.processing_catalog_repo import MemoryProcessingCatalogRepository
from src.memory.repos_memory.work_catalog_repo import MemoryWorkCatalogRepository
from src.memory.synthesis.session import discover_session_summary_artifacts
from src.memory.synthesis.transversal_candidates import (
    candidates_from_transversal_synthesis_artifact,
    generate_transversal_synthesis_candidates,
)
from src.memory.synthesis.transversal_vectorize import (
    vectorize_transversal_synthesis_artifacts,
)

_project_root = memory_paths._project_root
_default_target_date = memory_paths._default_target_date


def transversal_synthesis_path(
    target_date: date | str | None = None,
    root: str | Path | None = None,
) -> Path:
    """Return the daily transversal synthesis artifact path.

    Now lives in ``memory/YYYY/MM/DD/transversal.md``.
    """
    return memory_paths.transversal_path(target=target_date, root=root)


def transversal_synthesis_candidate_path(
    target_date: date | str | None = None,
    root: str | Path | None = None,
) -> Path:
    """Return the daily candidate path generated from transversal synthesis."""
    return memory_paths.transversal_candidate_path(target=target_date, root=root)


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
    tokens: list[str] = []
    for raw in re.findall(r"[^\W_]+(?:[._-][^\W_]+)*", text or "", re.UNICODE):
        token = raw.lower().strip("._-")
        if not evaluate_candidate_signal(token).accepted:
            continue
        tokens.append(token)
    return tokens


def _is_actionable_topic(topic: str) -> bool:
    return evaluate_candidate_signal(topic).accepted


def _summary_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("<!--") or line.startswith("#"):
            continue
        if _is_operational_metadata_line(line):
            continue
        if line.startswith("- "):
            line = line[2:].strip()
        lines.append(line)
    return lines


def _is_operational_metadata_line(line: str) -> bool:
    """Return whether a whole line is pipeline metadata, not user content.

    Only treat known metadata when it starts the bullet. A sentence such as
    ``We discussed the artifact: provenance`` remains valid semantic input.
    """

    normalized = line.lstrip("-* ").strip().lower()
    prefixes = (
        "blended coherence",
        "lsa rel=",
        "pmi rel=",
        "content_hash:",
        "session:",
        "channel:",
        "messages:",
        "artifact:",
        "metadata:",
    )
    return normalized.startswith(prefixes)


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
        semantic_text = "\n".join(lines)
        # Track which (session_id, line) we've already added as evidence per token
        seen_token_evidence: dict[str, set[tuple[str, str]]] = defaultdict(set)
        for token in _tokenize(semantic_text):
            if not _is_actionable_topic(token):
                continue
            token_counts[token] += 1
            if session_id:
                token_sessions[token].add(session_id)
            if len(evidence[token]) < 3:
                source_line = next((line for line in lines if token in line.lower()), "")
                if source_line:
                    dedup_key = (session_id, source_line)
                    if dedup_key not in seen_token_evidence[token]:
                        seen_token_evidence[token].add(dedup_key)
                        evidence[token].append(
                            {
                                "session_id": session_id,
                                "channel": channel,
                                "line": source_line,
                            }
                        )
        for entity in _infer_entities(semantic_text):
            entity_counts[entity] += 1
            if session_id:
                entity_sessions[entity].add(session_id)

    repeated_topics = []
    for token, count in token_counts.most_common():
        sessions = sorted(token_sessions.get(token, set()))
        if len(sessions) < 2:
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
                "path": Path(str(item.get("path") or "")).name,
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
) -> list[dict[str, Any]]:
    """Discover transversal synthesis artifacts from ``memory/*/*/*/transversal.md``."""

    base = Path(root) if root is not None else _project_root()
    artifacts: list[dict[str, Any]] = []
    for path in sorted(base.glob("memory/*/*/*/transversal.md")):
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


def generate_transversal_synthesis(
    root: str | Path | None = None,
    target_date: date | None = None,
) -> dict[str, Any]:
    """Generate an idempotent daily synthesis across session summaries."""

    target = target_date or _default_target_date()
    artifacts = discover_session_summary_artifacts(root=root)
    payload = build_transversal_synthesis(artifacts, target)
    rendered = render_transversal_synthesis(payload)
    digest = content_hash(rendered, limit=200000)
    path = transversal_synthesis_path(target, root=root)
    catalog = MemoryProcessingCatalogRepository(resolve_memory_db_path())
    file_digest = ""
    if path.exists():
        file_digest = content_hash(path.read_text(encoding="utf-8", errors="replace"), limit=200000)
    unchanged = file_digest == digest and catalog.is_processed(
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
