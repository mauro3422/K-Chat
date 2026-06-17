"""Tests for impact_analysis tool."""

import os
import ast
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.tools import impact_analysis


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_py(path: str, content: str) -> str:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return str(p.resolve())


# ---------------------------------------------------------------------------
# run() — async entry point
# ---------------------------------------------------------------------------

class TestRun:
    @pytest.mark.anyio
    async def test_missing_name_returns_error(self):
        result = await impact_analysis.run(path="/tmp/foo.py", name="")
        assert "[ERROR] Proporciona el nombre" in result

    @pytest.mark.anyio
    async def test_missing_path_returns_error(self):
        result = await impact_analysis.run(name="foo", path="")
        assert "[ERROR] Proporciona el path" in result

    @pytest.mark.anyio
    async def test_non_existent_file_returns_error(self):
        result = await impact_analysis.run(name="foo", path="/tmp/_nonexistent_12345.py")
        assert "[ERROR]" in result or "no es un archivo" in result

    @pytest.mark.anyio
    async def test_returns_impact_report_with_caller(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Source file with a function
            src = _write_py(os.path.join(tmp, "mymod.py"), """
def greet(name):
    return f"Hello {name}"
""")
            # Caller file
            _write_py(os.path.join(tmp, "caller.py"), f"""
from mymod import greet

def run():
    return greet("world")
""")
            project_root = impact_analysis._find_project_root(src)
            with patch("src.paths.CONTEXT_DIR", project_root):
                result = await impact_analysis.run(name="greet", path=src)
            assert "IMPACT ANALYSIS" in result
            assert "greet" in result
            # Should mention caller.py or have references
            assert len(result) > 50


# ---------------------------------------------------------------------------
# _find_project_root
# ---------------------------------------------------------------------------

class TestFindProjectRoot:
    def test_returns_parent_if_src_and_web_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "src"))
            os.makedirs(os.path.join(tmp, "web"))
            nested = os.path.join(tmp, "sub", "deep")
            os.makedirs(nested)
            result = impact_analysis._find_project_root(nested)
            assert result == os.path.realpath(tmp)

    def test_falls_back_to_parent_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            # No src/ no web/
            result = impact_analysis._find_project_root(tmp)
            assert result == os.path.realpath(os.path.dirname(tmp))


# ---------------------------------------------------------------------------
# _get_function_signature
# ---------------------------------------------------------------------------

class TestGetFunctionSignature:
    def test_extracts_sync_function(self):
        with tempfile.TemporaryDirectory() as tmp:
            fpath = _write_py(os.path.join(tmp, "mod.py"), """
def foo(a, b, c=1):
    pass
""")
            sig = impact_analysis._get_function_signature(fpath, "foo")
            assert sig == "def foo(a, b, c)"

    def test_extracts_async_function(self):
        with tempfile.TemporaryDirectory() as tmp:
            fpath = _write_py(os.path.join(tmp, "mod.py"), """
async def fetch(url):
    return 42
""")
            sig = impact_analysis._get_function_signature(fpath, "fetch")
            assert "async def fetch(url)" in sig

    def test_extracts_class_with_methods(self):
        with tempfile.TemporaryDirectory() as tmp:
            fpath = _write_py(os.path.join(tmp, "mod.py"), """
class MyService:
    def run(self):
        pass
    def stop(self):
        pass
""")
            sig = impact_analysis._get_function_signature(fpath, "MyService")
            assert "class MyService" in sig
            assert "run" in sig
            assert "stop" in sig

    def test_returns_none_when_not_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            fpath = _write_py(os.path.join(tmp, "mod.py"), "x = 1")
            sig = impact_analysis._get_function_signature(fpath, "does_not_exist")
            assert sig is None

    def test_returns_none_on_syntax_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            fpath = _write_py(os.path.join(tmp, "bad.py"), "this is not valid python @@@")
            sig = impact_analysis._get_function_signature(fpath, "anything")
            assert sig is None

    def test_extracts_with_vararg(self):
        with tempfile.TemporaryDirectory() as tmp:
            fpath = _write_py(os.path.join(tmp, "mod.py"), """
def flex(*args, **kwargs):
    pass
""")
            sig = impact_analysis._get_function_signature(fpath, "flex")
            assert "*args" in sig
            assert "**kwargs" in sig


