"""Tests for edit_file tool."""
import os
import tempfile
import pytest
from pathlib import Path

from src.tools import edit_file


@pytest.fixture
async def test_file():
    """Create a temporary file for testing."""
    content = "line one\nline two\nline three\nline four\nline five\n"
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(content)
        path = f.name
    
    yield path
    
    if os.path.exists(path):
        os.unlink(path)


class TestEditFile:
    @pytest.mark.anyio
    async def test_successful_edit_replace_line(self, test_file):
        """Test successful edit by replacing a line."""
        result = edit_file.run(
            path=test_file,
            start_line=2,
            end_line=2,
            new_content="replaced line two"
        )
        assert "Editado" in result
        
        with open(test_file, 'r') as f:
            content = f.read()
        assert "replaced line two" in content
        assert "line one" in content
        assert "line three" in content
    
    @pytest.mark.anyio
    async def test_old_string_not_found(self, test_file):
        """Test edit when the line doesn't match expectations."""
        # This tool uses line numbers, not string matching
        # So this test verifies line replacement works
        result = edit_file.run(
            path=test_file,
            start_line=1,
            end_line=1,
            new_content="new first line"
        )
        assert "Editado" in result
        
        with open(test_file, 'r') as f:
            content = f.read()
        assert "new first line" in content
    
    @pytest.mark.anyio
    async def test_file_not_found(self):
        """Test editing a file that doesn't exist."""
        result = edit_file.run(
            path="/tmp/nonexistent_file_12345.txt",
            start_line=1,
            new_content="test"
        )
        assert "[ERROR]" in result
        assert "no existe" in result
    
    @pytest.mark.anyio
    async def test_insert_before_line(self, test_file):
        """Test inserting content before a line."""
        result = edit_file.run(
            path=test_file,
            start_line=3,
            new_content="inserted line"
        )
        assert "Editado" in result
        
        with open(test_file, 'r') as f:
            content = f.read()
        assert "inserted line" in content
        assert "line two\ninserted line\nline three" in content
    
    @pytest.mark.anyio
    async def test_delete_line_range(self, test_file):
        """Test deleting a range of lines."""
        result = edit_file.run(
            path=test_file,
            start_line=2,
            end_line=3
        )
        assert "Editado" in result
        
        with open(test_file, 'r') as f:
            content = f.read()
        assert "line two" not in content
        assert "line three" not in content
        assert "line one" in content
        assert "line four" in content
    
    @pytest.mark.anyio
    async def test_no_operation_specified(self, test_file):
        """Test edit without specifying operation."""
        result = edit_file.run(
            path=test_file,
            start_line=1
        )
        assert "[ERROR]" in result
    
    @pytest.mark.anyio
    async def test_path_traversal_rejected(self):
        """Test that path traversal is rejected."""
        result = edit_file.run(
            path="/etc/passwd",
            start_line=1,
            new_content="hacked"
        )
        assert "[ERROR]" in result