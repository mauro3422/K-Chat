"""Extractive per-session synthesis artifacts."""

from __future__ import annotations

import asyncio
import logging
import hashlib
import json
import math
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

from src.memory.synthesis.candidates import (
    candidates_from_session_summary_artifact,
    generate_session_summary_candidates,
)
from src.memory.synthesis.vectorize import vectorize_session_summary_artifacts

# Mathematical analysis modules (optional — degrade gracefully)
try:
    from src.memory.analysis import (
        MemoryCorpus,
        EntityGraph,
        PMIClustering,
        SemanticSimilarity,
        CombinedScorer,
        keyword_rank_with_scores,
        candidate_confidence_from_scores,
        compute_statistical_thresholds,
        textrank_from_messages,
        LatentSemanticAnalysis,
        build_cross_turn_matrix,
        cross_pmi,
    )
    from src.memory.analysis.pmi_relations import calculate_pmi_for_session

    ANALYSIS_AVAILABLE = True
except ImportError as _exc:
    ANALYSIS_AVAILABLE = False
    CombinedScorer = None
    textrank_from_messages = None  # type: ignore
    LatentSemanticAnalysis = None  # type: ignore
    build_cross_turn_matrix = None  # type: ignore
    cross_pmi = None  # type: ignore
    logger.debug("Analysis modules not available: %s", _exc)

logger = logging.getLogger(__name__)


_project_root = memory_paths._project_root
_default_target_date = memory_paths._default_target_date


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


