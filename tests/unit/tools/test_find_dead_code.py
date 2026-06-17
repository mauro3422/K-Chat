import ast
import os

import pytest

from src.tools.find_dead_code import (
    _extract_top_level_definitions,
    _check_name_used,
    _build_name_index,
    _analyze_file,
    _quick_search,
    DEFINITION,
    run as find_dead_code_run,
)


class TestExtractTopLevelDefinitions:
    def test_function(self, tmp_path):
        p = tmp_path / "mod.py"
        p.write_text("def foo(): pass\n")
        defs = _extract_top_level_definitions(str(p))
        assert "foo" in defs
        assert defs["foo"]["type"] == "function"

    def test_async_function(self, tmp_path):
        p = tmp_path / "mod.py"
        p.write_text("async def fetch(): pass\n")
        defs = _extract_top_level_definitions(str(p))
        assert "fetch" in defs
        assert defs["fetch"]["is_async"] is True

    def test_class_with_methods(self, tmp_path):
        p = tmp_path / "mod.py"
        p.write_text("class MyClass:\n    def method_a(self): pass\n    async def method_b(self): pass\n")
        defs = _extract_top_level_definitions(str(p))
        assert "MyClass" in defs
        assert defs["MyClass"]["type"] == "class"
        assert "method_a" in defs["MyClass"]["methods"]
        assert "method_b" in defs["MyClass"]["methods"]

    def test_module_variable(self, tmp_path):
        p = tmp_path / "mod.py"
        p.write_text("CONFIG = {}\nVERSION = '1.0'\n")
        defs = _extract_top_level_definitions(str(p))
        assert defs["CONFIG"]["type"] == "variable"
        assert defs["VERSION"]["type"] == "variable"

    def test_dunder_skipped(self, tmp_path):
        p = tmp_path / "mod.py"
        p.write_text("def __init__(): pass\n__all__ = ['x']\n")
        defs = _extract_top_level_definitions(str(p))
        assert "__init__" in defs
        assert "__all__" in defs

    def test_syntax_error_returns_empty(self, tmp_path):
        p = tmp_path / "bad.py"
        p.write_text("def foo(\n")
        assert _extract_top_level_definitions(str(p)) == {}

    def test_empty_file(self, tmp_path):
        p = tmp_path / "empty.py"
        p.write_text("")
        assert _extract_top_level_definitions(str(p)) == {}

    def test_missing_file(self):
        assert _extract_top_level_definitions("/no/file.py") == {}


class TestCheckNameUsed:
    def test_name_used_in_expression(self):
        tree = ast.parse("import os\nprint(os)\n")
        assert _check_name_used("os", tree, 1) is True

    def test_name_used_in_attribute(self):
        tree = ast.parse("import pathlib\npathlib.Path('/tmp')\n")
        assert _check_name_used("pathlib", tree, 1) is True

    def test_name_not_used(self):
        tree = ast.parse("import os\nx = 1\n")
        assert _check_name_used("os", tree, 1) is False

    def test_only_import_line(self):
        tree = ast.parse("import os\n")
        assert _check_name_used("os", tree, 1) is False


class TestBuildNameIndex:
    def test_basic(self, tmp_path):
        (tmp_path / "a.py").write_text("x = 1\n")
        (tmp_path / "b.py").write_text("y = x\n")
        index = _build_name_index(str(tmp_path))
        assert "x" in index
        assert "y" in index

    def test_import_names_indexed(self, tmp_path):
        (tmp_path / "a.py").write_text("import os\nimport sys as system\n")
        index = _build_name_index(str(tmp_path))
        assert "os" in index
        assert "system" in index

    def test_import_from_names(self, tmp_path):
        (tmp_path / "a.py").write_text("from pathlib import Path\n")
        index = _build_name_index(str(tmp_path))
        assert "Path" in index

    def test_syntax_error_skipped(self, tmp_path):
        (tmp_path / "good.py").write_text("x = 1\n")
        (tmp_path / "bad.py").write_text("def foo(\n")
        index = _build_name_index(str(tmp_path))
        assert "x" in index

    def test_skips_node_modules(self, tmp_path):
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "stuff.py").write_text("secret = True\n")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "mod.py").write_text("x = 1\n")
        index = _build_name_index(str(tmp_path))
        assert "secret" not in index


