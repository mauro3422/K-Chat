"""Curator: reads clusters + sessions, extracts candidate memory items.
Dry run: python3 -m src.memory.curator.curate --dry

Dependency injection: callers can inject save_memory_fn and llm_call_fn
to avoid upward coupling (memory → tools, memory → llm).
When run as standalone CLI, defaults are created via public APIs only.
"""

import asyncio
import json
import logging
import os
import sqlite3
import sys
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

from src.memory.content_hash import content_hash
from src.memory.repos_memory.processing_catalog_repo import MemoryProcessingCatalogRepository
from src.memory.operations._helpers import _get_memory_md_path

logger = logging.getLogger(__name__)

CURATOR_PROMPT = """You are a memory curator. From the conversation exchanges below,
extract NEW information worth saving. Only extract things NOT already known.

Format each item as:
KEY: <category:description>
VALUE: <YYYY-MM-DD HH:MM | text>

Categories: user:, bug:, decision:, proyecto:, patron:, checkpoint:
If nothing new, respond: NO_NEW_INFO"""


def _get_memory_context() -> str:
    """Read MEMORY.md and return first 3000 chars as context for LLM dedup."""
    memory_md_path = _get_memory_md_path()
    try:
        with open(memory_md_path) as f:
            content = f.read()
        return content[:3000]
    except FileNotFoundError:
        logger.warning("MEMORY.md not found at %s", memory_md_path)
        return ""
    except Exception:
        logger.exception("Failed to read MEMORY.md")
        return ""


# ── Dependency injection helpers ────────────────────────────────────

async def _default_llm_call(system: str, user: str) -> str:
    """Default LLM call using the public chat() API.

    Only called when no llm_call_fn is injected (standalone mode).
    """
    from src.llm.client import chat
    r = await chat(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.3,
        max_tokens=1024,
        stream=False,
    )
    if r is None:
        return ""
    if hasattr(r, "content") and r.content:
        return r.content
    if hasattr(r, "reasoning") and r.reasoning:
        return r.reasoning
    if isinstance(r, dict):
        return r.get("choices", [{}])[0].get("message", {}).get("content", "")
    return str(r)


async def _noop_save_memory(key: str, value: str) -> str:
    """No-op fallback when no save_memory_fn is injected."""
    logger.debug("save_memory not injected — would save: %s = %s", key, value[:80])
    return "[NOOP] save_memory_fn not injected"


async def _save_memory_inbox_local(key: str, value: str) -> str:
    """Standalone curator save helper that writes to memory inbox, not canon."""

    from src.memory.curator.memory_inbox import append_memory_inbox_item

    payload = append_memory_inbox_item(
        {
            "key": key.strip(),
            "value": value.strip(),
            "channel": "curator",
            "urgency": "normal",
        }
    )
    return f"[OK] queued memory inbox item '{payload['inbox_id']}' for key '{key.strip()}'."


def _get_memory_db_path() -> str:
    """Get memory.db path using the project's path resolver."""
    from src.memory.memory_db_path import resolve_memory_db_path
    return resolve_memory_db_path()


def _get_sessions_db_path() -> str:
    """Get sessions.db path using the project's path resolver."""
    from src.memory.db_path import resolve_db_path
    return resolve_db_path()


# ── Core logic ──────────────────────────────────────────────────────

def _get_processing_catalog() -> MemoryProcessingCatalogRepository | None:
    try:
        return MemoryProcessingCatalogRepository(_get_memory_db_path())
    except Exception:
        logger.debug("memory_processing_catalog unavailable", exc_info=True)
        return None


def _mark_processing_catalog(
    catalog: MemoryProcessingCatalogRepository | None,
    *,
    source: str,
    source_key: str,
    item_idx: int,
    stage: str,
    content_hash: str,
    status: str = "processed",
    processor: str = "",
    reason: str = "",
    metadata: dict[str, Any] | None = None,
) -> None:
    if catalog is None:
        return
    try:
        catalog.mark(
            source=source,
            source_key=source_key,
            item_idx=item_idx,
            stage=stage,
            content_hash=content_hash,
            status=status,
            processor=processor,
            reason=reason,
            metadata=metadata,
        )
    except Exception:
        logger.debug("Failed to mark memory processing catalog", exc_info=True)


