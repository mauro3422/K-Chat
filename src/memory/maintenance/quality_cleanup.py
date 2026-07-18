"""Conservative cleanup for legacy curated-memory quality issues."""

from __future__ import annotations

import re
import shutil
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from src.memory.operations._helpers import _write_memory_md


@dataclass
class QualityCleanupPlan:
    updates: dict[str, str] = field(default_factory=dict)
    deletes: set[str] = field(default_factory=set)
    migrations: dict[str, str] = field(default_factory=dict)
    conflicts: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "updates": len(self.updates),
            "deletes": len(self.deletes),
            "migrations": dict(sorted(self.migrations.items())),
            "conflicts": list(self.conflicts),
            "updated_keys": sorted(self.updates),
            "deleted_keys": sorted(self.deletes),
        }


def normalize_memory_timestamp(value: str, updated_at: str) -> str:
    """Return a canonical ``YYYY-MM-DD HH:MM |`` prefix without inventing a date."""

    stripped = value.strip()
    canonical = re.match(
        r"^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})(?::\d{2})?\s*\|\s*(.*)$",
        stripped,
        flags=re.DOTALL,
    )
    if canonical:
        return f"{canonical.group(1)} {canonical.group(2)} | {canonical.group(3).strip()}"

    date_only = re.match(r"^(\d{4}-\d{2}-\d{2})\s*\|\s*(.*)$", stripped, flags=re.DOTALL)
    if date_only:
        return f"{date_only.group(1)} 00:00 | {date_only.group(2).strip()}"

    raw_timestamp = str(updated_at or "").strip().replace("T", " ")
    parsed_prefix = raw_timestamp[:16]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", parsed_prefix):
        raise ValueError("updated_at does not contain a usable timestamp")
    return f"{parsed_prefix} | {stripped}"


def _migration_target(key: str) -> str:
    return {
        "test:comida": "user:preferencias-comida",
        "test:habito": "user:habito-programacion-nocturna",
        "test:nombre": "user:proyecto-k-chat",
    }.get(key, "")


def _is_disposable_quality_artifact(key: str) -> bool:
    lowered = key.lower()
    return (
        lowered == "test"
        or lowered.startswith("test:")
        or lowered.startswith("lan_field_smoke:")
        or lowered.startswith("lan_failover_drill:")
        or lowered.startswith("stress-test:")
        or lowered.startswith("checkpoint:curation-")
        or lowered.startswith("checkpoint:stress-test")
        or lowered.startswith("checkpoint:test-")
        or lowered.startswith("estado:stress-test")
        or lowered.startswith("user:horario-stress-test")
        or lowered.startswith("user:horario-test-estres")
        or lowered.startswith("user:prueba-estres")
    )


def plan_quality_cleanup(rows: Iterable[dict[str, Any]]) -> QualityCleanupPlan:
    """Plan timestamp normalization, probe removal, and three known fact migrations."""

    materialized = [dict(row) for row in rows]
    existing = {str(row["key"]): str(row.get("value") or "") for row in materialized}
    plan = QualityCleanupPlan()

    for row in materialized:
        key = str(row["key"])
        value = str(row.get("value") or "").strip()
        updated_at = str(row.get("updated_at") or "")
        target = _migration_target(key)

        if target:
            normalized = normalize_memory_timestamp(value, updated_at)
            if target in existing and existing[target].strip() != normalized:
                plan.conflicts.append(f"{key} -> {target}")
                continue
            plan.updates[target] = normalized
            plan.deletes.add(key)
            plan.migrations[key] = target
            continue

        if _is_disposable_quality_artifact(key):
            plan.deletes.add(key)
            continue

        normalized = normalize_memory_timestamp(value, updated_at)
        if normalized != value:
            plan.updates[key] = normalized

    return plan


