"""Daily synthesis report for the nightly curator.

Generates a Markdown report summarizing the day's sessions,
memory entries, entities, and clusters discovered.
"""

import aiosqlite
import json
import logging
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from src.memory.memory_db_path import resolve_memory_db_path

logger = logging.getLogger(__name__)


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent.parent


async def get_sessions_for_date(db_path: str, date_str: str) -> list[dict[str, Any]]:
    """Return sessions created on a given date (YYYY-MM-DD)."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT session_id, name, created_at FROM sessions "
            "WHERE date(created_at) = ? ORDER BY created_at",
            (date_str,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_session_stats(db_path: str, session_id: str) -> dict[str, Any]:
    """Return stats for a session.

    Returns dict with message_count, first_message_time, last_message_time, duration.
    """
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT COUNT(*) as message_count, "
            "MIN(created_at) as first_message_time, "
            "MAX(created_at) as last_message_time "
            "FROM messages WHERE session_id = ?",
            (session_id,),
        )
        row = await cursor.fetchone()
        result = dict(row) if row else {
            "message_count": 0,
            "first_message_time": "",
            "last_message_time": "",
        }
        if result["first_message_time"] and result["last_message_time"]:
            t1 = _parse_dt(result["first_message_time"])
            t2 = _parse_dt(result["last_message_time"])
            result["duration"] = str(t2 - t1) if t1 and t2 else ""
        else:
            result["duration"] = ""
        return result


def _parse_dt(s: str) -> datetime | None:
    fmt = "%Y-%m-%dT%H:%M:%S" if "T" in s else "%Y-%m-%d %H:%M:%S"
    try:
        return datetime.strptime(s[:19], fmt)
    except ValueError:
        return None


async def _get_new_embeddings_count(mem_db: str, date_str: str) -> int:
    async with aiosqlite.connect(mem_db) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM vec_meta WHERE date(created_at) = ?",
            (date_str,),
        )
        row = await cursor.fetchone()
        return row[0] if row else 0


async def _get_new_memory_entries(mem_db: str, date_str: str) -> list[dict[str, str]]:
    async with aiosqlite.connect(mem_db) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT key, value, created_at FROM memory_index "
            "WHERE date(created_at) = ? ORDER BY created_at",
            (date_str,),
        )
        return [dict(r) for r in await cursor.fetchall()]


async def _get_new_entities(mem_db: str, date_str: str) -> list[dict[str, Any]]:
    async with aiosqlite.connect(mem_db) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, name, entity_type, mention_count FROM entities "
            "WHERE date(first_seen) = ? ORDER BY mention_count DESC",
            (date_str,),
        )
        return [dict(r) for r in await cursor.fetchall()]


async def _get_new_clusters(mem_db: str, date_str: str) -> list[dict[str, Any]]:
    async with aiosqlite.connect(mem_db) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT cluster_id, label, keywords, session_count, exchange_count "
            "FROM topic_clusters WHERE date(first_seen) = ? "
            "ORDER BY exchange_count DESC",
            (date_str,),
        )
        results = []
        for r in await cursor.fetchall():
            d = dict(r)
            try:
                kws = json.loads(d["keywords"])
                d["keyword_words"] = [
                    k["word"] for k in kws
                    if isinstance(k, dict) and "word" in k
                ][:5]
            except (json.JSONDecodeError, TypeError):
                d["keyword_words"] = []
            results.append(d)
        return results


async def _get_session_topics(mem_db: str, session_id: str) -> list[str]:
    async with aiosqlite.connect(mem_db) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT DISTINCT tc.label FROM topic_clusters tc "
            "JOIN exchange_clusters ec ON ec.cluster_id = tc.cluster_id "
            "JOIN vec_meta vm ON vm.rowid = ec.exchange_rowid "
            "WHERE vm.source = 'session' AND vm.source_key = ? "
            "AND tc.weight > 0 ORDER BY tc.exchange_count DESC LIMIT 3",
            (session_id,),
        )
        return [r["label"] for r in await cursor.fetchall() if r["label"]]


async def generate_daily_synthesis(db_path: str, output_dir: str = "memory/synthesis") -> str:
    """Generate a daily synthesis Markdown report.

    Connects to sessions.db at *db_path*, resolves memory.db internally.
    Groups sessions by date and creates a report for the most recent day.

    Args:
        db_path: Path to sessions.db.
        output_dir: Output directory relative to project root.

    Returns:
        Absolute path to the created report file.
    """
    mem_db = resolve_memory_db_path()
    root = _project_root()
    abs_output_dir = os.path.join(root, output_dir)

    now = datetime.now()
    target_date = now.date()
    if now.hour < 4:
        target_date = (now - timedelta(days=1)).date()
    date_str = target_date.isoformat()

    logger.info("Generating daily synthesis for %s", date_str)

    sessions = await get_sessions_for_date(db_path, date_str)

    session_stats: list[dict[str, Any]] = []
    total_messages = 0
    for s in sessions:
        stats = await get_session_stats(db_path, s["session_id"])
        topics = await _get_session_topics(mem_db, s["session_id"])
        total_messages += stats["message_count"]
        session_stats.append({**s, **stats, "topics": topics})

    new_embeddings = await _get_new_embeddings_count(mem_db, date_str)
    memory_entries = await _get_new_memory_entries(mem_db, date_str)
    entities = await _get_new_entities(mem_db, date_str)
    clusters = await _get_new_clusters(mem_db, date_str)

    lines: list[str] = [
        f"# Daily Synthesis — {date_str}",
        "",
        "## Summary",
        "",
        f"- **Sessions**: {len(sessions)}",
        f"- **Messages**: {total_messages}",
        f"- **New embeddings**: {new_embeddings}",
        f"- **New entities**: {len(entities)}",
        f"- **New clusters**: {len(clusters)}",
        f"- **New memory entries**: {len(memory_entries)}",
        "",
    ]

    if session_stats:
        lines.append("## Sessions")
        lines.append("")
        for s in session_stats:
            name = s.get("name") or s["session_id"][:12]
            lines.append(f"### {name}")
            lines.append("")
            lines.append(f"- **ID**: `{s['session_id']}`")
            lines.append(f"- **Messages**: {s['message_count']}")
            if s.get("first_message_time"):
                lines.append(f"- **Start**: {s['first_message_time']}")
            if s.get("last_message_time"):
                lines.append(f"- **End**: {s['last_message_time']}")
            if s.get("duration"):
                lines.append(f"- **Duration**: {s['duration']}")
            if s.get("topics"):
                lines.append(f"- **Topics**: {', '.join(s['topics'])}")
            lines.append("")

    if memory_entries:
        lines.append("## New Memory Entries")
        lines.append("")
        for e in memory_entries:
            val = e["value"][:120]
            if len(e["value"]) > 120:
                val += "…"
            lines.append(f"- `{e['key']}`: {val}")
        lines.append("")

    if entities:
        lines.append("## New Entities")
        lines.append("")
        for e in entities:
            lines.append(
                f"- **{e['name']}** ({e['entity_type']}) — "
                f"{e['mention_count']} mentions"
            )
        lines.append("")

    if clusters:
        lines.append("## Topic Clusters")
        lines.append("")
        for c in clusters:
            kws = ", ".join(c.get("keyword_words", []))
            kw_suffix = f" — keywords: {kws}" if kws else ""
            lines.append(
                f"- **{c['label']}**: {c['exchange_count']} exchanges, "
                f"{c['session_count']} sessions{kw_suffix}"
            )
        lines.append("")

    y, m, d = date_str.split("-")
    report_path = os.path.join(abs_output_dir, y, m, f"{d}.md")
    os.makedirs(os.path.dirname(report_path), exist_ok=True)

    with open(report_path, "w") as f:
        f.write("\n".join(lines))

    logger.info("Daily synthesis saved to %s", report_path)
    return report_path
