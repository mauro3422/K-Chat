import os
import sys

import pytest

from src.tools.dependency_graph import (
    _extract_imports,
    _classify_import,
    _find_project_root,
    _analyze_file,
    DEFINITION,
    run as dependency_graph_run,
)


class TestExtractImports:
    def test_regular_import(self, tmp_path):
        p = tmp_path / "mod.py"
        p.write_text("import os\nimport sys\n")
        imports = _extract_imports(str(p))
        modules = {imp["module"] for imp in imports}
        assert "os" in modules
        assert "sys" in modules

    def test_from_import(self, tmp_path):
        p = tmp_path / "mod.py"
        p.write_text("from pathlib import Path\n")
        imports = _extract_imports(str(p))
        assert any(imp["module"] == "pathlib" for imp in imports)

    def test_type_checking_detected(self, tmp_path):
        p = tmp_path / "mod.py"
        p.write_text(
            "from typing import TYPE_CHECKING\n"
            "if TYPE_CHECKING:\n"
            "    import numpy\n"
        )
        imports = _extract_imports(str(p))
        tc = [i for i in imports if i["type_checking"]]
        assert len(tc) >= 1
        assert all(i["type_checking"] for i in tc)
        normal = [i for i in imports if not i["type_checking"]]
        assert any("typing" in i["module"] for i in normal)

    def test_import_alias(self, tmp_path):
        p = tmp_path / "mod.py"
        p.write_text("import numpy as np\n")
        imports = _extract_imports(str(p))
        assert any(imp["module"] == "numpy" for imp in imports)

    def test_syntax_error_returns_empty(self, tmp_path):
        p = tmp_path / "bad.py"
        p.write_text("def foo(\n")
        assert _extract_imports(str(p)) == []

    def test_missing_file_returns_empty(self):
        assert _extract_imports("/no/such/file.py") == []

    def test_from_import_star(self, tmp_path):
        p = tmp_path / "mod.py"
        p.write_text("from os import *\n")
        imports = _extract_imports(str(p))
        assert any(i["module"] == "os" and "*" in i["names"] for i in imports)


class TestFindProjectRoot:
    def test_detects_src_and_web(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "web").mkdir()
        sub = tmp_path / "sub"
        sub.mkdir()
        assert _find_project_root(str(sub)) == str(tmp_path)

    def test_fallback_src_parent(self, tmp_path):
        (tmp_path / "src").mkdir()
        inner = tmp_path / "a" / "b"
        inner.mkdir(parents=True)
        root = _find_project_root(str(inner))
        # Fallback: last resort is parent of start_path
        assert root == str(tmp_path / "a")

    def test_no_src_returns_parent(self, tmp_path):
        inner = tmp_path / "x" / "y"
        inner.mkdir(parents=True)
        root = _find_project_root(str(inner))
        # Fallback: last resort is parent of start_path
        assert root == str(tmp_path / "x")


class TestClassifyImport:
    @pytest.fixture
    def proot(self, tmp_path):
        for d in ("src/memory", "src/llm", "src/tools", "src/context",
                  "src/core", "src/api", "web"):
            (tmp_path / d).mkdir(parents=True)
            (tmp_path / d / "__init__.py").write_text("")
        return tmp_path

    def test_downward_tools_to_memory(self, proot):
        r = _classify_import("src/tools/foo.py", "src.memory.x", str(proot))
        assert r["direction"] == "downward"

    def test_upward_tools_to_core(self, proot):
        r = _classify_import("src/tools/foo.py", "src.core.x", str(proot))
        assert r["direction"] == "upward"

    def test_same_layer(self, proot):
        r = _classify_import("src/tools/foo.py", "src.tools.bar", str(proot))
        assert r["direction"] == "same"

    def test_external_module(self, proot):
        r = _classify_import("src/tools/foo.py", "os", str(proot))
        assert r["direction"] == "external"

    def test_target_not_found(self, proot):
        r = _classify_import("src/tools/foo.py", "src.nonexistent.missing", str(proot))
        assert r["direction"] == "external"

    def test_source_outside_layers(self, proot):
        r = _classify_import("external/s.py", "os", str(proot))
        assert r["direction"] == "external"