def _keywords(messages: list[dict[str, Any]], limit: int = 10) -> list[str]:
    try:
        from src.memory.analysis.corpus import STOP
    except ImportError:
        STOP = set()

    counts: dict[str, int] = {}
    for message in messages:
        # Only extract keywords from user messages (less code noise)
        if message.get("role") != "user":
            continue
        for word in re.findall(r"[A-Za-zÁÉÍÓÚáéíóúÑñ0-9_]{4,}", message.get("content") or ""):
            normalized = word.lower()
            if normalized in STOP:
                continue
            counts[normalized] = counts.get(normalized, 0) + 1
    # Fallback: if no user messages, extract from assistant but filter code/noise
    if not counts:
        for message in messages:
            if message.get("role") != "assistant":
                continue
            for word in re.findall(r"[A-Za-zÁÉÍÓÚáéíóúÑñ0-9_]{4,}", message.get("content") or ""):
                normalized = word.lower()
                if normalized in STOP:
                    continue
                counts[normalized] = counts.get(normalized, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [word for word, _ in ranked[:limit]]


def _keywords_scored(
    messages: list[dict[str, Any]],
    scorer: "CombinedScorer | None" = None,
    limit: int = 10,
) -> list[str]:
    """Extract keywords with mathematical scoring (TF-IDF/BM25/centrality/PMI).

    Extracts from **both** user and assistant messages, merging their signals.
    Terms that appear in both roles get a cross-coherence bonus because
    they represent conversational focus (both parties talking about the
    same concept).

    Falls back to raw-count ranking if ``scorer`` is None.
    Uses the consolidated stopword list from ``analysis.corpus.tokenize_doc``.
    """
    from src.memory.analysis.corpus import STOP, strip_code

    # Skip system-injected messages (retry errors, forwarded content)
    def _is_organic(msg: dict[str, Any]) -> bool:
        content = str(msg.get("content") or "")
        return not content.startswith("[SYSTEM:")

    # Cap per-term per-message to prevent inline pasted content from dominating
    _MAX_PER_MSG = 30

    # Extract counts per role separately so we can compute cross-coherence
    counts: dict[str, int] = {}          # merged count (both roles)
    user_count: dict[str, int] = {}      # only user
    asst_count: dict[str, int] = {}      # only assistant

    for message in messages:
        role = str(message.get("role") or "")
        if role not in ("user", "assistant"):
            continue
        if not _is_organic(message):
            continue

        msg_tokens: dict[str, int] = {}
        # Strip code blocks before keyword extraction to prevent code noise
        clean_content = strip_code(str(message.get("content") or ""))
        for word in re.findall(r"[A-Za-zÁÉÍÓÚáéíóúÑñ0-9_]{4,}", clean_content):
            normalized = word.lower().strip("._-")
            if normalized in STOP or len(normalized) < 4:
                continue
            msg_tokens[normalized] = msg_tokens.get(normalized, 0) + 1

        target = user_count if role == "user" else asst_count
        for token, token_count in msg_tokens.items():
            capped = min(token_count, _MAX_PER_MSG)
            target[token] = target.get(token, 0) + capped
            counts[token] = counts.get(token, 0) + capped

    if not counts:
        return []

    # Cross-coherence bonus: terms appearing in BOTH roles get a multiplier
    # because they represent shared conversational focus.
    cross_terms = set(user_count) & set(asst_count)
    for term in cross_terms:
        counts[term] = int(counts[term] * 1.5)  # +50% boost for mutual terms

    if scorer is not None and ANALYSIS_AVAILABLE:
        doc_len = sum(len(m.get("content", "").split()) for m in messages if _is_organic(m)) + 1

        # Compute TextRank scores per-term for this session
        textrank_scores: dict[str, float] = {}
        if textrank_from_messages is not None:
            try:
                tr_terms = textrank_from_messages(
                    messages, include_roles=("user", "assistant"), limit=30
                )
                textrank_scores = dict(tr_terms)
            except Exception:
                pass

        ranked = scorer.score_keywords_batch(
            list(counts.items()), doc_len, textrank_scores=textrank_scores
        )
        return [term for term, _ in ranked[:limit]]

    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [word for word, _ in ranked[:limit]]


def build_session_summary(
    session: dict[str, Any],
    messages: list[dict[str, Any]],
    scorer: "CombinedScorer | None" = None,
    word_idf: dict[str, float] | None = None,
    max_idf: float = 4.0,
    stem_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build a deterministic summary payload for one session.

    When the scorer is available, also computes:
    - TextRank (intra-session word graph) — per-term scores
    - LSA coherence (cross-role topic alignment via SVD)
    - Cross-PMI (user↔assistant term pair strength)
    - IDF-weighted PMI (when word_idf + stem_map provided)

    Parameters
    ----------
    session : dict
        Session row from the DB.
    messages : list[dict]
        Message rows for the session.
    scorer : CombinedScorer | None
        Optional mathematical scorer.
    word_idf : dict | None
        Global IDF weights per stem. When provided, PMI uses IDF weighting.
    max_idf : float
        Maximum IDF value in the corpus (for normalization).
    stem_map : dict | None
        Raw token → stem mapping. When provided, PMI uses stemming.
    """

    user_messages = [m for m in messages if m.get("role") == "user"]
    assistant_messages = [m for m in messages if m.get("role") == "assistant"]
    first_user = _clip(user_messages[0].get("content", "")) if user_messages else ""
    last_user = _clip(user_messages[-1].get("content", "")) if user_messages else ""
    last_assistant = _clip(assistant_messages[-1].get("content", "")) if assistant_messages else ""

    # Use scored keywords when scorer is available
    if scorer is not None and ANALYSIS_AVAILABLE:
        keywords = _keywords_scored(messages, scorer=scorer)
    else:
        keywords = _keywords(messages)

    # Compute conversation-level analytics (LSA, cross-PMI)
    lsa_coherence = 0.0
    lsa_reliability = 0.0
    cross_pmi_score = 0.0
    pmi_reliability = 0.0
    blended_coherence = 0.0

    _organic = [m for m in messages if not str(m.get("content", "")).startswith("[SYSTEM:")]

    pmi_entities_set = set()
    if _organic and ANALYSIS_AVAILABLE:
        pmi_relations, _ = calculate_pmi_for_session(
            [str(m.get("content", "")) for m in _organic],
            word_idf=word_idf,
            max_idf=max_idf,
            stem_map=stem_map,
        )
        from src.memory.analysis.pmi_relations import persist_pmi_relations
        from src.memory.memory_db_path import resolve_memory_db_path
        persist_pmi_relations(resolve_memory_db_path(), pmi_relations)
        for a, b, _ in pmi_relations:
            pmi_entities_set.add(a)
            pmi_entities_set.add(b)
    pmi_entities = sorted(list(pmi_entities_set))

    if LatentSemanticAnalysis is not None and len(_organic) >= 4:
        try:
            lsa = LatentSemanticAnalysis(n_topics=min(5, len(_organic) // 2)).fit(_organic)
            cross_sims = lsa.cross_role_similarities()
            if cross_sims:
                raw_coherence = sum(s for _, _, s in cross_sims) / len(cross_sims)
                # Clamp to [0, 1]: SVD topic vectors can be negative (opposite
                # directions), which gives negative cosine.  Zero means "no
                # topic alignment" which is the floor for coherence.
                lsa_coherence = round(max(0.0, raw_coherence), 4)
            # Reliability: LSA needs user turns to find topics
            lsa_reliability = round(min(1.0, lsa.n_user_turns / 5), 4)
        except Exception as exc:
            logger.debug("LSA coherence failed: %s", exc)

    if build_cross_turn_matrix is not None and cross_pmi is not None and len(_organic) >= 4:
        try:
            matrix = build_cross_turn_matrix(_organic, window=1)
            pmi_scores = cross_pmi(matrix, min_cooc=1)
            n_pairs = len(pmi_scores)
            if pmi_scores:
                mean_pmi = sum(pmi_scores.values()) / n_pairs
                # Sigmoid normalisation: PMI ∈ ℝ → [0, 1]
                cross_pmi_score = round(1.0 / (1.0 + math.exp(-mean_pmi)), 4)
            # Reliability: PMI needs enough term pairs to be stable
            pmi_reliability = round(min(1.0, n_pairs / 10), 4)
        except Exception as exc:
            logger.debug("Cross-PMI failed: %s", exc)

    # Blended coherence: weighted by reliability of each signal
    denom = lsa_reliability + pmi_reliability + 1e-12
    blended_coherence = round(
        (lsa_reliability * lsa_coherence + pmi_reliability * cross_pmi_score) / denom,
        4,
    )

    return {
        "session_id": session.get("session_id", ""),
        "name": session.get("name") or "",
        "channel": session.get("channel") or "web",
        "created_at": session.get("created_at") or "",
        "message_count": len(messages),
        "user_message_count": len(user_messages),
        "assistant_message_count": len(assistant_messages),
        "content_hash": _message_digest(messages),
        "keywords": keywords,
        "first_user": first_user,
        "last_user": last_user,
        "last_assistant": last_assistant,
        "lsa_coherence": lsa_coherence,
        "lsa_reliability": lsa_reliability,
        "cross_pmi_score": cross_pmi_score,
        "pmi_reliability": pmi_reliability,
        "blended_coherence": blended_coherence,
        "pmi_entities": pmi_entities,
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
        "lsa_coherence": summary.get("lsa_coherence", 0.0),
        "lsa_reliability": summary.get("lsa_reliability", 0.0),
        "cross_pmi_score": summary.get("cross_pmi_score", 0.0),
        "pmi_reliability": summary.get("pmi_reliability", 0.0),
        "blended_coherence": summary.get("blended_coherence", 0.0),
        "pmi_entities": summary.get("pmi_entities", []),
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
        try:
            from src.memory.analysis.graph_analysis import EntityGraph
            from src.memory.memory_db_path import resolve_memory_db_path
            graph = EntityGraph(resolve_memory_db_path())
        except Exception:
            graph = None

        keywords = summary["keywords"]
        if graph:
            by_comm = {}
            for kw in keywords:
                comm = graph.entity_community(kw)
                by_comm.setdefault(comm, []).append(kw)
            
            lines.append("- Keywords (Louvain Communities):")
            for comm_idx in sorted(by_comm.keys()):
                label = "General" if comm_idx == -1 else f"Categoría {comm_idx}"
                lines.append(f"  * **[{label}]**: {', '.join(by_comm[comm_idx])}")
        else:
            lines.append(f"- Keywords: {', '.join(keywords)}")
    # Show blended coherence if available
    blended = summary.get("blended_coherence", 0.0)
    lsa_r = summary.get("lsa_reliability", 0.0)
    pmi_r = summary.get("pmi_reliability", 0.0)
    if blended > 0:
        lines.append(f"- Blended coherence: **{blended:.3f}** (LSA rel={lsa_r:.2f}, PMI rel={pmi_r:.2f})")

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


def _build_scorer(root: str | Path | None = None) -> "CombinedScorer | None":
    """Initialise a CombinedScorer from project artifacts.

    Each component is initialised independently so a missing table or
    unavailable dependency degrades gracefully.  Returns None only when
    none of the components could be built at all.
    """
    if not ANALYSIS_AVAILABLE or CombinedScorer is None:
        return None

    base = Path(root) if root else _project_root()
    curated_db = resolve_memory_db_path()

    corpus: Optional["MemoryCorpus"] = None
    entity_graph: Optional["EntityGraph"] = None
    pmi: Optional["PMIClustering"] = None
    semantic: Optional["SemanticSimilarity"] = None

    try:
        corpus = MemoryCorpus(base)
    except Exception as exc:
        logger.debug("MemoryCorpus init failed: %s", exc)

    try:
        entity_graph = EntityGraph(curated_db)
    except Exception as exc:
        logger.debug("EntityGraph init failed: %s", exc)

    try:
        pmi = PMIClustering(base)
    except Exception as exc:
        logger.debug("PMIClustering init failed: %s", exc)

    try:
        semantic = SemanticSimilarity(curated_db)
    except Exception as exc:
        logger.debug("SemanticSimilarity init failed: %s", exc)

    # Return None only if nothing could be built
    if not any([corpus, entity_graph, pmi, semantic]):
        logger.warning("All scorer components failed — returning None")
        return None

    return CombinedScorer(
        corpus=corpus,
        entity_graph=entity_graph,
        pmi=pmi,
        semantic=semantic,
    )


async def generate_session_summaries(
    db_path: str,
    target_date: date | None = None,
    root: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Generate idempotent extractive summaries for sessions on a date.

    Computes global IDF + stemming from all session messages,
    then passes them to each build_session_summary call for
    IDF-weighted PMI (filters stopwords, preserves core concepts).
    """

    target = target_date or _default_target_date()
    date_str = target.isoformat()
    sessions = await get_sessions_for_summary_date(db_path, date_str)
    catalog = MemoryProcessingCatalogRepository(resolve_memory_db_path())

    # Build mathematical scorer (TF-IDF/BM25/graph/PMI) from existing artifacts
    scorer = _build_scorer(root=root)

    # ── Compute global IDF + stemming from ALL session messages ──
    from collections import defaultdict
    import math as _math
    from src.memory.analysis.pmi_relations import stem_spanish
    from src.memory.analysis.corpus import STOP
    from src.memory.analysis.pmi_relations import SPANISH_STOPWORDS

    # First pass: collect all messages and compute stem DF
    all_sessions_data: list[tuple[dict, list[dict]]] = []
    global_stem_df: dict[str, int] = defaultdict(int)
    
    for session in sessions:
        session_id = str(session.get("session_id") or "")
        if (
            session_id.startswith("test-")
            or session_id.startswith("test_")
            or "test" in session_id.lower()
        ):
            continue
        messages = await get_session_messages_for_summary(db_path, session_id)
        if len(messages) < 2:
            continue
        all_sessions_data.append((session, messages))
        
        # Compute stem DF for this session
        session_stems: set[str] = set()
        for msg in messages:
            content = str(msg.get("content", ""))
            for word in content.replace(","," ").replace("."," ").replace("?"," ").replace(":"," ").replace('"'," ").replace("'"," ").split():
                t = word.strip().lower()
                if t not in STOP and t not in SPANISH_STOPWORDS and len(t) > 2 and t.isalpha():
                    session_stems.add(stem_spanish(t))
        for s in session_stems:
            global_stem_df[s] += 1
    
    # Compute IDF and stem_map
    total_active = len(all_sessions_data)
    word_idf: dict[str, float] = {}
    if total_active > 0:
        word_idf = {w: _math.log((total_active + 1) / (d + 1)) + 1.0 
                     for w, d in global_stem_df.items()}
    max_idf = _math.log(total_active + 1) + 1.0 if total_active > 0 else 4.0
    
    # Build stem_map for all raw tokens seen
    stem_map: dict[str, str] = {}
    for _, messages in all_sessions_data:
        for msg in messages:
            content = str(msg.get("content", ""))
            for word in content.replace(","," ").replace("."," ").replace("?"," ").replace(":"," ").replace('"'," ").replace("'"," ").split():
                t = word.strip().lower()
                if t not in STOP and t not in SPANISH_STOPWORDS and len(t) > 2 and t.isalpha():
                    stem_map[t] = stem_spanish(t)

    # ── Process each session with IDF ──
    results: list[dict[str, Any]] = []
    for session, messages in all_sessions_data:
        session_id = str(session.get("session_id") or "")
        summary = build_session_summary(
            session, messages, scorer=scorer,
            word_idf=word_idf, max_idf=max_idf, stem_map=stem_map,
        )
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



