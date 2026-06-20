from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.anyio
async def test_compare_reports_mismatches_with_db_metadata(tmp_path: Path):
    from src.memory.operations.sync import _compare

    memory_md = tmp_path / "MEMORY.md"
    memory_md.write_text(
        "# MEMORY.md\n\nUser: test\nSystem: test\n\n## Memories\n"
        "- **Preferencia**: TypeScript\n"
        "- **Arquitectura**: Modular\n",
        encoding="utf-8",
    )

    repos = SimpleNamespace(
        memory=SimpleNamespace(
            memory_index=SimpleNamespace(
                get_all=AsyncMock(
                    return_value=[
                        {"key": "Preferencia", "value": "Python", "updated_at": "2026-06-19T10:00:00"},
                        {"key": "SoloDB", "value": "Persistida", "updated_at": "2026-06-19T11:00:00"},
                    ]
                )
            )
        )
    )

    with patch("src.memory.operations.sync._get_memory_md_path", return_value=str(memory_md)):
        report = await _compare(fmt="json", repos=repos)

    assert '"matched": 0' in report
    assert '"only_in_md": [\n    "Arquitectura"' in report
    assert '"only_in_db": [\n    "SoloDB"' in report
    assert '"db_updated_at": "2026-06-19T10:00:00"' in report


@pytest.mark.anyio
async def test_sync_preview_counts_add_update_delete(tmp_path: Path):
    from src.memory.operations.sync import _sync

    memory_md = tmp_path / "MEMORY.md"
    memory_md.write_text(
        "# MEMORY.md\n\nUser: test\nSystem: test\n\n## Memories\n"
        "- **Preferencia**: TypeScript\n"
        "- **Arquitectura**: Modular\n",
        encoding="utf-8",
    )

    idx = SimpleNamespace(
        get_all=AsyncMock(
            return_value=[
                {"key": "Preferencia", "value": "Python", "updated_at": "2026-06-19T10:00:00"},
                {"key": "SoloDB", "value": "Persistida", "updated_at": "2026-06-19T11:00:00"},
            ]
        ),
        upsert=AsyncMock(),
        delete=AsyncMock(),
    )
    repos = SimpleNamespace(memory=SimpleNamespace(memory_index=idx))

    with patch("src.memory.operations.sync._get_memory_md_path", return_value=str(memory_md)):
        preview = await _sync(dry_run=True, confirm=True, repos=repos)

    assert "Add: 1" in preview
    assert "Update: 1" in preview
    assert "Delete: 1" in preview
    idx.upsert.assert_not_awaited()
    idx.delete.assert_not_awaited()


@pytest.mark.anyio
async def test_sync_reconstructs_memory_db_from_memory_md(tmp_path: Path):
    from src.memory.operations.sync import _sync

    memory_md = tmp_path / "MEMORY.md"
    memory_md.write_text(
        "# MEMORY.md\n\nUser: test\nSystem: test\n\n## Memories\n"
        "- **Preferencia**: TypeScript\n"
        "- **Arquitectura**: Modular\n",
        encoding="utf-8",
    )

    idx = SimpleNamespace(
        get_all=AsyncMock(return_value=[]),
        upsert=AsyncMock(),
        delete=AsyncMock(),
    )
    repos = SimpleNamespace(memory=SimpleNamespace(memory_index=idx))

    with patch("src.memory.operations.sync._get_memory_md_path", return_value=str(memory_md)):
        result = await _sync(dry_run=False, confirm=False, repos=repos)

    assert "Reconstructed" in result
    assert idx.upsert.await_count == 2
    idx.delete.assert_not_awaited()


@pytest.mark.anyio
async def test_compare_reports_rename_candidates(tmp_path: Path):
    from src.memory.operations.sync import _compare

    memory_md = tmp_path / "MEMORY.md"
    memory_md.write_text(
        "# MEMORY.md\n\nUser: test\nSystem: test\n\n## Memories\n"
        "- **Preferencia TS**: TypeScript\n",
        encoding="utf-8",
    )

    repos = SimpleNamespace(
        memory=SimpleNamespace(
            memory_index=SimpleNamespace(
                get_all=AsyncMock(
                    return_value=[
                        {"key": "Preferencia", "value": "Python", "updated_at": "2026-06-19T10:00:00"},
                    ]
                )
            )
        )
    )

    with patch("src.memory.operations.sync._get_memory_md_path", return_value=str(memory_md)):
        report = await _compare(fmt="json", repos=repos)

    assert '"rename_candidates": [' in report
    assert '"orphan": "Preferencia"' in report
    assert '"target": "Preferencia TS"' in report


@pytest.mark.anyio
async def test_repair_uses_memory_md_value_for_rename(tmp_path: Path):
    from src.memory.operations.sync import _repair

    memory_md = tmp_path / "MEMORY.md"
    memory_md.write_text(
        "# MEMORY.md\n\nUser: test\nSystem: test\n\n## Memories\n"
        "- **Preferencia TS**: TypeScript\n",
        encoding="utf-8",
    )

    idx = SimpleNamespace(
        get_all=AsyncMock(
            return_value=[
                {"key": "Preferencia", "value": "Python", "updated_at": "2026-06-19T10:00:00"},
            ]
        ),
        upsert=AsyncMock(),
        delete=AsyncMock(),
    )
    repos = SimpleNamespace(memory=SimpleNamespace(memory_index=idx))

    with patch("src.memory.operations.sync._get_memory_md_path", return_value=str(memory_md)):
        preview = await _repair(dry_run=True, confirm=True, repos=repos)
        result = await _repair(dry_run=False, confirm=True, repos=repos)

    assert "Rename 'Preferencia' -> 'Preferencia TS'" in preview
    idx.delete.assert_awaited_once_with("Preferencia")
    idx.upsert.assert_awaited_once_with("Preferencia TS", "TypeScript")
    assert "renombradas" in result
