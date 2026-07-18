from __future__ import annotations

import sqlite3
from pathlib import Path

from src.memory.maintenance.quality_cleanup import (
    apply_quality_cleanup,
    normalize_memory_timestamp,
    plan_quality_cleanup,
    plan_quality_cleanup_state,
)


def test_normalize_memory_timestamp_handles_date_only_and_seconds():
    assert normalize_memory_timestamp(
        "2026-06-15 | Mauro programa de noche.",
        "2026-06-20 21:22:42",
    ) == "2026-06-15 00:00 | Mauro programa de noche."
    assert normalize_memory_timestamp(
        "2026-06-15 14:25:40 | Decisión estable.",
        "2026-06-20 21:22:42",
    ) == "2026-06-15 14:25 | Decisión estable."


def test_plan_quality_cleanup_migrates_facts_and_removes_artifacts():
    plan = plan_quality_cleanup(
        [
            {
                "key": "test:comida",
                "value": "2026-06-15 | Mauro prefiere pizza.",
                "updated_at": "2026-06-20 21:22:42",
            },
            {
                "key": "lan_field_smoke:123",
                "value": "manual probe",
                "updated_at": "2026-06-20 21:22:42",
            },
            {
                "key": "user:ubicacion",
                "value": "Tucumán, Argentina.",
                "updated_at": "2026-06-20 21:22:42",
            },
        ]
    )

    assert plan.migrations == {"test:comida": "user:preferencias-comida"}
    assert plan.deletes == {"test:comida", "lan_field_smoke:123"}
    assert plan.updates["user:preferencias-comida"].startswith("2026-06-15 00:00 |")
    assert plan.updates["user:ubicacion"].startswith("2026-06-20 21:22 |")
    assert plan.conflicts == []


def test_plan_quality_cleanup_state_preserves_file_only_memories_and_prefers_file_value():
    plan = plan_quality_cleanup_state(
        [
            {
                "key": "user:workflow",
                "value": "2026-07-18 01:00 | Valor anterior en DB.",
                "updated_at": "2026-07-18 01:00:00",
            }
        ],
        {
            "user:workflow": "2026-07-18 02:00 | Valor canónico del archivo.",
            "user:file-only": "2026-07-18 02:01 | Recuerdo conservado sólo en archivo.",
        },
        file_updated_at="2026-07-18 02:05",
    )

    assert plan.updates["user:workflow"] == "2026-07-18 02:00 | Valor canónico del archivo."
    assert plan.updates["user:file-only"] == (
        "2026-07-18 02:01 | Recuerdo conservado sólo en archivo."
    )


def test_apply_quality_cleanup_backs_up_and_invalidates_changed_vectors(tmp_path):
    memory_db = tmp_path / "memory.db"
    memory_file = tmp_path / "MEMORY.md"
    backup_dir = tmp_path / "backups"
    memory_file.write_text(
        "# MEMORY.md\n\nUser: Mauro\nSystem: Kairos\n\n## Memories\n"
        "- **test**: test\n"
        "- **user:ubicacion**: Tucumán, Argentina.\n",
        encoding="utf-8",
    )
    conn = sqlite3.connect(memory_db)
    conn.executescript(
        """
        CREATE TABLE memory_index (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE vec_meta (
            rowid INTEGER PRIMARY KEY,
            source TEXT,
            source_key TEXT
        );
        CREATE TABLE vec_entries (rowid INTEGER PRIMARY KEY, embedding BLOB);
        CREATE TABLE memory_work_catalog (
            source TEXT,
            source_key TEXT
        );
        INSERT INTO memory_index VALUES ('test', 'test', '2026-06-20 21:22:42');
        INSERT INTO memory_index VALUES (
            'user:ubicacion', 'Tucumán, Argentina.', '2026-06-20 21:22:42'
        );
        INSERT INTO vec_meta VALUES (1, 'memory', 'user:ubicacion');
        INSERT INTO vec_entries VALUES (1, X'00');
        INSERT INTO memory_work_catalog VALUES ('memory', 'user:ubicacion');
        """
    )
    conn.commit()
    conn.close()

    plan = plan_quality_cleanup(
        [
            {
                "key": "test",
                "value": "test",
                "updated_at": "2026-06-20 21:22:42",
            },
            {
                "key": "user:ubicacion",
                "value": "Tucumán, Argentina.",
                "updated_at": "2026-06-20 21:22:42",
            },
        ]
    )
    result = apply_quality_cleanup(
        memory_db=str(memory_db),
        memory_file=str(memory_file),
        backup_dir=str(backup_dir),
        plan=plan,
    )

    conn = sqlite3.connect(memory_db)
    rows = dict(conn.execute("SELECT key, value FROM memory_index").fetchall())
    assert set(rows) == {"user:ubicacion"}
    assert rows["user:ubicacion"].startswith("2026-06-20 21:22 |")
    assert conn.execute("SELECT COUNT(*) FROM vec_meta").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM vec_entries").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM memory_work_catalog").fetchone()[0] == 0
    conn.close()

    backup_path = Path(result["backup_dir"])
    assert (backup_path / "memory.db").exists()
    assert (backup_path / "MEMORY.md").exists()
    text = memory_file.read_text(encoding="utf-8")
    assert "**test**" not in text
    assert "2026-06-20 21:22 | Tucumán, Argentina." in text
