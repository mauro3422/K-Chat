"""Read-only audit for Kairos memory and embedding state.

The audit intentionally does not import app internals beyond path resolvers.
It can be run while Kairos is up because it only opens SQLite read connections.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@dataclass
class SessionAudit:
    session_id: str
    name: str = ""
    message_count: int = 0
    exchange_count: int = 0
    vector_count: int = 0
    missing_hashes: list[str] = field(default_factory=list)
    stale_vectors: list[dict[str, Any]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.missing_hashes and not self.stale_vectors


def _connect_readonly(path: str) -> sqlite3.Connection:
    uri = Path(path).resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _count(conn: sqlite3.Connection, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return int(conn.execute(f"SELECT COUNT(1) FROM {table}").fetchone()[0])


def _normalize_for_dedup(text: str) -> str:
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    text = re.sub(r"`[^`]+`", "", text)
    text = text.lower().strip()
    return re.sub(r"\s+", " ", text)


def _content_hash(text: str, *, limit: int = 4000) -> str:
    return hashlib.md5(_normalize_for_dedup(text[:limit]).encode("utf-8")).hexdigest()


def _group_into_exchanges(messages: list[sqlite3.Row]) -> list[dict[str, Any]]:
    exchanges: list[dict[str, Any]] = []
    current_user: dict[str, Any] | None = None

    for msg in messages:
        role = str(msg["role"] or "")
        content = str(msg["content"] or "").strip()
        if not content:
            continue
        if role == "user":
            current_user = {
                "user_text": content,
                "created_at": msg["created_at"] if "created_at" in msg.keys() else "",
            }
        elif role == "assistant" and current_user is not None:
            exchanges.append({
                "idx": len(exchanges),
                "text": f"User: {current_user['user_text']}\nAssistant: {content}",
                "created_at": current_user.get("created_at", ""),
            })
            current_user = None

    if current_user is not None:
        exchanges.append({
            "idx": len(exchanges),
            "text": f"User: {current_user['user_text']}\nAssistant: _pending_",
            "created_at": current_user.get("created_at", ""),
        })

    return exchanges


def _duplicate_groups(conn: sqlite3.Connection, column: str) -> int:
    if not _table_exists(conn, "vec_meta"):
        return 0
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(vec_meta)").fetchall()}
    if column not in cols:
        return 0
    row = conn.execute(
        f"""
        SELECT COUNT(1)
        FROM (
            SELECT {column}
            FROM vec_meta
            WHERE {column} IS NOT NULL AND {column} != ''
            GROUP BY {column}
            HAVING COUNT(1) > 1
        )
        """
    ).fetchone()
    return int(row[0] if row else 0)


def _source_counts(conn: sqlite3.Connection) -> dict[str, int]:
    if not _table_exists(conn, "vec_meta"):
        return {}
    return {
        str(row["source"]): int(row["count"])
        for row in conn.execute("SELECT source, COUNT(1) AS count FROM vec_meta GROUP BY source")
    }


def _catalog_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    if not _table_exists(conn, "memory_work_catalog"):
        return {
            "exists": False,
            "total": 0,
            "by_status": {},
            "pending": 0,
            "missing_vec_links": 0,
        }
    by_status = {
        str(row["status"]): int(row["count"])
        for row in conn.execute(
            "SELECT status, COUNT(1) AS count FROM memory_work_catalog GROUP BY status"
        ).fetchall()
    }
    missing_vec_links = conn.execute(
        """
        SELECT COUNT(1)
        FROM memory_work_catalog c
        LEFT JOIN vec_meta m ON m.rowid = c.vec_rowid
        WHERE c.status IN ('embedded', 'deduped')
          AND c.vec_rowid IS NOT NULL
          AND m.rowid IS NULL
        """
    ).fetchone()[0]
    return {
        "exists": True,
        "total": _count(conn, "memory_work_catalog"),
        "by_status": by_status,
        "pending": by_status.get("pending", 0),
        "missing_vec_links": int(missing_vec_links or 0),
    }


def _curated_memory_quality(conn: sqlite3.Connection) -> dict[str, Any]:
    if not _table_exists(conn, "memory_index"):
        return {
            "exists": False,
            "total": 0,
            "empty": 0,
            "too_short": 0,
            "missing_timestamp": 0,
            "duplicate_value_groups": 0,
            "samples": [],
        }

    rows = conn.execute(
        """
        SELECT key, value
        FROM memory_index
        ORDER BY updated_at DESC
        """
    ).fetchall()
    empty: list[str] = []
    too_short: list[str] = []
    missing_timestamp: list[str] = []
    by_value: dict[str, list[str]] = {}

    for row in rows:
        key = str(row["key"])
        value = str(row["value"] or "").strip()
        if not value:
            empty.append(key)
            continue
        if len(value) < 20:
            too_short.append(key)
        if not re.match(r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}\s+\|", value):
            missing_timestamp.append(key)
        normalized = re.sub(r"\s+", " ", value.lower())
        by_value.setdefault(normalized, []).append(key)

    duplicate_groups = [keys for keys in by_value.values() if len(keys) > 1]
    samples: list[dict[str, Any]] = []
    for kind, keys in [
        ("empty", empty),
        ("too_short", too_short),
        ("missing_timestamp", missing_timestamp),
    ]:
        samples.extend({"kind": kind, "key": key} for key in keys[:8])
    for keys in duplicate_groups[:8]:
        samples.append({"kind": "duplicate_value", "keys": keys[:6]})

    return {
        "exists": True,
        "total": len(rows),
        "empty": len(empty),
        "too_short": len(too_short),
        "missing_timestamp": len(missing_timestamp),
        "duplicate_value_groups": len(duplicate_groups),
        "samples": samples[:30],
    }


def _processing_catalog_summary(
    sessions_conn: sqlite3.Connection,
    memory_conn: sqlite3.Connection,
    *,
    root: str,
) -> dict[str, Any]:
    if not _table_exists(memory_conn, "memory_processing_catalog"):
        return {
            "exists": False,
            "total": 0,
            "by_stage_status": {},
            "pending": 0,
            "failed": 0,
            "stale": 0,
            "stale_rows": [],
        }

    rows = memory_conn.execute(
        """
        SELECT source, source_key, item_idx, stage, content_hash, status,
               processor, reason, updated_at
        FROM memory_processing_catalog
        ORDER BY updated_at DESC
        """
    ).fetchall()
    by_stage_status: dict[str, dict[str, int]] = {}
    pending = 0
    failed = 0
    stale_rows: list[dict[str, Any]] = []
    for row in rows:
        stage = str(row["stage"])
        status = str(row["status"])
        by_stage_status.setdefault(stage, {})
        by_stage_status[stage][status] = by_stage_status[stage].get(status, 0) + 1
        if status == "pending":
            pending += 1
        if status == "failed":
            failed += 1

        expected_hash = _expected_processing_hash(
            sessions_conn,
            memory_conn,
            root=root,
            source=str(row["source"]),
            source_key=str(row["source_key"]),
            stage=stage,
        )
        row_hash = str(row["content_hash"] or "")
        if expected_hash and row_hash and expected_hash != row_hash:
            stale_rows.append({
                "source": str(row["source"]),
                "source_key": str(row["source_key"]),
                "item_idx": int(row["item_idx"]),
                "stage": stage,
                "status": status,
                "hash": row_hash[:12],
                "expected_hash": expected_hash[:12],
                "updated_at": str(row["updated_at"]),
            })

    return {
        "exists": True,
        "total": len(rows),
        "by_stage_status": by_stage_status,
        "pending": pending,
        "failed": failed,
        "stale": len(stale_rows),
        "stale_rows": stale_rows[:50],
    }


def _expected_processing_hash(
    sessions_conn: sqlite3.Connection,
    memory_conn: sqlite3.Connection,
    *,
    root: str,
    source: str,
    source_key: str,
    stage: str,
) -> str:
    if source == "session" and stage == "curated":
        return _expected_curated_session_hash(sessions_conn, memory_conn, source_key)
    if source == "daily_synthesis" and stage == "generated":
        return _expected_daily_synthesis_hash(root, source_key)
    return ""


def _expected_curated_session_hash(
    sessions_conn: sqlite3.Connection,
    memory_conn: sqlite3.Connection,
    session_id: str,
) -> str:
    if not _table_exists(sessions_conn, "sessions") or not _table_exists(memory_conn, "vec_meta"):
        return ""
    session = sessions_conn.execute(
        "SELECT name FROM sessions WHERE session_id=?",
        (session_id,),
    ).fetchone()
    if session is None:
        return ""
    texts = memory_conn.execute(
        """
        SELECT text
        FROM vec_meta
        WHERE source='session'
          AND source_key=?
          AND length(text) > 30
        ORDER BY exchange_idx DESC
        LIMIT 8
        """,
        (session_id,),
    ).fetchall()
    text_values = [str(row["text"]) for row in texts if str(row["text"] or "")]
    if not text_values:
        return ""
    prompt = (
        f"Session: {str(session['name'] or '') or session_id[:12]}\n\n"
        + "\n---\n".join(text[:400] for text in text_values)
        + "\n\nExtract new info or NO_NEW_INFO"
    )
    return _content_hash(prompt)


def _expected_daily_synthesis_hash(root: str, date_str: str) -> str:
    parts = date_str.split("-")
    if len(parts) != 3:
        return ""
    y, m, d = parts
    report_path = Path(root) / "memory" / "synthesis" / y / m / f"{d}.md"
    if not report_path.exists():
        return ""
    return _content_hash(report_path.read_text(encoding="utf-8", errors="replace"), limit=100000)


def _audit_sessions(sessions_conn: sqlite3.Connection, memory_conn: sqlite3.Connection) -> tuple[list[SessionAudit], list[dict[str, Any]]]:
    if not _table_exists(sessions_conn, "sessions") or not _table_exists(sessions_conn, "messages"):
        return [], []

    sessions = sessions_conn.execute(
        "SELECT session_id, name FROM sessions ORDER BY created_at DESC"
    ).fetchall()
    session_ids = {str(row["session_id"]) for row in sessions}
    audits: list[SessionAudit] = []

    has_vec_meta = _table_exists(memory_conn, "vec_meta")
    has_catalog = _table_exists(memory_conn, "memory_work_catalog")
    for session in sessions:
        session_id = str(session["session_id"])
        messages = sessions_conn.execute(
            "SELECT role, content, created_at FROM messages WHERE session_id=? ORDER BY id ASC",
            (session_id,),
        ).fetchall()
        exchanges = _group_into_exchanges(messages)
        current_hashes = {
            exchange["idx"]: _content_hash(str(exchange["text"]))
            for exchange in exchanges
            if len(str(exchange["text"])) >= 30
        }

        vector_rows: list[sqlite3.Row] = []
        if has_vec_meta:
            vector_rows = memory_conn.execute(
                """
                SELECT rowid, exchange_idx, hash, content_hash, created_at
                FROM vec_meta
                WHERE source='session' AND source_key=?
                ORDER BY exchange_idx ASC
                """,
                (session_id,),
            ).fetchall()

        vector_hashes = {
            str(row["content_hash"] or row["hash"] or "")
            for row in vector_rows
            if str(row["content_hash"] or row["hash"] or "")
        }
        covered_hashes = set(vector_hashes)
        if has_catalog:
            catalog_rows = memory_conn.execute(
                """
                SELECT item_idx, content_hash, status
                FROM memory_work_catalog
                WHERE source='session' AND source_key=?
                  AND status IN ('embedded', 'deduped', 'noise')
                """,
                (session_id,),
            ).fetchall()
            covered_hashes.update(
                str(row["content_hash"])
                for row in catalog_rows
                if str(row["content_hash"] or "")
            )
        missing = [
            f"{idx}:{digest[:12]}"
            for idx, digest in current_hashes.items()
            if digest not in covered_hashes
        ]
        stale = []
        current_digest_set = set(current_hashes.values())
        for row in vector_rows:
            digest = str(row["content_hash"] or row["hash"] or "")
            if digest and digest not in current_digest_set:
                stale.append({
                    "rowid": row["rowid"],
                    "exchange_idx": row["exchange_idx"],
                    "hash": digest[:12],
                    "created_at": row["created_at"],
                })

        audits.append(SessionAudit(
            session_id=session_id,
            name=str(session["name"] or ""),
            message_count=len(messages),
            exchange_count=len(exchanges),
            vector_count=len(vector_rows),
            missing_hashes=missing,
            stale_vectors=stale,
        ))

    orphan_vectors: list[dict[str, Any]] = []
    if has_vec_meta:
        rows = memory_conn.execute(
            """
            SELECT source_key, COUNT(1) AS count, MAX(exchange_idx) AS max_exchange_idx
            FROM vec_meta
            WHERE source='session'
            GROUP BY source_key
            """
        ).fetchall()
        for row in rows:
            source_key = str(row["source_key"])
            if source_key not in session_ids:
                orphan_vectors.append({
                    "source_key": source_key,
                    "count": int(row["count"]),
                    "max_exchange_idx": row["max_exchange_idx"],
                })

    return audits, orphan_vectors


def _latest_synthesis(root: str) -> dict[str, Any]:
    base = Path(root) / "memory" / "synthesis"
    if not base.exists():
        return {"exists": False, "latest": "", "count": 0}
    files = sorted(base.rglob("*.md"), key=lambda path: path.stat().st_mtime, reverse=True)
    return {
        "exists": True,
        "latest": str(files[0]) if files else "",
        "count": len(files),
    }


def run_audit(*, sessions_db: str, memory_db: str, root: str) -> dict[str, Any]:
    with closing(_connect_readonly(sessions_db)) as sessions_conn, closing(_connect_readonly(memory_db)) as memory_conn:
        session_audits, orphan_vectors = _audit_sessions(sessions_conn, memory_conn)
        stale_sessions = [audit for audit in session_audits if audit.stale_vectors]
        missing_sessions = [audit for audit in session_audits if audit.missing_hashes]

        checkpoints: list[dict[str, str]] = []
        if _table_exists(memory_conn, "memory_index"):
            checkpoints = [
                {"key": str(row["key"]), "updated_at": str(row["updated_at"])}
                for row in memory_conn.execute(
                    """
                    SELECT key, updated_at
                    FROM memory_index
                    WHERE key LIKE 'checkpoint:curation-%' OR key LIKE 'synthesis:%'
                    ORDER BY updated_at DESC
                    LIMIT 12
                    """
                ).fetchall()
            ]

        legacy_vector_tables = _table_exists(sessions_conn, "vec_meta")
        legacy_vector_count = _count(sessions_conn, "vec_meta") if legacy_vector_tables else 0
        processing_catalog = _processing_catalog_summary(sessions_conn, memory_conn, root=root)
        curated_quality = _curated_memory_quality(memory_conn)

        return {
            "ok": not stale_sessions
            and not orphan_vectors
            and processing_catalog["failed"] == 0
            and processing_catalog["stale"] == 0
            and curated_quality["empty"] == 0,
            "paths": {"sessions_db": sessions_db, "memory_db": memory_db},
            "counts": {
                "sessions": _count(sessions_conn, "sessions"),
                "messages": _count(sessions_conn, "messages"),
                "memory_index": _count(memory_conn, "memory_index"),
                "memory_vec_meta": _count(memory_conn, "vec_meta"),
                "legacy_session_vec_meta": legacy_vector_count,
            },
            "catalog": _catalog_summary(memory_conn),
            "processing_catalog": processing_catalog,
            "curated_memory_quality": curated_quality,
            "vector_sources": _source_counts(memory_conn),
            "duplicates": {
                "hash_groups": _duplicate_groups(memory_conn, "hash"),
                "content_hash_groups": _duplicate_groups(memory_conn, "content_hash"),
            },
            "sessions": [audit.__dict__ for audit in session_audits],
            "summary": {
                "sessions_with_missing_vectors": len(missing_sessions),
                "sessions_with_stale_vectors": len(stale_sessions),
                "orphan_vector_sources": len(orphan_vectors),
                "processing_failed": processing_catalog["failed"],
                "processing_stale": processing_catalog["stale"],
                "curated_empty": curated_quality["empty"],
                "curated_too_short": curated_quality["too_short"],
                "curated_missing_timestamp": curated_quality["missing_timestamp"],
                "curated_duplicate_value_groups": curated_quality["duplicate_value_groups"],
            },
            "orphan_vectors": orphan_vectors,
            "synthesis": _latest_synthesis(root),
            "checkpoints": checkpoints,
            "legacy": {
                "sessions_db_has_vec_meta": legacy_vector_tables,
                "sessions_db_vec_meta_count": legacy_vector_count,
            },
        }


def print_text_report(report: dict[str, Any]) -> None:
    counts = report["counts"]
    summary = report["summary"]
    print("Kairos memory audit")
    print(f"sessions={counts['sessions']} messages={counts['messages']} memory_entries={counts['memory_index']}")
    print(f"vectors={counts['memory_vec_meta']} sources={json.dumps(report['vector_sources'], sort_keys=True)}")
    catalog = report["catalog"]
    if catalog["exists"]:
        print(
            "catalog: "
            f"units={catalog['total']} statuses={json.dumps(catalog['by_status'], sort_keys=True)} "
            f"pending={catalog['pending']} missing_vec_links={catalog['missing_vec_links']}"
        )
    processing = report["processing_catalog"]
    if processing["exists"]:
        print(
            "processing: "
            f"units={processing['total']} stages={json.dumps(processing['by_stage_status'], sort_keys=True)} "
            f"pending={processing['pending']} failed={processing['failed']} stale={processing['stale']}"
        )
    quality = report["curated_memory_quality"]
    if quality["exists"]:
        print(
            "curated_quality: "
            f"empty={quality['empty']} too_short={quality['too_short']} "
            f"missing_timestamp={quality['missing_timestamp']} "
            f"duplicate_value_groups={quality['duplicate_value_groups']}"
        )
    print(
        "issues: "
        f"missing_sessions={summary['sessions_with_missing_vectors']} "
        f"stale_sessions={summary['sessions_with_stale_vectors']} "
        f"orphan_sources={summary['orphan_vector_sources']} "
        f"dup_hash_groups={report['duplicates']['hash_groups']} "
        f"dup_content_hash_groups={report['duplicates']['content_hash_groups']} "
        f"processing_failed={summary['processing_failed']} "
        f"processing_stale={summary['processing_stale']} "
        f"curated_empty={summary['curated_empty']}"
    )
    if report["legacy"]["sessions_db_has_vec_meta"]:
        print(f"legacy: sessions.db has vec_meta with {report['legacy']['sessions_db_vec_meta_count']} rows")

    synthesis = report["synthesis"]
    print(f"synthesis: exists={synthesis['exists']} count={synthesis['count']} latest={synthesis['latest'] or '-'}")

    printed = False
    for session in report["sessions"]:
        if not session["missing_hashes"] and not session["stale_vectors"]:
            continue
        if not printed:
            print("")
            print("Session issues:")
            printed = True
        label = session["name"] or session["session_id"][:12]
        print(
            f"- {label}: exchanges={session['exchange_count']} vectors={session['vector_count']} "
            f"missing={len(session['missing_hashes'])} stale={len(session['stale_vectors'])}"
        )
        if session["missing_hashes"]:
            print(f"  missing: {', '.join(session['missing_hashes'][:8])}")
        if session["stale_vectors"]:
            stale = ", ".join(f"{item['exchange_idx']}:{item['hash']}" for item in session["stale_vectors"][:8])
            print(f"  stale: {stale}")

    if report["orphan_vectors"]:
        print("")
        print("Orphan vectors:")
        for item in report["orphan_vectors"][:12]:
            print(f"- {item['source_key']}: count={item['count']} max_exchange_idx={item['max_exchange_idx']}")

    if processing.get("stale_rows"):
        print("")
        print("Processing catalog stale rows:")
        for item in processing["stale_rows"][:12]:
            print(
                f"- {item['stage']} {item['source']}:{item['source_key']} "
                f"hash={item['hash']} expected={item['expected_hash']} status={item['status']}"
            )

    if quality.get("samples"):
        print("")
        print("Curated memory quality samples:")
        for item in quality["samples"][:12]:
            if item["kind"] == "duplicate_value":
                print(f"- duplicate_value: {', '.join(item['keys'])}")
            else:
                print(f"- {item['kind']}: {item['key']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only audit of Kairos memory embeddings and synthesis state.")
    parser.add_argument("--sessions-db", default="")
    parser.add_argument("--memory-db", default="")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    sessions_db = args.sessions_db
    memory_db = args.memory_db
    if not sessions_db:
        from src.memory.db_path import resolve_db_path
        sessions_db = resolve_db_path()
    if not memory_db:
        from src.memory.memory_db_path import resolve_memory_db_path
        memory_db = resolve_memory_db_path()

    report = run_audit(sessions_db=sessions_db, memory_db=memory_db, root=args.root)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print_text_report(report)
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