def parse_resp(text: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    key = None
    for line in text.strip().split("\n"):
        if line.startswith("KEY:"):
            key = line[4:].strip()
        elif line.startswith("VALUE:") and key:
            entries.append({"key": key, "value": line[6:].strip()})
            key = None
    return entries


async def curate_clusters(
    dry: bool = False,
    llm_call_fn: Optional[Callable[[str, str], str]] = None,
) -> list[dict[str, str]]:
    """Read top topic clusters and ask LLM to extract new info.

    Args:
        dry: If True, don't call LLM, just report what would be processed.
        llm_call_fn: Injected LLM function (system, user) → response.
                     Falls back to _default_llm_call if None.
    """
    if llm_call_fn is None:
        llm_call_fn = _default_llm_call

    db_path = _get_memory_db_path()
    catalog = None if dry else _get_processing_catalog()
    conn = sqlite3.connect(db_path)
    clusters = conn.execute(
        "SELECT cluster_id, label, exchange_count FROM topic_clusters "
        "WHERE exchange_count >= 2 ORDER BY exchange_count DESC LIMIT 5"
    ).fetchall()
    conn.close()

    entries = []
    for cid, label, _ in clusters:
        conn = sqlite3.connect(db_path)
        try:
            texts = conn.execute(
                "SELECT m.text FROM exchange_clusters ec "
                "JOIN vec_meta m ON m.rowid = ec.exchange_rowid "
                "WHERE ec.cluster_id = ? ORDER BY ec.similarity DESC LIMIT 3",
                (cid,),
            ).fetchall()
        except Exception:
            texts = []

        if not texts:
            kw = conn.execute(
                "SELECT keywords FROM topic_clusters WHERE cluster_id = ?",
                (cid,),
            ).fetchone()
            if kw and kw[0]:
                words = [k["word"] for k in json.loads(kw[0])[:3]]
                p = "%" + "%".join(words) + "%"
                try:
                    texts = conn.execute(
                        "SELECT text FROM vec_meta WHERE source='session' "
                        "AND metadata LIKE ? AND length(text) > 30 LIMIT 3",
                        (p,),
                    ).fetchall()
                except Exception:
                    texts = []
        conn.close()

        texts = [t[0] for t in texts if t[0] and len(t[0]) > 30]
        if not texts:
            continue
        if dry:
            continue

        prompt = (
            f"Cluster: {label}\n\n"
            + "\n---\n".join(t[:400] for t in texts)
            + "\n\nExtract new info or NO_NEW_INFO"
        )
        digest = content_hash(prompt)
        if catalog and catalog.is_processed(
            source="cluster",
            source_key=str(cid),
            item_idx=-1,
            stage="curated",
            content_hash=digest,
        ):
            logger.info("Skipping unchanged curated cluster %s", cid)
            continue

        # Pre-mark as "processing" to claim the work atomically and prevent
        # duplicate LLM calls from concurrent curators (TOCTOU fix).
        _mark_processing_catalog(
            catalog,
            source="cluster",
            source_key=str(cid),
            item_idx=-1,
            stage="curated",
            content_hash=digest,
            status="processing",
            processor="curate_clusters",
            reason="claimed",
            metadata={"texts": len(texts), "label": str(label)},
        )

        context = _get_memory_context()
        system_prompt = f"EXISTING MEMORIES:\n{context}\n\n{CURATOR_PROMPT}" if context else CURATOR_PROMPT
        try:
            resp = await llm_call_fn(system_prompt, prompt)
            parsed = [] if "NO_NEW_INFO" in resp else parse_resp(resp)
            _mark_processing_catalog(
                catalog,
                source="cluster",
                source_key=str(cid),
                item_idx=-1,
                stage="curated",
                content_hash=digest,
                processor="curate_clusters",
                reason="no_new_info" if not parsed else "entries_extracted",
                metadata={"entries": len(parsed), "texts": len(texts), "label": str(label)},
            )
            entries.extend(parsed)
        except Exception:
            logger.exception("LLM call failed for cluster %s", label)
            _mark_processing_catalog(
                catalog,
                source="cluster",
                source_key=str(cid),
                item_idx=-1,
                stage="curated",
                content_hash=digest,
                status="failed",
                processor="curate_clusters",
                reason="llm_call_failed",
                metadata={"texts": len(texts), "label": str(label)},
            )

    return entries


async def curate_sessions(
    days: int = 1,
    dry: bool = False,
    llm_call_fn: Optional[Callable[[str, str], str]] = None,
) -> list[dict[str, str]]:
    """Read recent vectorized sessions and ask LLM to extract new info.

    Args:
        days: How many days back to look for sessions.
        dry: If True, don't call LLM.
        llm_call_fn: Injected LLM function. Falls back to _default_llm_call.
    """
    if llm_call_fn is None:
        llm_call_fn = _default_llm_call

    sessions_db = _get_sessions_db_path()
    mem_db = _get_memory_db_path()
    catalog = None if dry else _get_processing_catalog()

    conn = sqlite3.connect(sessions_db)
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    sessions = conn.execute(
        "SELECT session_id, name FROM sessions "
        "WHERE created_at >= ? ORDER BY created_at DESC LIMIT 3",
        (cutoff,),
    ).fetchall()
    conn.close()

    entries = []
    for sid, name in sessions:
        conn = sqlite3.connect(mem_db)
        texts = conn.execute(
            "SELECT text FROM vec_meta WHERE source='session' "
            "AND source_key = ? AND length(text) > 30 "
            "ORDER BY exchange_idx DESC LIMIT 8",
            (sid,),
        ).fetchall()
        conn.close()

        texts = [t[0] for t in texts if t[0]]
        if not texts:
            continue
        if dry:
            continue

        prompt_body = "\n---\n".join(t[:400] for t in texts)
        prompt = (
            f"Session: {name or sid[:12]}\n\n"
            + prompt_body
            + "\n\nExtract new info or NO_NEW_INFO"
        )
        digest = content_hash(prompt)
        if catalog and catalog.is_processed(
            source="session",
            source_key=sid,
            item_idx=-1,
            stage="curated",
            content_hash=digest,
        ):
            logger.info("Skipping unchanged curated session %s", sid)
            continue

        # Pre-mark as "processing" to claim the work atomically and prevent
        # duplicate LLM calls from concurrent curators (TOCTOU fix).
        _mark_processing_catalog(
            catalog,
            source="session",
            source_key=sid,
            item_idx=-1,
            stage="curated",
            content_hash=digest,
            status="processing",
            processor="curate_sessions",
            reason="claimed",
            metadata={"texts": len(texts)},
        )

        context = _get_memory_context()
        system_prompt = f"EXISTING MEMORIES:\n{context}\n\n{CURATOR_PROMPT}" if context else CURATOR_PROMPT
        try:
            resp = await llm_call_fn(system_prompt, prompt)
            parsed = [] if "NO_NEW_INFO" in resp else parse_resp(resp)
            if catalog:
                catalog.mark(
                    source="session",
                    source_key=sid,
                    item_idx=-1,
                    stage="curated",
                    content_hash=digest,
                    status="processed",
                    processor="curate_sessions",
                    reason="no_new_info" if not parsed else "entries_extracted",
                    metadata={"entries": len(parsed), "texts": len(texts)},
                )
            entries.extend(parsed)
        except Exception:
            logger.exception("LLM call failed for session %s", sid)
            if catalog:
                catalog.mark(
                    source="session",
                    source_key=sid,
                    item_idx=-1,
                    stage="curated",
                    content_hash=digest,
                    status="failed",
                    processor="curate_sessions",
                    reason="llm_call_failed",
                    metadata={"texts": len(texts)},
                )

    return entries


def _retire_old_sessions(max_age_days: int, dry: bool = False) -> int:
    """Delete sessions older than max_age_days from sessions.db.

    Moves session metadata to deleted_sessions.db before deleting.
    Also cleans up orphan vectors from memory.db.
    Returns count of retired sessions.
    """
    try:
        sessions_db = _get_sessions_db_path()
        deleted_db = os.path.join(os.path.dirname(sessions_db), "deleted_sessions.db")

        if not os.path.exists(deleted_db):
            logger.warning("deleted_sessions.db not found at %s, skipping retention", deleted_db)
            return 0

        conn = sqlite3.connect(sessions_db)
        cutoff = (datetime.now() - timedelta(days=max_age_days)).isoformat()

        old = conn.execute(
            "SELECT session_id, name FROM sessions WHERE created_at < ?",
            (cutoff,),
        ).fetchall()

        if not old:
            conn.close()
            return 0

        del_conn = sqlite3.connect(deleted_db)
        now = datetime.now().isoformat()

        for sid, name in old:
            msg_count = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE session_id = ?", (sid,)
            ).fetchone()[0]
            if not dry:
                try:
                    # Insert into deleted_sessions first, then delete from sessions.
                    # If DELETE fails (e.g., FK constraint), the INSERT is harmless
                    # because it uses OR IGNORE. Each pair commits independently
                    # so a failure on one session doesn't block the rest.
                    del_conn.execute(
                        "INSERT OR IGNORE INTO deleted_sessions (session_id, name, message_count, deleted_at) VALUES (?, ?, ?, ?)",
                        (sid, name, msg_count, now),
                    )
                    del_conn.commit()
                    conn.execute("DELETE FROM sessions WHERE session_id = ?", (sid,))
                    conn.commit()
                except Exception:
                    logger.warning("Failed to retire session %s, skipping", sid, exc_info=True)
                    conn.rollback()

        del_conn.close()
        conn.close()

        # Clean up orphan vectors from memory.db for retired sessions
        if not dry and old:
            try:
                mem_db = _get_memory_db_path()
                mem_conn = sqlite3.connect(mem_db)
                cleaned = 0
                for sid, _ in old:
                    rows = mem_conn.execute(
                        "SELECT rowid FROM vec_meta WHERE source='session' AND source_key = ?",
                        (sid,),
                    ).fetchall()
                    for (rowid,) in rows:
                        mem_conn.execute("DELETE FROM vec_entries WHERE rowid = ?", (rowid,))
                        cleaned += 1
                    mem_conn.execute(
                        "DELETE FROM vec_meta WHERE source='session' AND source_key = ?",
                        (sid,),
                    )
                mem_conn.commit()
                mem_conn.close()
                if cleaned:
                    logger.info("Cleaned %d vectors from memory.db for %d retired sessions",
                                cleaned, len(old))
            except Exception:
                logger.exception("Failed to clean up session vectors from memory.db")

        logger.info("Retired %d old sessions (age > %d days)", len(old), max_age_days)
        return len(old)
    except Exception:
        logger.exception("Failed to retire old sessions")
        return 0


