import pytest
from unittest.mock import AsyncMock
from src.core.history_ui import match_tools_to_msgs as _match_tools_to_msgs

@pytest.mark.anyio
async def test_match_tools_to_msgs_empty():
    """Test matching with empty lists."""
    assert _match_tools_to_msgs([], []) == {}

@pytest.mark.anyio
async def test_match_tools_to_msgs_basic():
    """Test matching tool calls to assistant messages chronologically."""
    msgs = [
        {"role": "user", "content": "Hello", "created_at": 10},
        {"role": "assistant", "content": "Hi there", "created_at": 20},
        {"role": "user", "content": "Do search", "created_at": 30},
        {"role": "assistant", "content": "Here is search result", "created_at": 50},
    ]
    all_tools = [
        {"tool_name": "web_search", "input": "query1", "status": "ok", "created_at": 15, "turn": 1},
        {"tool_name": "web_search", "input": "query2", "status": "ok", "created_at": 40, "turn": 1},
        {"tool_name": "save_memory", "input": "mem1", "status": "ok", "created_at": 45, "turn": 1},
    ]

    matched = _match_tools_to_msgs(msgs, all_tools)

    # Message at ts=20 should match tools <= 20 (only tool at created_at=15)
    assert len(matched[20]) == 1
    assert matched[20][0]["tool_name"] == "web_search"
    assert matched[20][0]["input"] == "query1"

    # Message at ts=50 should match tools <= 50 that weren't matched before (created_at=40, 45)
    assert len(matched[50]) == 2
    assert matched[50][0]["input"] == "query2"
    assert matched[50][1]["input"] == "mem1"
