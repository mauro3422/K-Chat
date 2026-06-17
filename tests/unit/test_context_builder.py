import pytest
from unittest.mock import MagicMock, patch

from src.context.builder import build_system_prompt


@pytest.fixture
def mock_context_snapshot():
    with patch("src.context.builder.build_context_snapshot") as mock:
        snap = MagicMock()
        snap.text = "SOUL.md content\n\nMEMORY.md content\n\nAGENTS.md content"
        mock.return_value = snap
        yield


class TestBuildSystemPrompt:
    def test_build_system_prompt_without_memory(self, mock_context_snapshot):
        result = build_system_prompt(model="test-model")
        assert "AUTO-RETRIEVED MEMORIES" not in result["content"]
        assert result["role"] == "system"

    def test_build_system_prompt_with_memory(self, mock_context_snapshot):
        result = build_system_prompt(model="test-model", memory_results="test block")
        assert "━━━ AUTO-RETRIEVED MEMORIES ━━━" in result["content"]
        assert "test block" in result["content"]
        assert "━━━ END AUTO-RETRIEVED MEMORIES ━━━" in result["content"]

    def test_build_system_prompt_memory_empty_string(self, mock_context_snapshot):
        result = build_system_prompt(model="test-model", memory_results="")
        assert "AUTO-RETRIEVED MEMORIES" not in result["content"]

    def test_build_system_prompt_output_structure(self, mock_context_snapshot):
        result = build_system_prompt(model="test-model")
        assert result["role"] == "system"
        assert isinstance(result["content"], str)
        assert result["content"].startswith("[CRITICAL")

    def test_build_system_prompt_identity_and_model(self, mock_context_snapshot):
        result = build_system_prompt(model="gpt-4-test")
        assert "Kairos" in result["content"]
        assert "gpt-4-test" in result["content"]
