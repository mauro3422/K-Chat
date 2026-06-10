import json
import re

from src.api import save_message
from src.core.history import rebuild_history
from src.memory.database import init_db


def test_rebuild_history_empty_session():
    init_db()
    session_id = "test-empty-session"
    result = rebuild_history(session_id, "test-model")
    assert len(result) == 1
    assert result[0]["role"] == "system"
    assert "test-model" in result[0]["content"]


def test_rebuild_history_simple():
    init_db()
    session_id = "test-simple"
    save_message(session_id=session_id, role="user", content="Hello", model="test-model")
    save_message(session_id=session_id, role="assistant", content="Hi there!", model="test-model")
    result = rebuild_history(session_id, "test-model")
    assert len(result) == 3
    assert result[0]["role"] == "system"
    assert result[1]["role"] == "user"
    assert re.match(r"\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\] Hello", result[1]["content"])
    assert result[2]["role"] == "assistant"
    assert re.match(r"\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\] Hi there!", result[2]["content"])


def test_rebuild_history_tool_calls_with_responses():
    init_db()
    session_id = "test-tool-with-response"
    tool_calls_json = json.dumps([
        {"id": "call_weather", "type": "function", "function": {"name": "get_weather", "arguments": "{}"}},
        {"id": "call_time", "type": "function", "function": {"name": "get_time", "arguments": "{}"}},
    ])
    save_message(session_id=session_id, role="assistant", content="", model="test-model", tool_calls=tool_calls_json)
    save_message(session_id=session_id, role="tool", content='{"temp": 22}', model="test-model", tool_call_id="call_weather")
    save_message(session_id=session_id, role="tool", content='{"time": "12:00"}', model="test-model", tool_call_id="call_time")
    result = rebuild_history(session_id, "test-model")
    assert len(result) == 4
    assert result[0]["role"] == "system"
    assert result[1]["role"] == "assistant"
    assert result[1]["tool_calls"] == [
        {"id": "call_weather", "type": "function", "function": {"name": "get_weather", "arguments": "{}"}},
        {"id": "call_time", "type": "function", "function": {"name": "get_time", "arguments": "{}"}},
    ]
    assert result[2]["role"] == "tool"
    assert result[2]["tool_call_id"] == "call_weather"
    assert result[3]["role"] == "tool"
    assert result[3]["tool_call_id"] == "call_time"


def test_rebuild_history_orphan_tool_calls():
    init_db()
    session_id = "test-orphan-tc"
    tool_calls_json = json.dumps([
        {"id": "call_orphan", "type": "function", "function": {"name": "get_weather", "arguments": "{}"}},
    ])
    save_message(session_id=session_id, role="assistant", content="", model="test-model", tool_calls=tool_calls_json)
    result = rebuild_history(session_id, "test-model")
    assert len(result) == 1
    assert result[0]["role"] == "system"


def test_rebuild_history_orphan_tool_response():
    init_db()
    session_id = "test-orphan-tool-resp"
    save_message(session_id=session_id, role="tool", content="orphan result", model="test-model", tool_call_id="call_nonexistent")
    result = rebuild_history(session_id, "test-model")
    assert len(result) == 1
    assert result[0]["role"] == "system"


def test_rebuild_history_orphan_tool_calls_with_content_kept():
    init_db()
    session_id = "test-orphan-tc-with-content"
    tool_calls_json = json.dumps([
        {"id": "call_orphan", "type": "function", "function": {"name": "get_weather", "arguments": "{}"}},
    ])
    save_message(session_id=session_id, role="assistant", content="I have content even without tools", model="test-model", tool_calls=tool_calls_json)
    result = rebuild_history(session_id, "test-model")
    assert len(result) == 2
    assert result[1]["role"] == "assistant"
    assert "tool_calls" not in result[1]
    assert "I have content even without tools" in result[1]["content"]


def test_rebuild_history_reasoning():
    init_db()
    session_id = "test-reasoning"
    save_message(session_id=session_id, role="user", content="Think step by step", model="test-model")
    save_message(session_id=session_id, role="assistant", content="Final answer", model="test-model", reasoning="Let me think...")
    result = rebuild_history(session_id, "test-model")
    assert len(result) == 3
    assert result[2]["role"] == "assistant"
    assert result[2]["reasoning_content"] == "Let me think..."
    assert result[2]["content"].endswith("Final answer")


def test_rebuild_history_multiple_timestamps():
    init_db()
    session_id = "test-timestamps"
    save_message(session_id=session_id, role="user", content="First", model="test-model")
    save_message(session_id=session_id, role="assistant", content="Second", model="test-model")
    save_message(session_id=session_id, role="user", content="Third", model="test-model")
    result = rebuild_history(session_id, "test-model")
    assert len(result) == 4
    for i in range(1, 4):
        assert result[i]["content"].startswith("["), f"msg {i} missing timestamp: {result[i]['content']}"
    assert result[1]["content"].endswith("First")
    assert result[2]["content"].endswith("Second")
    assert result[3]["content"].endswith("Third")
    ts1 = re.match(r"\[(.+?)\]", result[1]["content"]).group(1)
    ts2 = re.match(r"\[(.+?)\]", result[2]["content"]).group(1)
    ts3 = re.match(r"\[(.+?)\]", result[3]["content"]).group(1)
    assert ts1 <= ts2 <= ts3


def test_rebuild_history_skips_system_rows():
    init_db()
    session_id = "test-skip-system"
    save_message(session_id=session_id, role="system", content="this should be ignored", model="test-model")
    save_message(session_id=session_id, role="user", content="Hello", model="test-model")
    result = rebuild_history(session_id, "test-model")
    assert len(result) == 2
    assert result[0]["role"] == "system"
    assert "this should be ignored" not in result[0]["content"]
    assert result[1]["role"] == "user"
    assert result[1]["content"].endswith("Hello")


def test_rebuild_history_content_none_with_tool_calls():
    init_db()
    session_id = "test-content-none-tc"
    tool_calls_json = json.dumps([
        {"id": "call_none", "type": "function", "function": {"name": "do_something", "arguments": "{}"}},
    ])
    save_message(session_id=session_id, role="assistant", content="", model="test-model", tool_calls=tool_calls_json)
    save_message(session_id=session_id, role="tool", content="done", model="test-model", tool_call_id="call_none")
    result = rebuild_history(session_id, "test-model")
    assert len(result) == 3
    assert result[1]["role"] == "assistant"
    assert result[1]["content"] is None
    assert result[1]["tool_calls"] == [
        {"id": "call_none", "type": "function", "function": {"name": "do_something", "arguments": "{}"}},
    ]
    assert result[2]["role"] == "tool"
    assert result[2]["tool_call_id"] == "call_none"


def test_rebuild_history_partial_tool_calls_filtered():
    init_db()
    session_id = "test-partial-tc"
    tool_calls_json = json.dumps([
        {"id": "call_matched", "type": "function", "function": {"name": "matched_func", "arguments": "{}"}},
        {"id": "call_orphan", "type": "function", "function": {"name": "orphan_func", "arguments": "{}"}},
    ])
    save_message(session_id=session_id, role="assistant", content="", model="test-model", tool_calls=tool_calls_json)
    save_message(session_id=session_id, role="tool", content="matched result", model="test-model", tool_call_id="call_matched")
    result = rebuild_history(session_id, "test-model")
    assert len(result) == 3
    assert result[1]["role"] == "assistant"
    assert len(result[1]["tool_calls"]) == 1
    assert result[1]["tool_calls"][0]["id"] == "call_matched"
    assert result[2]["role"] == "tool"
    assert result[2]["tool_call_id"] == "call_matched"
