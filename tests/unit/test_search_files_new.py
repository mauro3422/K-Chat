"""Tests for search_files tool."""
import os
import tempfile
import pytest
from pathlib import Path

from src.tools import search_files


@pytest.fixture
async def test_directory():
    """Create a temporary directory with test files."""
    temp_dir = tempfile.mkdtemp()
    
    py_file = os.path.join(temp_dir, "test_module.py")
    with open(py_file, 'w') as f:
        f.write("def hello():\n    print('Hello')\n    return 'world'\n")
    
    js_file = os.path.join(temp_dir, "test_script.js")
    with open(js_file, 'w') as f:
        f.write("function hello() {\n    console.log('Hello');\n    return 'world';\n}\n")
    
    txt_file = os.path.join(temp_dir, "readme.txt")
    with open(txt_file, 'w') as f:
        f.write("This is a test file.\nAnother line with hello.\nFinal line.\n")
    
    sub_dir = os.path.join(temp_dir, "subdir")
    os.makedirs(sub_dir)
    sub_file = os.path.join(sub_dir, "nested.py")
    with open(sub_file, 'w') as f:
        f.write("def nested_func():\n    pass\n")
    
    yield temp_dir
    
    import shutil
    shutil.rmtree(temp_dir)


class TestSearchFiles:
    @pytest.mark.anyio
    async def test_pattern_match(self, test_directory):
        result = await search_files.run(pattern="hello", path=test_directory)
        assert "hello" in result.lower()
        assert "match" in result.lower() or "coincidencia" in result.lower()
    
    @pytest.mark.anyio
    async def test_no_matches(self, test_directory):
        result = await search_files.run(pattern="xyznonexistent123", path=test_directory)
        assert "Sin coincidencias" in result or "sin coincidencias" in result
    
    @pytest.mark.anyio
    async def test_include_filter(self, test_directory):
        result = await search_files.run(
            pattern="hello",
            path=test_directory,
            file_pattern="*.py"
        )
        assert "hello" in result.lower()
    
    @pytest.mark.anyio
    async def test_path_not_found(self):
        result = await search_files.run(
            pattern="test",
            path="/tmp/nonexistent_directory_12345"
        )
        assert "[ERROR]" in result
        assert "no existe" in result
    
    @pytest.mark.anyio
    async def test_case_sensitive_search(self, test_directory):
        result_sensitive = await search_files.run(
            pattern="Hello",
            path=test_directory,
            case_sensitive=True
        )
        result_insensitive = await search_files.run(
            pattern="hello",
            path=test_directory,
            case_sensitive=False
        )
        assert "Hello" in result_sensitive or "match" in result_sensitive.lower()
    
    @pytest.mark.anyio
    async def test_empty_pattern(self, test_directory):
        result = await search_files.run(pattern="", path=test_directory)
        assert "[ERROR]" in result
    
    @pytest.mark.anyio
    async def test_context_lines(self, test_directory):
        result = await search_files.run(
            pattern="Hello",
            path=test_directory,
            context_lines=3
        )
        assert "Hello" in result
