from unittest.mock import AsyncMock, MagicMock

import pytest

from src.tools.runner import run_parallel_tools


def _tool_call(name: str, arguments: str, call_id: str = "call_1") -> MagicMock:
    call = MagicMock()
    call.id = call_id
    call.function.name = name
    call.function.arguments = arguments
    return call


@pytest.mark.anyio
async def test_invalid_argument_shape_is_persisted_as_a_tool_error():
    repos = MagicMock()
    repos.tool_calls.log = AsyncMock()
    run_fn = MagicMock(return_value="should not run")
    history: list = []
    detail: list = []
    used_tools: list[str] = []

    events = [
        event async for event in run_parallel_tools(
            [_tool_call("web_search", "null")],
            session_id="session-1",
            turn=2,
            history=history,
            tool_detail=detail,
            used_tools=used_tools,
            phase_tool_ids=[],
            repos=repos,
            tool_map={"web_search": run_fn},
        )
    ]

    assert events == []
    run_fn.assert_not_called()
    repos.tool_calls.log.assert_awaited_once_with(
        "session-1", "web_search", "{}", "error", turn=2,
    )
    assert used_tools == []
    assert history[0].content == "[ERROR in web_search]: Tool arguments must be a JSON object."
    assert detail == [{
        "name": "web_search",
        "args": {},
        "status": "error",
        "result_truncated": "[ERROR in web_search]: Tool arguments must be a JSON object.",
    }]
