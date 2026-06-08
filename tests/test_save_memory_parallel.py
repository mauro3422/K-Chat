import os, sys, tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.tools.save_memory import run as save_memory_run


def test_parallel_save_unique_keys():
    """4 save_memory en paralelo con keys distintas — todas deben persistir."""
    temp_dir = tempfile.mkdtemp()
    filepath = os.path.join(temp_dir, "MEMORY.md")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("# MEMORY.md\n\nUser: \nSystem: test\n\n")

    with patch("src.tools.save_memory.CONTEXT_DIR", temp_dir):
        pairs = [("k1", "v1"), ("k2", "v2"), ("k3", "v3"), ("k4", "v4")]
        with ThreadPoolExecutor(max_workers=4) as pool:
            futs = {pool.submit(save_memory_run, key=k, value=v): (k, v) for k, v in pairs}
            for fut in as_completed(futs):
                res = fut.result()
                assert "Éxito" in res, f"Fallo: {res}"

        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

    assert "# MEMORY.md" in content, "Header perdido"
    assert "User:" in content
    assert "System: test" in content
    assert "## Memories" in content
    for k, v in pairs:
        assert f"- **{k}**: {v}" in content, f"Falta entrada {k}"

    os.remove(filepath)
    os.rmdir(temp_dir)


def test_parallel_save_same_key():
    """2 save_memory en paralelo con la misma key — la última escritura gana."""
    temp_dir = tempfile.mkdtemp()
    filepath = os.path.join(temp_dir, "MEMORY.md")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("# MEMORY.md\n\nUser: \nSystem: test\n\n")

    with patch("src.tools.save_memory.CONTEXT_DIR", temp_dir):
        with ThreadPoolExecutor(max_workers=2) as pool:
            futs = [
                pool.submit(save_memory_run, key="key", value="A"),
                pool.submit(save_memory_run, key="key", value="B"),
            ]
            for fut in as_completed(futs):
                res = fut.result()
                assert "Éxito" in res, f"Fallo: {res}"

        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

    assert "# MEMORY.md" in content
    assert "- **key**:" in content
    # Solo debe haber UNA entrada para "key"
    assert content.count("- **key**:") == 1

    os.remove(filepath)
    os.rmdir(temp_dir)


def test_parallel_save_many_keys():
    """20 save_memory en paralelo — todas deben persistir sin perder header."""
    temp_dir = tempfile.mkdtemp()
    filepath = os.path.join(temp_dir, "MEMORY.md")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("# MEMORY.md\n\nUser: \nSystem: test\n\n")

    with patch("src.tools.save_memory.CONTEXT_DIR", temp_dir):
        pairs = [(f"k{i}", f"v{i}") for i in range(20)]
        with ThreadPoolExecutor(max_workers=8) as pool:
            futs = {pool.submit(save_memory_run, key=k, value=v): (k, v) for k, v in pairs}
            for fut in as_completed(futs):
                res = fut.result()
                assert "Éxito" in res

        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

    assert "# MEMORY.md" in content, "Header perdido tras 20 writes"
    assert "## Memories" in content
    for k, v in pairs:
        assert f"- **{k}**: {v}" in content, f"Falta entrada {k}"

    os.remove(filepath)
    os.rmdir(temp_dir)


def test_corrupted_file_repair():
    """Si MEMORY.md está corrupto (sin header), save_memory lo repara."""
    temp_dir = tempfile.mkdtemp()
    filepath = os.path.join(temp_dir, "MEMORY.md")
    # Archivo corrupto: sin header, entrada malformada
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n## Memories\n- **k1**: v1\nbasura: sin formato\n")

    with patch("src.tools.save_memory.CONTEXT_DIR", temp_dir):
        res = save_memory_run(key="k2", value="v2")
        assert "Éxito" in res

        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

    assert "# MEMORY.md" in content, "Header no reparado"
    assert "User:" in content
    assert "System:" in content
    assert "- **k1**: v1" in content, "Entrada previa perdida"
    assert "- **k2**: v2" in content, "Nueva entrada faltante"
    assert "basura" not in content, "Entrada malformada no debería persistir"

    os.remove(filepath)
    os.rmdir(temp_dir)