class TestAnalyzeFile:
    @pytest.fixture
    def proot(self, tmp_path):
        (tmp_path / "src" / "tools").mkdir(parents=True)
        return tmp_path

    def test_dead_function_detected(self, proot):
        f = proot / "src" / "tools" / "mod.py"
        f.write_text("def unused_func(): pass\n")
        index = _build_name_index(str(proot))
        r = _analyze_file(str(f), str(proot), index)
        assert any(d["name"] == "unused_func" for d in r["dead_code"])

    def test_function_used_elsewhere_not_dead(self, proot):
        f = proot / "src" / "tools" / "mod.py"
        f.write_text("def helper(): pass\n")
        (proot / "src" / "tools" / "consumer.py").write_text("from mod import helper\nhelper()\n")
        index = _build_name_index(str(proot))
        r = _analyze_file(str(f), str(proot), index)
        assert not any(d["name"] == "helper" for d in r["dead_code"])

    def test_unused_import_detected(self, proot):
        f = proot / "src" / "tools" / "mod.py"
        f.write_text("import os\nx = 1\n")
        index = _build_name_index(str(proot))
        r = _analyze_file(str(f), str(proot), index, dead_imports=True)
        assert len(r["unused_imports"]) >= 1

    def test_unused_imports_skipped_when_flag_off(self, proot):
        f = proot / "src" / "tools" / "mod.py"
        f.write_text("import os\nx = 1\n")
        index = _build_name_index(str(proot))
        r = _analyze_file(str(f), str(proot), index, dead_imports=False)
        assert r["unused_imports"] == []

    def test_dunder_not_reported_as_dead(self, proot):
        f = proot / "src" / "tools" / "mod.py"
        f.write_text("def __str__(): return ''\n")
        index = _build_name_index(str(proot))
        r = _analyze_file(str(f), str(proot), index)
        assert not any(d["name"] == "__str__" for d in r["dead_code"])

    def test_empty_file(self, proot):
        f = proot / "src" / "tools" / "empty.py"
        f.write_text("")
        index = _build_name_index(str(proot))
        r = _analyze_file(str(f), str(proot), index)
        assert r["dead_code"] == []
        assert r["unused_imports"] == []

    def test_syntax_error_file(self, proot):
        f = proot / "src" / "tools" / "bad.py"
        f.write_text("def foo(\n")
        index = _build_name_index(str(proot))
        r = _analyze_file(str(f), str(proot), index)
        assert r["definitions"] == {}
        assert r["unused_imports"] == []


class TestQuickSearch:
    def test_name_found(self, tmp_path):
        (tmp_path / "a.py").write_text("target_func = 1\n")
        exclude = tmp_path / "other.py"
        exclude.write_text("")
        assert _quick_search(str(tmp_path), "target_func", str(exclude)) is True

    def test_name_not_found(self, tmp_path):
        (tmp_path / "a.py").write_text("x = 1\n")
        exclude = tmp_path / "other.py"
        exclude.write_text("")
        assert _quick_search(str(tmp_path), "missing", str(exclude)) is False

    def test_exclude_file_skipped(self, tmp_path):
        f = tmp_path / "mod.py"
        f.write_text("unique_thing = 42\n")
        assert _quick_search(str(tmp_path), "unique_thing", str(f)) is False

    def test_no_py_files(self, tmp_path):
        exclude = tmp_path / "exclude.py"
        exclude.write_text("")
        assert _quick_search(str(tmp_path), "anything", str(exclude)) is False


@pytest.mark.anyio
class TestRun:
    @pytest.fixture
    def proot(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "web").mkdir()
        return tmp_path

    async def test_requires_path(self):
        r = await find_dead_code_run()
        assert "Proporciona una ruta" in r

    async def test_basic_dead_code(self, proot):
        f = proot / "src" / "mod.py"
        f.write_text("def dead(): pass\n")
        r = await find_dead_code_run(path=str(f))
        assert "DEAD CODE ANALYSIS" in r
        assert "dead" in r

    async def test_exclude_tests_filter(self, proot):
        (proot / "src" / "mod.py").write_text("def live(): pass\n")
        (proot / "src" / "test_mod.py").write_text("def test_thing(): pass\n")
        r = await find_dead_code_run(path=str(proot / "src"), exclude_tests=True)
        assert "test_mod.py" not in r

    async def test_dead_imports_flag(self, proot):
        f = proot / "src" / "mod.py"
        f.write_text("import os\nx = 1\n")
        r = await find_dead_code_run(path=str(f), dead_imports=True)
        assert "unused import" in r

        r2 = await find_dead_code_run(path=str(f), dead_imports=False)
        assert "unused import" not in r2

    async def test_quick_mode(self, proot):
        f = proot / "src" / "mod.py"
        f.write_text("def unreferenced(): pass\n")
        r = await find_dead_code_run(path=str(f), quick=True)
        assert "DEAD CODE ANALYSIS" in r
        assert "unreferenced" in r

    async def test_variable_is_dead_code(self, proot):
        f = proot / "src" / "mod.py"
        f.write_text("x = 1\n")
        r = await find_dead_code_run(path=str(f))
        assert "DEAD CODE ANALYSIS" in r
        assert "x" in r

    async def test_definition_fixture(self):
        assert DEFINITION["function"]["name"] == "find_dead_code"
