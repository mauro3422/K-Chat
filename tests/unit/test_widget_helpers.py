import pytest
from unittest.mock import AsyncMock
from src.tools._widget_helpers import sanitize_widget_id, validate_widget_args


@pytest.mark.anyio
async def test_sanitize_id_removes_special_chars():
    assert sanitize_widget_id("hello!@#world") == "helloworld"


@pytest.mark.anyio
async def test_sanitize_id_allows_alphanumeric():
    assert sanitize_widget_id("ABC123") == "abc123"


@pytest.mark.anyio
async def test_sanitize_id_handles_empty():
    assert sanitize_widget_id("") == ""


@pytest.mark.anyio
async def test_sanitize_id_preserves_hyphen():
    assert sanitize_widget_id("hello-world") == "hello-world"


@pytest.mark.anyio
async def test_sanitize_id_allows_hyphen_and_underscore():
    assert sanitize_widget_id("my-widget_v2") == "my-widget_v2"


@pytest.mark.anyio
async def test_sanitize_id_strips_whitespace():
    assert sanitize_widget_id("  foo  ") == "foo"


@pytest.mark.anyio
async def test_sanitize_id_only_special_chars():
    assert sanitize_widget_id("!@#$%") == ""


@pytest.mark.anyio
async def test_sanitize_id_mixed_case():
    assert sanitize_widget_id("MyCoolWidget") == "mycoolwidget"


@pytest.mark.anyio
async def test_validate_args_missing_session_id():
    result = validate_widget_args(None, "my_widget")
    assert isinstance(result, str)
    assert "session_id" in result


@pytest.mark.anyio
async def test_validate_args_invalid_widget_id():
    result = validate_widget_args("sess-123", "!@#$")
    assert isinstance(result, str)
    assert "Invalid widget" in result


@pytest.mark.anyio
async def test_validate_args_success():
    result = validate_widget_args("sess-123", "MyWidget")
    assert isinstance(result, tuple)
    session_id, clean_id = result
    assert session_id == "sess-123"
    assert clean_id == "mywidget"


@pytest.mark.anyio
async def test_validate_args_empty_session_id():
    result = validate_widget_args("", "my_widget")
    assert isinstance(result, str)
    assert "session_id" in result