# ---------------------------------------------------------------------------
# _find_callers
# ---------------------------------------------------------------------------

class TestFindCallers:
    def _setup_project(self, tmp: str, files: dict[str, str]) -> str:
        root = os.path.join(tmp, "project")
        for rel, content in files.items():
            _write_py(os.path.join(root, rel), content)
        return root

    def test_finds_import_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._setup_project(tmp, {
                "mymod.py": "def util(): pass",
                "caller.py": "from mymod import util\nutil()",
            })
            src = os.path.join(root, "mymod.py")
            callers = impact_analysis._find_callers("util", root, src)
            assert len(callers) == 1
            assert callers[0]["file"].endswith("caller.py")
            types = {r["type"] for r in callers[0]["references"]}
            assert "import" in types

    def test_finds_direct_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._setup_project(tmp, {
                "lib.py": "def calc(x): return x",
                "use.py": "from lib import calc\ncalc(42)",
            })
            src = os.path.join(root, "lib.py")
            callers = impact_analysis._find_callers("calc", root, src)
            refs = callers[0]["references"]
            assert any(r["type"] == "call" for r in refs)

    def test_finds_method_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._setup_project(tmp, {
                "service.py": "class Svc:\n    def run(self): pass",
                "client.py": "obj = Svc()\nobj.run()",
            })
            src = os.path.join(root, "service.py")
            callers = impact_analysis._find_callers("run", root, src)
            assert len(callers) == 1
            assert any(r["type"] == "method_call" for r in callers[0]["references"])

    def test_finds_attribute_access(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._setup_project(tmp, {
                "cfg.py": "TIMEOUT = 30",
                "app.py": "from cfg import TIMEOUT\nprint(TIMEOUT)",
            })
            src = os.path.join(root, "cfg.py")
            callers = impact_analysis._find_callers("TIMEOUT", root, src)
            assert len(callers) == 1
            assert any(r["type"] == "usage" for r in callers[0]["references"])

    def test_skips_self_when_not_including_internal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._setup_project(tmp, {
                "mod.py": "def foo(): pass\ndef bar(): foo()",
            })
            src = os.path.join(root, "mod.py")
            callers = impact_analysis._find_callers("foo", root, src, include_internal=False)
            assert len(callers) == 0

    def test_includes_self_when_including_internal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._setup_project(tmp, {
                "mod.py": "def foo(): pass\ndef bar(): foo()",
            })
            src = os.path.join(root, "mod.py")
            callers = impact_analysis._find_callers("foo", root, src, include_internal=True)
            assert len(callers) == 1
            assert callers[0]["file"].endswith("mod.py")

    def test_returns_empty_when_no_references(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._setup_project(tmp, {
                "a.py": "x = 1",
                "b.py": "y = 2",
            })
            callers = impact_analysis._find_callers("nonexistent", root, "dummy.py")
            assert callers == []

    def test_skips_non_py_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._setup_project(tmp, {
                "mod.py": "TOOL = 'x'",
            })
            (Path(root) / "data.txt").write_text("TOOL")
            src = os.path.join(root, "mod.py")
            # The txt file should be skipped
            callers = impact_analysis._find_callers("TOOL", root, src)
            assert len(callers) == 0

    def test_skips_dot_underscore_etc(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._setup_project(tmp, {
                "mod.py": "HOOK = 1",
            })
            (Path(root) / "__pycache__").mkdir()
            (Path(root) / "__pycache__" / "cache.py").write_text("HOOK")
            src = os.path.join(root, "mod.py")
            callers = impact_analysis._find_callers("HOOK", root, src)
            assert len(callers) == 0

    def test_import_asname(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._setup_project(tmp, {
                "lib.py": "def helper(): pass",
                "caller.py": "from lib import helper as hp\nhp()",
            })
            src = os.path.join(root, "lib.py")
            callers = impact_analysis._find_callers("helper", root, src)
            assert len(callers) == 1
            assert any(r["type"] == "import" for r in callers[0]["references"])

    def test_skips_function_def_self(self):
        """Name() node inside a FunctionDef that defines the function itself."""
        with tempfile.TemporaryDirectory() as tmp:
            root = self._setup_project(tmp, {
                "mod.py": "def duplicate(): pass",
                "other.py": "def duplicate(x): return x",
            })
            src = os.path.join(root, "mod.py")
            callers = impact_analysis._find_callers("duplicate", root, src)
            # other.py has a 'def duplicate' too — the Name node for 'duplicate'
            # in the FunctionDef header should NOT be counted as a usage.
            # But there IS an import-level detection from the name string…
            # Actually 'def duplicate' doesn't contain a Name node usage — it's a
            # FunctionDef node itself. So any Name node for 'duplicate' in other.py
            # is just the def itself, excluded by the FunctionDef check.
            assert len(callers) == 0


# ---------------------------------------------------------------------------
# _sync_impact
# ---------------------------------------------------------------------------

class TestSyncImpact:
    def test_non_existent_file_returns_error(self):
        result = impact_analysis._sync_impact("foo", "/tmp/_no_file_x.py", False)
        assert "[ERROR]" in result or "no es un archivo" in result

    def test_no_callers_shows_safe_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            fpath = _write_py(os.path.join(tmp, "lib.py"), "VERSION = 1")
            root = impact_analysis._find_project_root(fpath)
            with patch("src.paths.CONTEXT_DIR", root):
                result = impact_analysis._sync_impact("VERSION", fpath, False)
            assert "Sin dependencias externas" in result
            assert "cambio seguro" in result

    def test_with_callers_shows_risk(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, "project")
            os.makedirs(os.path.join(root, "src"))
            os.makedirs(os.path.join(root, "web"))
            src = _write_py(os.path.join(root, "mymod.py"), "def compute(a, b): return a + b")
            _write_py(os.path.join(root, "caller.py"), "from mymod import compute\ncompute(1, 2)")
            with patch("src.paths.CONTEXT_DIR", root):
                result = impact_analysis._sync_impact("compute", src, False)
            assert "IMPACT ANALYSIS" in result
            assert "compute" in result
            assert "caller.py" in result
            assert "RIESGO" in result

    def test_include_internal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, "project")
            os.makedirs(os.path.join(root, "src"))
            os.makedirs(os.path.join(root, "web"))
            src = _write_py(os.path.join(root, "mod.py"), """
def util():
    pass
def run():
    util()
""")
            with patch("src.paths.CONTEXT_DIR", root):
                result_ext = impact_analysis._sync_impact("util", src, include_internal=False)
            assert "Sin dependencias externas" in result_ext

            with patch("src.paths.CONTEXT_DIR", root):
                result_int = impact_analysis._sync_impact("util", src, include_internal=True)
            assert "Sin dependencias externas" not in result_int

    def test_signature_included_in_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, "project")
            os.makedirs(os.path.join(root, "src"))
            os.makedirs(os.path.join(root, "web"))
            src = _write_py(os.path.join(root, "greeter.py"), "def greet(name: str) -> str: return f'Hi {name}'")
            with patch("src.paths.CONTEXT_DIR", root):
                result = impact_analysis._sync_impact("greet", src, False)
            assert "Firma actual" in result
            assert "def greet(name)" in result

    def test_truncates_long_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, "project")
            os.makedirs(os.path.join(root, "src"))
            os.makedirs(os.path.join(root, "web"))
            src = _write_py(os.path.join(root, "big.py"), f"def big(): pass")
            for i in range(500):
                _write_py(os.path.join(root, f"caller_{i}.py"), f"from big import big\nbig()")
            with patch("src.paths.CONTEXT_DIR", root):
                result = impact_analysis._sync_impact("big", src, False)
            # Truncation at 30000 chars
            assert len(result) <= 30015  # 30000 + len("...[truncado]")
