#!/usr/bin/env python
"""Remove legacy vector/search tables from sessions.db after safe backup.

sessions.db is the local conversation database. Embeddings and semantic search
state now live in memory.db, so old vector tables in sessions.db are legacy
residue that confuses audits and repair workflows.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


LEGACY_TABLES = (
    "vec_entries",
    "vec_entries_chunks",
    "vec_entries_info",
    "vec_entries_rowids",
    "vec_entries_vector_chunks00",
    "vec_meta",
    "vec_keywords",
    "exchange_clusters",
    "topic_clusters",
    "topic_relations",
    "entities",
    "entity_aliases",
    "entity_mentions",
    "entity_relations",
    "retrieval_log",
    "memory_schema_version",
)

PROTECTED_TABLES = {
    "sessions",
    "messages",
    "tool_calls",
    "debug_info",
    "widget_states",
    "saved_widgets",
    "widget_versions",
    "chat_journal",
    "gateway_log",
    "telegram_msg_ids",
    "memory_index",
    "schema_version",
    "sqlite_sequence",
}


@dataclass
class LegacyTable:
    name: str
    kind: str
    rows: int | None


@dataclass
class CleanupReport:
    sessions_db: str
    planned_tables: list[LegacyTable]
    protected_present: list[str]
    backup_path: str = ""
    dropped_tables: list[str] | None = None

    @property
    def needs_cleanup(self) -> bool:
        return bool(self.planned_tables)


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def table_rows(conn: sqlite3.Connection, name: str) -> int | None:
    try:
        return int(conn.execute(f'SELECT COUNT(1) FROM "{name}"').fetchone()[0])
    except sqlite3.Error:
        return None


def inspect_legacy_tables(sessions_db: str) -> CleanupReport:
    with connect(sessions_db) as conn:
        rows = conn.execute(
            "SELECT name, type FROM sqlite_master WHERE type IN ('table', 'view')"
        ).fetchall()
        objects = {str(row["name"]): str(row["type"]) for row in rows}
        planned = [
            LegacyTable(name=name, kind=objects[name], rows=table_rows(conn, name))
            for name in LEGACY_TABLES
            if name in objects
        ]
        protected = sorted(name for name in PROTECTED_TABLES if name in objects)
    return CleanupReport(
        sessions_db=sessions_db,
        planned_tables=planned,
        protected_present=protected,
    )


def make_backup(sessions_db: str, backup_root: str) -> str:
    source = Path(sessions_db)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination_dir = Path(backup_root) / "legacy-session-vectors"
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / f"{source.stem}.{stamp}.db"
    counter = 1
    while destination.exists():
        destination = destination_dir / f"{source.stem}.{stamp}.{counter}.db"
        counter += 1
    with sqlite3.connect(sessions_db) as src, sqlite3.connect(destination) as dst:
        src.backup(dst)
    return str(destination)


def load_sqlite_vec(conn: sqlite3.Connection) -> None:
    try:
        conn.enable_load_extension(True)
        import sqlite_vec

        sqlite_vec.load(conn)
    except Exception:
        pass


def apply_cleanup(sessions_db: str, backup_root: str) -> CleanupReport:
    report = inspect_legacy_tables(sessions_db)
    if not report.needs_cleanup:
        report.dropped_tables = []
        return report

    backup_path = make_backup(sessions_db, backup_root)
    dropped: list[str] = []
    with connect(sessions_db) as conn:
        load_sqlite_vec(conn)
        conn.execute("PRAGMA foreign_keys=OFF")
        existing = {
            str(row["name"])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
            ).fetchall()
        }
        for name in LEGACY_TABLES:
            if name not in existing:
                continue
            conn.execute(f'DROP TABLE IF EXISTS "{name}"')
            dropped.append(name)
        conn.commit()
    report.backup_path = backup_path
    report.dropped_tables = dropped
    return report


def report_to_dict(report: CleanupReport) -> dict[str, Any]:
    data = asdict(report)
    data["planned_tables"] = [asdict(table) for table in report.planned_tables]
    data["needs_cleanup"] = report.needs_cleanup
    return data


def print_text(report: CleanupReport, *, applied: bool) -> None:
    print("Kairos legacy session vector cleanup")
    print(f"sessions_db={report.sessions_db}")
    print(f"planned_tables={len(report.planned_tables)}")
    if report.planned_tables:
        for table in report.planned_tables:
            rows = "?" if table.rows is None else str(table.rows)
            print(f"- {table.name}: kind={table.kind} rows={rows}")
    if applied:
        print(f"backup={report.backup_path or '-'}")
        print(f"dropped_tables={len(report.dropped_tables or [])}")
    else:
        print("mode=dry-run")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Clean legacy vector tables from sessions.db.")
    parser.add_argument("--sessions-db", default="")
    parser.add_argument("--backup-root", default=".kairos/backups")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true", help="Exit nonzero if legacy tables remain.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    sessions_db = args.sessions_db
    if not sessions_db:
        from src.memory.db_path import resolve_db_path

        sessions_db = resolve_db_path()

    report = apply_cleanup(sessions_db, args.backup_root) if args.apply else inspect_legacy_tables(sessions_db)
    remaining = inspect_legacy_tables(sessions_db) if args.apply and args.strict else report
    if args.json:
        print(json.dumps(report_to_dict(report), ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print_text(report, applied=args.apply)
    return 1 if args.strict and remaining.needs_cleanup else 0


if __name__ == "__main__":
    raise SystemExit(main())
