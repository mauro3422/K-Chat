"""Tests for WebSocket event emission from the Telegram adapter.

Verifies that process_message() calls ws_client.send_event() at the
correct flush points during streaming.
"""

from unittest.mock import AsyncMock, patch, MagicMock
import pytest


@pytest.fixture
def mock_ws_client():
    """Mock the WS client singleton so send_event is a MagicMock."""
    with patch("channels.telegram.adapter.get_ws_client") as mock:
        client = MagicMock()
        client.send_event = AsyncMock()
        mock.return_value = client
        yield client


@pytest.fixture
def mock_lazy_imports():
    """Create a minimal _LazyImports substitute with a mock chat_stream."""
    li = MagicMock()
    
    mock_sessions = AsyncMock()
    mock_sessions.find_by_telegram_chat_id.return_value = "tele-12345"
    mock_sessions.ensure = AsyncMock()
    mock_sessions.update_telegram_chat_id = AsyncMock()
    
    mock_messages = AsyncMock()
    mock_messages.get_session_messages.return_value = []
    
    repos = MagicMock()
    repos.sessions = mock_sessions
    repos.messages = mock_messages
    
    li.get_repos.return_value = repos
    li.get_default_model.return_value = "test-model"

    async def dummy_stream(**kwargs):
        # Yield a sequence of events simulating a full assistant response
        # phase 1: reasoning
        for token in "First", " second", " reasoning":
            yield "reasoning", token
        # tool call
        yield "tool_call", '{"name": "read_file", "id": "call_1", "status": "calling"}'
        # tool result
        yield "tool_call", '{"name": "read_file", "id": "call_1", "status": "ok"}'
        # phase 2: more reasoning
        for token in "More", " reasoning":
            yield "reasoning", token
        # phase 3: content
        for token in "Final", " content":
            yield "content", token

    li.chat_stream = dummy_stream
    with patch("channels.telegram.adapter._LazyImports", return_value=li):
        yield li


@pytest.mark.asyncio
async def test_send_event_called_for_reasoning(mock_ws_client, mock_lazy_imports):
    """First reasoning token should trigger send_event for stream:reasoning."""
    from channels.telegram.adapter import process_message

    async for _ in process_message("test input", 12345, MagicMock()):
        pass

    # Should have called send_event at least once with stream:reasoning
    reasoning_calls = [
        call for call in mock_ws_client.send_event.call_args_list
        if call[0][0] == "stream:reasoning"
    ]
    assert len(reasoning_calls) >= 1, (
        "send_event was never called with stream:reasoning"
    )
    # The first call should contain the session_id
    first_reasoning = reasoning_calls[0]
    assert "session_id" in first_reasoning[0][1]


@pytest.mark.asyncio
async def test_send_event_called_for_content(mock_ws_client, mock_lazy_imports):
    """Content tokens should trigger send_event for stream:content."""
    from channels.telegram.adapter import process_message

    async for _ in process_message("test input", 12345, MagicMock()):
        pass

    content_calls = [
        call for call in mock_ws_client.send_event.call_args_list
        if call[0][0] == "stream:content"
    ]
    assert len(content_calls) >= 1, (
        "send_event was never called with stream:content"
    )


@pytest.mark.asyncio
async def test_send_event_called_for_tool_call(mock_ws_client, mock_lazy_imports):
    """Tool calls should trigger send_event for stream:tool."""
    from channels.telegram.adapter import process_message

    async for _ in process_message("test input", 12345, MagicMock()):
        pass

    tool_calls = [
        call for call in mock_ws_client.send_event.call_args_list
        if call[0][0] == "stream:tool"
    ]
    assert len(tool_calls) >= 1, (
        "send_event was never called with stream:tool"
    )
    # Verify tool_name is included
    first_tool = tool_calls[0]
    assert "tool_name" in first_tool[0][1]
    assert first_tool[0][1]["tool_name"] == "read_file"


@pytest.mark.asyncio
async def test_send_event_contains_session_id(mock_ws_client, mock_lazy_imports):
    """Every send_event call must include session_id."""
    from channels.telegram.adapter import process_message

    async for _ in process_message("test input", 12345, MagicMock()):
        pass

    for call_args in mock_ws_client.send_event.call_args_list:
        event_data = call_args[0][1]
        assert "session_id" in event_data, (
            f"send_event({call_args[0][0]}) missing session_id"
        )


@pytest.mark.asyncio
async def test_send_event_not_called_for_heartbeat(mock_ws_client, mock_lazy_imports):
    """Heartbeat events should NOT trigger send_event."""
    async def heartbeat_stream(**kwargs):
        yield "heartbeat", ""

    mock_lazy_imports.chat_stream = heartbeat_stream

    from channels.telegram.adapter import process_message
    async for _ in process_message("test", 12345, MagicMock()):
        pass

    mock_ws_client.send_event.assert_not_called()


@pytest.mark.asyncio
async def test_reasoning_flush_interval_respected(mock_ws_client, mock_lazy_imports):
    """send_event should be called at reasoning_flush_interval boundaries."""
    reasoning_tokens = [f"token_{i}" for i in range(25)]  # 25 tokens, flush at 5

    async def reasoning_stream(**kwargs):
        for t in reasoning_tokens:
            yield "reasoning", t

    mock_lazy_imports.chat_stream = reasoning_stream

    from channels.telegram.adapter import process_message
    async for _ in process_message("test", 12345, MagicMock()):
        pass

    reasoning_calls = [
        call for call in mock_ws_client.send_event.call_args_list
        if call[0][0] == "stream:reasoning"
    ]
    # With flush_interval=5 and 25 tokens, expect flush at 1, 5, 10, 15, 20, 25 = 6 calls
    assert len(reasoning_calls) >= 4, (
        f"Expected ~5 reasoning flushes, got {len(reasoning_calls)}"
    )
