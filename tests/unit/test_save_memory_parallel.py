import asyncio
import pytest
from unittest.mock import AsyncMock
import os
import tempfile
from unittest.mock import patch


from src.tools.save_memory import run as save_memory_run


def _temp_memory_file():
    temp_dir = tempfile.mkdtemp()
    filepath = os.path.join(temp_dir, "MEMORY.md")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("# MEMORY.md\n\nUser: \nSystem: test\n\n")
    return temp_dir, filepath


def _cleanup(temp_dir, filepath):
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
        os.rmdir(temp_dir)
    except Exception:
        pass


@pytest.mark.anyio
async def test_parallel_save_unique_keys():
    temp_dir, filepath = _temp_memory_file()
    try:
        with patch("src.tools.save_memory.CONTEXT_DIR", temp_dir):
            pairs = [("k1", "v1"), ("k2", "v2"), ("k3", "v3"), ("k4", "v4")]
            results = await asyncio.gather(*[
                save_memory_run(key=k, value=v, scope="canonical") for k, v in pairs
            ])
            for res in results:
                assert "[OK]" in res, f"Failed: {res}"

            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()

        assert "# MEMORY.md" in content, "Header perdido"
        assert "User:" in content
        assert "System: test" in content
        assert "## Memories" in content
        for k, v in pairs:
            assert f"- **{k}**: {v}" in content, f"Falta entrada {k}"
    finally:
        _cleanup(temp_dir, filepath)


@pytest.mark.anyio
async def test_parallel_save_same_key():
    temp_dir, filepath = _temp_memory_file()
    try:
        with patch("src.tools.save_memory.CONTEXT_DIR", temp_dir):
            results = await asyncio.gather(
                save_memory_run(key="key", value="A", scope="canonical"),
                save_memory_run(key="key", value="B", scope="canonical"),
            )
            for res in results:
                assert "[OK]" in res, f"Failed: {res}"

            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()

        assert "# MEMORY.md" in content
        assert "- **key**:" in content
        assert content.count("- **key**:") == 1
    finally:
        _cleanup(temp_dir, filepath)


@pytest.mark.anyio
async def test_parallel_save_many_keys():
    temp_dir, filepath = _temp_memory_file()
    try:
        with patch("src.tools.save_memory.CONTEXT_DIR", temp_dir):
            pairs = [(f"k{i}", f"v{i}") for i in range(20)]
            results = await asyncio.gather(*[
                save_memory_run(key=k, value=v, scope="canonical") for k, v in pairs
            ])
            for res in results:
                assert "[OK]" in res

            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()

        assert "# MEMORY.md" in content, "Header perdido tras 20 writes"
        assert "## Memories" in content
        for k, v in pairs:
            assert f"- **{k}**: {v}" in content, f"Falta entrada {k}"
    finally:
        _cleanup(temp_dir, filepath)


@pytest.mark.anyio
async def test_corrupted_file_repair():
    temp_dir, filepath = _temp_memory_file()
    try:
        # Corrupt: write junk
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n## Memories\n- **k1**: v1\nbasura: sin formato\n")

        with patch("src.tools.save_memory.CONTEXT_DIR", temp_dir):
            res = await save_memory_run(key="k2", value="v2", scope="canonical")
            assert "[OK]" in res

            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()

        assert "# MEMORY.md" in content, "Header no reparado"
        assert "User:" in content
        assert "System:" in content
        assert "- **k1**: v1" in content, "Entrada previa perdida"
        assert "- **k2**: v2" in content, "Nueva entrada faltante"
        assert "basura" not in content, "Entrada malformada no debería persistir"
    finally:
        _cleanup(temp_dir, filepath)
