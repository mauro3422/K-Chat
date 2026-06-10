import json
from unittest.mock import MagicMock


from src.tools.runner import run_parallel_tools


class MockFunction:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments


class MockToolCall:
    def __init__(self, tc_id, name, arguments):
        self.id = tc_id
        self.function = MockFunction(name, arguments)


def test_execute_action_unpacking():
    """Verify that execute_action is unpacked and successfully runs sub-tools."""
    # Mock tool map for sub-tool
    mock_run_subtool = MagicMock(return_value="Resultado exitoso")
    tool_map = {
        "web_search": mock_run_subtool
    }

    # Simulate execute_action tool call from LLM
    tc = MockToolCall(
        tc_id="call_mock_1",
        name="execute_action",
        arguments=json.dumps({
            "action_name": "web_search",
            "arguments": {"query": "clima de hoy"}
        })
    )

    history = []
    tool_detail = []
    used_tools = []
    phase_tool_ids = []

    # Run the executor
    events = list(run_parallel_tools(
        tool_calls=[tc],
        session_id="test-session-meta",
        turn=1,
        history=history,
        tool_detail=tool_detail,
        used_tools=used_tools,
        phase_tool_ids=phase_tool_ids,
        tagged=True,
        tool_map=tool_map
    ))

    # Verify that the sub-tool was called with the correct argument
    mock_run_subtool.assert_called_once_with(query="clima de hoy", _session_id="test-session-meta")

    # Verify that log and history show the unpacked tool name (web_search)
    assert used_tools == ["web_search"]
    assert tool_detail[0]["name"] == "web_search"
    assert tool_detail[0]["args"] == {"query": "clima de hoy"}
    assert tool_detail[0]["status"] == "ok"

    # Verify that events yield the unpacked tool name (web_search)
    calling_event = json.loads(events[0][1])
    assert calling_event["name"] == "web_search"
    assert calling_event["status"] == "calling"

    ok_event = json.loads(events[1][1])
    assert ok_event["name"] == "web_search"
    assert ok_event["status"] == "ok"

    # Verify that the history role=tool message is appended with the correct tool_call_id
    assert len(history) == 1
    assert history[0]["role"] == "tool"
    assert history[0]["content"] == "Resultado exitoso"
    assert history[0]["tool_call_id"] == "call_mock_1"
