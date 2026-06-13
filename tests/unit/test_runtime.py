import os
from unittest.mock import patch, MagicMock, mock_open


def test_build_context_snapshot_reads_files():
    from src.context.runtime import build_context_snapshot, invalidate_context_cache, CONTEXT_DIR

    invalidate_context_cache()

    soul_path = os.path.join(CONTEXT_DIR, "SOUL.md")
    memory_path = os.path.join(CONTEXT_DIR, "MEMORY.md")
    agents_path = os.path.join(CONTEXT_DIR, "AGENTS.md")

    read_map = {
        soul_path: "# Soul content",
        memory_path: "# Memory content",
        agents_path: "# Agents content",
    }

    with patch("src.context.runtime._ensure_file"):
        with patch("src.context.runtime._read_file", side_effect=lambda p: read_map.get(p, "")):
            with patch("src.context.runtime._build_rules_files"):
                with patch("src.context.runtime._build_tools_md", return_value="# Tools md content"):
                    with patch("builtins.open", mock_open()) as mock_file:
                        result = build_context_snapshot()

                        assert result.text == "# Soul content\n\n# Memory content\n\n# Agents content"
                        assert result.tools_md == "# Tools md content"
                        assert mock_file().write.call_args[0][0] == "# Tools md content"


def test_build_context_snapshot_uses_cache():
    from src.context.runtime import build_context_snapshot, invalidate_context_cache

    invalidate_context_cache()

    with patch("src.context.runtime._ensure_file"):
        with patch("src.context.runtime._read_file", return_value="# content"):
            with patch("src.context.runtime._build_rules_files"):
                with patch("src.context.runtime._build_tools_md", return_value="# Tools md"):
                    with patch("builtins.open", mock_open()) as mock_file:
                        result1 = build_context_snapshot()
                        assert result1.text == "# content\n\n# content\n\n# content"

                        mock_file().write.reset_mock()

                        result2 = build_context_snapshot()
                        assert result2.text == result1.text
                        assert result2.tools_md == result1.tools_md
                        mock_file().write.assert_not_called()


def test_build_context_snapshot_force_bypasses_cache():
    from src.context.runtime import build_context_snapshot, invalidate_context_cache

    invalidate_context_cache()

    with patch("src.context.runtime._ensure_file"):
        with patch("src.context.runtime._read_file", return_value="# content"):
            with patch("src.context.runtime._build_rules_files"):
                with patch("src.context.runtime._build_tools_md", return_value="# Tools md"):
                    with patch("builtins.open", mock_open()) as mock_file:
                        result1 = build_context_snapshot()
                        mock_file().write.assert_called_once()

                        mock_file().write.reset_mock()

                        result2 = build_context_snapshot(force=True)
                        assert result2.text == result1.text
                        assert result2.tools_md == result1.tools_md
                        mock_file().write.assert_called_once()


def test_invalidate_context_cache():
    from src.context.runtime import invalidate_context_cache, build_context_snapshot

    invalidate_context_cache()

    with patch("src.context.runtime._ensure_file"):
        with patch("src.context.runtime._read_file", return_value="# content"):
            with patch("src.context.runtime._build_rules_files"):
                with patch("src.context.runtime._build_tools_md", return_value="# Tools md"):
                    with patch("builtins.open", mock_open()) as mock_file:
                        result1 = build_context_snapshot()
                        mock_file().write.assert_called_once()

                        invalidate_context_cache()

                        mock_file().write.reset_mock()
                        result2 = build_context_snapshot()
                        mock_file().write.assert_called_once()


def test_write_if_changed_writes_when_different():
    from src.context.runtime import _write_if_changed

    with patch("src.context.runtime._read_file", return_value="current"):
        with patch("builtins.open", mock_open()) as mock_file:
            _write_if_changed("/tmp/test.md", "new")
            mock_file().write.assert_called_once_with("new")


def test_write_if_changed_skips_when_same():
    from src.context.runtime import _write_if_changed

    with patch("src.context.runtime._read_file", return_value="same"):
        with patch("builtins.open") as mock_file:
            _write_if_changed("/tmp/test.md", "same")
            mock_file.assert_not_called()


def test_context_snapshot_dataclass():
    from src.context.runtime import ContextSnapshot

    snapshot = ContextSnapshot(text="test text", tools_md="test tools")
    assert snapshot.text == "test text"
    assert snapshot.tools_md == "test tools"