class TestAnalyzeFile:
    @pytest.fixture
    def proot(self, tmp_path):
        (tmp_path / "src" / "tools").mkdir(parents=True)
        (tmp_path / "src" / "memory").mkdir(parents=True)
        (tmp_path / "src" / "memory" / "storage.py").write_text("def load(): pass\n")
        (tmp_path / "web").mkdir()
        return tmp_path

    def test_downward_dependency(self, proot):
        f = proot / "src" / "tools" / "loader.py"
        f.write_text("import src.memory.storage\n")
        r = _analyze_file(str(f), str(proot))
        assert r["file"].endswith("src/tools/loader.py")
        assert any(d["direction"] == "downward" for d in r["dependencies"])

    def test_type_checking_skipped_by_default(self, proot):
        (proot / "src" / "core").mkdir()
        (proot / "src" / "core" / "engine.py").write_text("def run(): pass\n")
        f = proot / "src" / "tools" / "loader.py"
        f.write_text(
            "from typing import TYPE_CHECKING\n"
            "if TYPE_CHECKING:\n"
            "    import src.core.engine\n"
        )
        r = _analyze_file(str(f), str(proot), verbose=False)
        tc = [d for d in r["dependencies"] if d["type_checking"]]
        assert len(tc) == 0

    def test_type_checking_shown_when_verbose(self, proot):
        (proot / "src" / "core").mkdir()
        (proot / "src" / "core" / "engine.py").write_text("def run(): pass\n")
        f = proot / "src" / "tools" / "loader.py"
        f.write_text(
            "from typing import TYPE_CHECKING\n"
            "if TYPE_CHECKING:\n"
            "    import src.core.engine\n"
        )
        r = _analyze_file(str(f), str(proot), verbose=True)
        tc = [d for d in r["dependencies"] if d["type_checking"]]
        assert len(tc) >= 1

    def test_no_dependencies(self, proot):
        f = proot / "src" / "tools" / "standalone.py"
        f.write_text("x = 42\n")
        r = _analyze_file(str(f), str(proot))
        assert r["dependencies"] == []

    def test_upward_dep_detected(self, proot):
        (proot / "src" / "core").mkdir()
        (proot / "src" / "core" / "engine.py").write_text("def run(): pass\n")
        f = proot / "src" / "tools" / "client.py"
        f.write_text("import src.core.engine\n")
        r = _analyze_file(str(f), str(proot))
        assert any(d["direction"] == "upward" for d in r["dependencies"])


@pytest.mark.anyio
class TestRun:
    @pytest.fixture
    def proot(self, tmp_path):
        (tmp_path / "src" / "tools").mkdir(parents=True)
        (tmp_path / "src" / "memory").mkdir(parents=True)
        (tmp_path / "src" / "memory" / "storage.py").write_text("def load(): pass\n")
        (tmp_path / "web").mkdir()
        # File with actual dependency so it shows in output
        (tmp_path / "src" / "tools" / "mod_a.py").write_text("import src.memory.storage\n")
        return tmp_path

    async def test_requires_path(self):
        r = await dependency_graph_run()
        assert "Proporciona un path" in r

    async def test_basic_graph(self, proot):
        r = await dependency_graph_run(path=str(proot / "src" / "tools"))
        assert "DEPENDENCY GRAPH" in r
        assert "mod_a.py" in r

    async def test_filter_by_file(self, proot):
        (proot / "src" / "tools" / "mod_b.py").write_text("import src.memory.storage\n")
        r = await dependency_graph_run(path=str(proot / "src" / "tools"), file="mod_a.py")
        assert "mod_a.py" in r
        assert "mod_b.py" not in r

    async def test_non_existent_path(self, proot):
        r = await dependency_graph_run(path=str(proot / "no_such_dir"))
        assert "no es un directorio" in r

    async def test_definition_fixture(self):
        assert DEFINITION["function"]["name"] == "dependency_graph"
