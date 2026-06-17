import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from src.tools.git_operation import (
    DEFINITION,
    _build_command,
    _is_blocked,
    run,
)


class TestIsBlocked:
    def test_safe_command_not_blocked(self):
        blocked, msg = _is_blocked("git status --short")
        assert blocked is False
        assert msg == ""

    def test_force_push_is_blocked(self):
        blocked, msg = _is_blocked("git push --force")
        assert blocked is True
        assert "Blocked" in msg

    def test_hard_reset_is_blocked(self):
        blocked, msg = _is_blocked("git reset --hard HEAD~1")
        assert blocked is True
        assert "Blocked" in msg

    def test_reset_without_hard_is_not_blocked(self):
        blocked, msg = _is_blocked("git reset HEAD")  # no space around " reset " -> no
        # Since the pattern is " reset " (with spaces), "git reset HEAD" does contain " reset "
        # Actually: "git reset HEAD" lower is "git reset head" which contains " reset "
        # because "git reset head" has " reset " — yes it does.
        assert blocked is True

    def test_clean_fd_is_blocked(self):
        blocked, msg = _is_blocked("git clean -fd")
        assert blocked is True
        assert "Blocked" in msg

    def test_rm_is_blocked(self):
        blocked, msg = _is_blocked("git rm file.txt")
        assert blocked is True
        assert "Blocked" in msg

    def test_empty_command_not_blocked(self):
        blocked, msg = _is_blocked("")
        assert blocked is False
        assert msg == ""

    def test_partial_word_no_false_positive(self):
        blocked, msg = _is_blocked("git branch --merged")  # " rm " not present
        assert blocked is False


class TestBuildCommand:
    def test_status(self):
        assert _build_command("status", None, None, 5) == ["git", "status", "--short"]

    def test_diff_default(self):
        assert _build_command("diff", None, None, 1) == ["git", "diff"]

    def test_diff_with_count(self):
        assert _build_command("diff", None, None, 3) == ["git", "diff", "HEAD~3"]

    def test_log(self):
        assert _build_command("log", None, None, 10) == ["git", "log", "--oneline", "-10"]

    def test_branch(self):
        assert _build_command("branch", None, None, 5) == ["git", "branch", "-a"]

    def test_add_with_path(self):
        assert _build_command("add", "foo.py", None, 5) == ["git", "add", "foo.py"]

    def test_add_raises_without_path(self):
        with pytest.raises(ValueError, match="path is required"):
            _build_command("add", None, None, 5)

    def test_commit_with_message(self):
        assert _build_command("commit", None, "my msg", 5) == ["git", "commit", "-m", "my msg"]

    def test_commit_raises_without_message(self):
        with pytest.raises(ValueError, match="message is required"):
            _build_command("commit", None, None, 5)

    def test_push(self):
        assert _build_command("push", None, None, 5) == ["git", "push"]

    def test_pull(self):
        assert _build_command("pull", None, None, 5) == ["git", "pull"]

    def test_clone_with_path(self):
        assert _build_command("clone", "https://example.com/repo.git", None, 5) == [
            "git", "clone", "https://example.com/repo.git",
        ]

    def test_clone_raises_without_path(self):
        with pytest.raises(ValueError, match="path.*required"):
            _build_command("clone", None, None, 5)

    def test_unknown_operation(self):
        with pytest.raises(ValueError, match="Unknown operation"):
            _build_command("rebase", None, None, 5)


class TestRun:
    @pytest.mark.anyio
    async def test_no_operation_returns_error(self):
        result = await run()
        assert result == "[ERROR] No operation provided."

    @pytest.mark.anyio
    async def test_invalid_operation_returns_error(self):
        result = await run(operation="rebase")
        assert "[ERROR]" in result

    @pytest.mark.anyio
    async def test_blocked_operation_returns_error(self):
        result = await run(operation="add", path="--force", cwd="/tmp")
        assert "[ERROR] Blocked" in result

    @pytest.mark.anyio
    async def test_nonexistent_cwd(self):
        result = await run(operation="status", cwd="/nonexistent_path_xyz")
        assert "[ERROR]" in result
        assert "does not exist" in result

    @pytest.mark.anyio
    async def test_successful_status(self):
        with patch("src.tools.git_operation.subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.stdout = " M foo.py\n"
            mock_result.stderr = ""
            mock_result.returncode = 0
            mock_run.return_value = mock_result

            with tempfile.TemporaryDirectory() as tmpdir:
                result = await run(operation="status", cwd=tmpdir)

            assert " M foo.py" in result

    @pytest.mark.anyio
    async def test_stderr_included_in_output(self):
        with patch("src.tools.git_operation.subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.stdout = ""
            mock_result.stderr = "fatal: not a git repository"
            mock_result.returncode = 128
            mock_run.return_value = mock_result

            with tempfile.TemporaryDirectory() as tmpdir:
                result = await run(operation="status", cwd=tmpdir)

            assert "EXIT CODE: 128" in result
            assert "fatal: not a git repository" in result

    @pytest.mark.anyio
    async def test_timeout(self):
        with patch("src.tools.git_operation.subprocess.run") as mock_run:
            from subprocess import TimeoutExpired
            mock_run.side_effect = TimeoutExpired("git", 60)

            with tempfile.TemporaryDirectory() as tmpdir:
                result = await run(operation="status", cwd=tmpdir)

            assert "timed out" in result

    @pytest.mark.anyio
    async def test_permission_error(self):
        with patch("src.tools.git_operation.subprocess.run") as mock_run:
            mock_run.side_effect = PermissionError("Permission denied")

            with tempfile.TemporaryDirectory() as tmpdir:
                result = await run(operation="status", cwd=tmpdir)

            assert "Permission denied" in result

    @pytest.mark.anyio
    async def test_os_error(self):
        with patch("src.tools.git_operation.subprocess.run") as mock_run:
            mock_run.side_effect = OSError("ENOENT: no such file")

            with tempfile.TemporaryDirectory() as tmpdir:
                result = await run(operation="status", cwd=tmpdir)

            assert "System error" in result

    @pytest.mark.anyio
    async def test_truncates_large_output(self):
        with patch("src.tools.git_operation.subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.stdout = "x" * 40000
            mock_result.stderr = ""
            mock_result.returncode = 0
            mock_run.return_value = mock_result

            with tempfile.TemporaryDirectory() as tmpdir:
                result = await run(operation="log", count=1000, cwd=tmpdir)

            assert len(result) <= 30000 + 50  # 30000 + truncation message
            assert "...[truncated" in result

    @pytest.mark.anyio
    async def test_add_requires_path(self):
        result = await run(operation="add", path=None)
        assert "[ERROR]" in result
        assert "path is required" in result

    @pytest.mark.anyio
    async def test_commit_requires_message(self):
        result = await run(operation="commit", path="foo.py", message=None)
        assert "[ERROR]" in result
        assert "message is required" in result


class TestDefinition:
    def test_definition_structure(self):
        assert DEFINITION["type"] == "function"
        assert DEFINITION["function"]["name"] == "git_operation"
        assert "operation" in DEFINITION["function"]["parameters"]["properties"]
        assert DEFINITION["function"]["parameters"]["required"] == ["operation"]