async def curate_all(
    dry: bool = False,
    save_memory_fn: Optional[Callable[[str, str], str]] = None,
    llm_call_fn: Optional[Callable[[str, str], str]] = None,
    run_gardener: bool = True,
    run_tracer: bool = True,
    artifact_root: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """Run full curation pipeline: Retention → Gardener → Tracer → Curator.

    Steps:
      1. Session retention — retire sessions older than max_age_days
      2. Memory Gardener — prune/merge/cleanup low-value entries
      3. Cross-Session Tracer — detect patterns between sessions
      4. Curator (clusters + sessions) — LLM extraction of new info
      5. Report - write curation summary artifact

    Args:
        dry: If True, don't call LLM or save, just report what would happen.
        save_memory_fn: Injected save function (key, value) → result string.
        llm_call_fn: Injected LLM function.
        run_gardener: Whether to run the Memory Gardener step.
        run_tracer: Whether to run the Cross-Session Tracer step.

    Returns:
        dict with all results.
    """
    if save_memory_fn is None:
        save_memory_fn = _save_memory_inbox_local
    if llm_call_fn is None:
        llm_call_fn = _default_llm_call

    from src.memory.curator.gardener import garden
    from src.memory.curator.tracer import trace
    from datetime import datetime

    report_lines = [
        f"## Curation Report — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
    ]

    # Step 0: Vectorize new sessions (incremental)
    if not dry:
        try:
            from src.memory.vectorize_sessions import vectorize_all_sessions
            from src.memory.repos import get_repos
            repos = get_repos()
            vec_results = await vectorize_all_sessions(repos=repos)
            total_vec = sum(vec_results.values())
            if total_vec > 0:
                report_lines.append(f"- vectorized: {total_vec} new exchanges across {len(vec_results)} sessions")
                report_lines.append("")
        except Exception:
            logger.exception("Session vectorization step failed")

    # Step 1: Session retention
    # Step 1: Gardener
    gardener_results = []
    if run_gardener:
        gardener_results = garden({"dry_run": dry})
        for r in gardener_results:
            report_lines.append(f"- gardener/{r['action']}: {r}")
        report_lines.append("")

    # Step 2: Tracer
    tracer_result: dict[str, Any] = {"patterns": [], "total": 0}
    if run_tracer:
        tracer_result = await trace(
            {"dry_run": dry, "artifact_root": artifact_root},
            save_memory_fn=None,
        )
        report_lines.append(f"- tracer: {tracer_result['total']} patterns found")
        for p in tracer_result.get("patterns", []):
            report_lines.append(f"  - [{p['type']}] {p}")
        report_lines.append("")

    # Step 3: Existing curator
    entries: list[dict[str, str]] = []
    entries.extend(await curate_clusters(dry=dry, llm_call_fn=llm_call_fn))
    entries.extend(await curate_sessions(days=1, dry=dry, llm_call_fn=llm_call_fn))

    if entries:
        report_lines.append(f"- curator: {len(entries)} new entries extracted")

    saved = 0
    if not dry and entries:
        for e in entries:
            try:
                r = await save_memory_fn(e["key"], e["value"])
                if "[OK]" in r:
                    saved += 1
            except Exception:
                logger.exception("Failed to save: %s", e.get("key"))
        report_lines.append(f"- curator: {saved}/{len(entries)} queued to memory inbox")

    # Step 4: Write report artifact and processing checkpoint
    report_path = None
    if not dry:
        report_text = "\n".join(report_lines)
        catalog = _get_processing_catalog()
        report_digest = content_hash("\n".join(report_lines[2:]) or report_text)
        report_metadata = {
            "entries": len(entries),
            "saved": saved,
            "gardener_actions": len(gardener_results),
            "tracer_patterns": int(tracer_result.get("total", 0)),
        }
        _mark_processing_catalog(
            catalog,
            source="curator",
            source_key=datetime.now().strftime("%Y-%m-%d"),
            item_idx=-1,
            stage="run",
            content_hash=report_digest,
            processor="curate_all",
            reason="completed",
            metadata=report_metadata,
        )
        try:
            from src.memory.curator.curation_events import write_curation_report

            report_path = write_curation_report(
                report_lines,
                report_metadata,
                root=artifact_root,
            )
            logger.info("Curation report artifact -> %s", report_path)
        except Exception:
            logger.exception("Failed to write curation report artifact")

    # Step 5: Daily synthesis report
    synthesis_path = None
    if not dry:
        try:
            from src.memory.synthesis.daily import generate_daily_synthesis
            sessions_db = _get_sessions_db_path()
            synthesis_path = await generate_daily_synthesis(db_path=sessions_db)
            logger.info("Daily synthesis -> %s", synthesis_path)
        except Exception:
            logger.exception("Failed to generate daily synthesis")

    return {
        "gardener": gardener_results,
        "tracer": tracer_result,
        "entries": entries,
        "saved": saved,
        "report": report_lines,
        "report_path": str(report_path) if report_path else None,
        "synthesis_path": synthesis_path,
        "dry": dry,
    }


# ── Standalone CLI entry point ──────────────────────────────────────

async def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    dry = "--dry" in sys.argv
    r = await curate_all(dry=dry)

    print("\n=== Gardener ===")
    for gr in r.get("gardener", []):
        print(f"  {gr['action']}: {gr}")

    print("\n=== Tracer ===")
    tr = r.get("tracer", {})
    print(f"  {tr.get('total', 0)} patterns")
    for p in tr.get("patterns", []):
        print(f"  [{p['type']}] {p}")

    print("\n=== Curator ===")
    for e in r["entries"]:
        print(f"  [{e['key']}] {e['value'][:80]}")
    print(f"Saved: {r['saved']}")

    print(f"\nDry run: {r.get('dry', False)}")


if __name__ == "__main__":
    asyncio.run(main())
