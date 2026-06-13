"""Tests for filesystem tools: read_file, write_file, edit_file."""
import pytest
from pathlib import Path
from src.tools import read_file
from src.tools import write_file
from src.tools import edit_file


class TestReadFile:
    def test_definition_exists(self):
        assert "function" in read_file.DEFINITION
        assert read_file.DEFINITION["function"]["name"] == "read_file"

    def test_reads_file(self, tmp_path):
        path = tmp_path / "test.txt"
        path.write_text("hello world")
        result = read_file.run(path=str(path))
        assert "hello world" in result
        assert "File:" in result

    def test_file_not_found(self, tmp_path):
        path = tmp_path / "nonexistent.txt"
        result = read_file.run(path=str(path))
        assert result.startswith("[ERROR]")

    def test_directory_rejected(self, tmp_path):
        result = read_file.run(path=str(tmp_path))
        assert result.startswith("[ERROR]")

    def test_empty_file(self, tmp_path):
        path = tmp_path / "empty.txt"
        path.write_text("")
        result = read_file.run(path=str(path))
        assert "Total lines: 0" in result

    def test_pagination_caps_at_100_lines(self, tmp_path):
        path = tmp_path / "long.txt"
        path.write_text("\n".join(f"line{i}" for i in range(200)))
        result = read_file.run(path=str(path))
        assert "Displayed range: 1-100" in result
        assert "Output truncated" in result

    def test_start_end_line(self, tmp_path):
        path = tmp_path / "test.txt"
        path.write_text("a\nb\nc\nd\ne\n")
        result = read_file.run(path=str(path), start_line=2, end_line=4)
        assert "Displayed range: 2-4" in result
        assert "2: b" in result
        assert "4: d" in result

    def test_path_traversal_rejected(self, tmp_path):
        result = read_file.run(path=str(tmp_path / "../../../etc/passwd"))
        assert result.startswith("[ERROR]")

    def test_reads_absolute_path(self, tmp_path):
        path = tmp_path / "abs.txt"
        path.write_text("absolute")
        result = read_file.run(path=str(path))
        assert "absolute" in result


class TestWriteFile:
    def test_definition_exists(self):
        assert "function" in write_file.DEFINITION
        assert write_file.DEFINITION["function"]["name"] == "write_file"

    def test_writes_file(self, tmp_path):
        path = tmp_path / "test.txt"
        result = write_file.run(path=str(path), content="hello")
        assert path.read_text() == "hello"
        assert "[OK]" in result

    def test_creates_directories(self, tmp_path):
        path = tmp_path / "a" / "b" / "test.txt"
        result = write_file.run(path=str(path), content="deep")
        assert path.read_text() == "deep"
        assert "[OK]" in result

    def test_path_traversal_rejected(self):
        result = write_file.run(path="/etc/pwned", content="x")
        assert result.startswith("[ERROR]")

    def test_overwrites_existing_file(self, tmp_path):
        path = tmp_path / "overwrite.txt"
        path.write_text("old content")
        result = write_file.run(path=str(path), content="new content")
        assert path.read_text() == "new content"
        assert "[OK]" in result

    def test_writes_empty_content(self, tmp_path):
        path = tmp_path / "empty.txt"
        result = write_file.run(path=str(path), content="")
        assert path.read_text() == ""
        assert "[OK]" in result


class TestEditFile:
    def test_definition_exists(self):
        assert "function" in edit_file.DEFINITION
        assert edit_file.DEFINITION["function"]["name"] == "edit_file"

    def test_replaces_line_range(self, tmp_path):
        path = tmp_path / "test.txt"
        path.write_text("line one\nline two\nline three\n")
        result = edit_file.run(
            path=str(path), start_line=2, end_line=2,
            new_content="replaced two\n",
        )
        text = path.read_text()
        assert "replaced two" in text
        assert "line one" in text
        assert "line three" in text
        assert "Editado" in result

    def test_inserts_before_line(self, tmp_path):
        path = tmp_path / "test.txt"
        path.write_text("first\nlast\n")
        result = edit_file.run(
            path=str(path), start_line=2,
            new_content="middle\n",
        )
        assert path.read_text() == "first\nmiddle\nlast\n"
        assert "Editado" in result

    def test_deletes_line_range(self, tmp_path):
        path = tmp_path / "test.txt"
        path.write_text("keep\ndelete\nkeep\n")
        result = edit_file.run(
            path=str(path), start_line=2, end_line=2,
        )
        assert path.read_text() == "keep\nkeep\n"
        assert "Editado" in result

    def test_file_not_found(self, tmp_path):
        path = tmp_path / "nonexistent.txt"
        result = edit_file.run(path=str(path), start_line=1, new_content="x")
        assert result.startswith("[ERROR]")

    def test_no_operation_specified(self, tmp_path):
        path = tmp_path / "test.txt"
        path.write_text("content\n")
        result = edit_file.run(path=str(path), start_line=1)
        assert result.startswith("[ERROR]")

    def test_path_traversal_rejected(self):
        result = edit_file.run(
            path="/etc/pwned",
            start_line=1, new_content="x",
        )
        assert result.startswith("[ERROR]")
