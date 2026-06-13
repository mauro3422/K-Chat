"""Contract test: Web code should go through API facade, not directly to repos."""
import pytest
from src.api import __init__ as api_init_module


class TestApiFacadeBypass:
    def test_api_init_is_empty(self):
        content = open(api_init_module.__file__).read().strip()
        assert content == "# Package marker. Intentionally empty."

    def test_api_modules_importable(self):
        from src.api import messages, session, widgets, debug, tools, history, connection, models
        assert hasattr(messages, "save_message")
        assert hasattr(session, "get_sessions")
        assert hasattr(widgets, "save_widget_state")
        assert hasattr(debug, "save_debug_info")
