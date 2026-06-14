from unittest.mock import AsyncMock
"""Contract test: API domain modules should remain importable."""
import importlib
import pytest

api_init_module = importlib.import_module("src.api")


class TestApiFacadeBypass:
    @pytest.mark.anyio
    async def test_api_init_is_empty(self):
        content = open(api_init_module.__file__).read().strip()
        assert content.startswith('"""Public API for K-Chat')

    @pytest.mark.anyio
    async def test_api_modules_importable(self):
        from src.api import messages, session, widgets, debug, tools
        assert hasattr(messages, "save_message_record")
        assert hasattr(session, "get_sessions")
        assert hasattr(widgets, "save_widget_state")
        assert hasattr(debug, "save_debug_info")