def plan_quality_cleanup_state(
    db_rows: Iterable[dict[str, Any]],
    file_memories: dict[str, str],
    *,
    file_updated_at: str,
) -> QualityCleanupPlan:
    """Plan cleanup over the safe union, preferring MEMORY.md on value conflicts."""

    database = {str(row["key"]): dict(row) for row in db_rows}
    merged = {key: dict(row) for key, row in database.items()}
    for key, value in file_memories.items():
        merged[key] = {
            "key": key,
            "value": value,
            "updated_at": database.get(key, {}).get("updated_at") or file_updated_at,
        }

    plan = plan_quality_cleanup(merged.values())
    for key, row in merged.items():
        if key in plan.deletes or key in plan.migrations:
            continue
        normalized = normalize_memory_timestamp(
            str(row.get("value") or ""),
            str(row.get("updated_at") or ""),
        )
        database_value = str(database.get(key, {}).get("value") or "")
        if key not in database or database_value != normalized:
            plan.updates[key] = normalized
    return plan


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _load_vector_extension_if_needed(conn: sqlite3.Connection) -> None:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='vec_entries'"
    ).fetchone()
    definition = str(row[0] or "") if row else ""
    if "USING VEC0" not in definition.upper():
        return
    import sqlite_vec

    conn.enable_load_extension(True)
    sqlite_vec.load(conn)


def _invalidate_memory_embeddings(conn: sqlite3.Connection, keys: set[str]) -> int:
    if not keys or not _table_exists(conn, "vec_meta"):
        return 0

    deleted = 0
    has_entries = _table_exists(conn, "vec_entries")
    has_catalog = _table_exists(conn, "memory_work_catalog")
    for key in sorted(keys):
        rowids = [
            int(row[0])
            for row in conn.execute(
                "SELECT rowid FROM vec_meta WHERE source='memory' AND source_key=?",
                (key,),
            ).fetchall()
        ]
        if has_entries:
            for rowid in rowids:
                conn.execute("DELETE FROM vec_entries WHERE rowid=?", (rowid,))
        deleted += conn.execute(
            "DELETE FROM vec_meta WHERE source='memory' AND source_key=?",
            (key,),
        ).rowcount
        if has_catalog:
            conn.execute(
                "DELETE FROM memory_work_catalog WHERE source='memory' AND source_key=?",
                (key,),
            )
    return deleted


def apply_quality_cleanup(
    *,
    memory_db: str,
    memory_file: str,
    backup_dir: str,
    plan: QualityCleanupPlan,
) -> dict[str, Any]:
    """Apply a conflict-free plan after making SQLite and text backups."""

    if plan.conflicts:
        raise ValueError("cleanup plan has migration conflicts")

    db_path = Path(memory_db).resolve()
    file_path = Path(memory_file).resolve()
    backup_root = Path(backup_dir).resolve()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    destination = backup_root / stamp
    destination.mkdir(parents=True, exist_ok=False)

    conn = sqlite3.connect(db_path)
    _load_vector_extension_if_needed(conn)
    backup_conn = sqlite3.connect(destination / db_path.name)
    try:
        conn.backup(backup_conn)
    finally:
        backup_conn.close()

    if file_path.exists():
        shutil.copy2(file_path, destination / file_path.name)

    touched = set(plan.updates) | set(plan.deletes)
    canonical_memories: dict[str, str]
    conn.execute("BEGIN IMMEDIATE")
    try:
        invalidated = _invalidate_memory_embeddings(conn, touched)
        for key, value in sorted(plan.updates.items()):
            conn.execute(
                """
                INSERT INTO memory_index (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET
                    value=excluded.value,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (key, value),
            )
        for key in sorted(plan.deletes):
            conn.execute("DELETE FROM memory_index WHERE key=?", (key,))
        conn.commit()
        canonical_memories = dict(
            conn.execute("SELECT key, value FROM memory_index ORDER BY key").fetchall()
        )
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    _write_memory_md(str(file_path), canonical_memories)

    return {
        "backup_dir": str(destination),
        "updated": len(plan.updates),
        "deleted": len(plan.deletes),
        "invalidated_vectors": invalidated,
    }


def load_memory_rows(memory_db: str) -> list[dict[str, Any]]:
    path = Path(memory_db).resolve()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        return [
            dict(row)
            for row in conn.execute(
                "SELECT key, value, updated_at FROM memory_index ORDER BY key"
            ).fetchall()
        ]
    finally:
        conn.close()
