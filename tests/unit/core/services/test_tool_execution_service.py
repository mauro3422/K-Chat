import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import AsyncGenerator, Any

from src.core.services.tool_execution_service import (
    ToolExecutionService,
    _wrap_run_with_runtime_dependencies,
)


@pytest.mark.anyio
async def test_execute_calls_streaming_loop_when_streaming_true():
    tool_registry = MagicMock()
    tool_registry.tool_map = {"test_tool": MagicMock()}
    tool_registry.tools_openai = [{"type": "function", "function": {"name": "test_tool"}}]
    tool_registry._skill_registry = None
    service = ToolExecutionService(tool_registry=tool_registry)

    events: list[Any] = []

    async def fake_streaming_loop(*args, **kwargs):
        yield "event1"
        yield "event2"

    with patch(
        "src.core.services.tool_execution_service.run_tool_loop_streaming",
        side_effect=fake_streaming_loop,
    ) as mock_streaming:
        with patch(
            "src.core.services.tool_execution_service.run_tool_loop_sync",
        ) as mock_sync:
            async for event in service.execute(
                history=[{"role": "user", "content": "hi"}],
                model="gpt-4",
                session_id="sess-1",
                streaming=True,
            ):
                events.append(event)

    assert events == ["event1", "event2"]
    mock_streaming.assert_called_once()
    mock_sync.assert_not_called()


@pytest.mark.anyio
async def test_execute_calls_sync_loop_when_streaming_false():
    tool_registry = MagicMock()
    tool_registry.tool_map = {"test_tool": MagicMock()}
    tool_registry.tools_openai = [{"type": "function", "function": {"name": "test_tool"}}]
    tool_registry._skill_registry = None
    service = ToolExecutionService(tool_registry=tool_registry)

    events: list[Any] = []

    async def fake_sync_loop(*args, **kwargs):
        yield "ev1"

    with patch(
        "src.core.services.tool_execution_service.run_tool_loop_sync",
        side_effect=fake_sync_loop,
    ) as mock_sync:
        with patch(
            "src.core.services.tool_execution_service.run_tool_loop_streaming",
        ) as mock_streaming:
            async for event in service.execute(
                history=[{"role": "user", "content": "hi"}],
                model="gpt-4",
                session_id="sess-1",
                streaming=False,
            ):
                events.append(event)

    assert events == ["ev1"]
    mock_sync.assert_called_once()
    mock_streaming.assert_not_called()


@pytest.mark.anyio
async def test_execute_passes_repos_and_llm_fns():
    tool_registry = MagicMock()
    tool_registry.tool_map = {}
    tool_registry.tools_openai = []
    tool_registry._skill_registry = None
    service = ToolExecutionService(tool_registry=tool_registry)

    repos = MagicMock()
    llm_chat_fn = MagicMock()
    llm_chat_stream_fn = MagicMock()

    async def fake_loop(
        history, model, session_id, tagged, debug, phases_output,
        used_tools, tool_detail, run_fn, tool_map,
        repos=None, llm_chat_fn=None, llm_chat_stream_fn=None,
        tool_defs=None, skill_registry=None,
    ):
        assert repos is not None
        assert llm_chat_fn is not None
        assert llm_chat_stream_fn is not None
        yield "ok"

    with patch(
        "src.core.services.tool_execution_service.run_tool_loop_streaming",
        side_effect=fake_loop,
    ):
        async for _ in service.execute(
            history=[], model="m", repos=repos,
            llm_chat_fn=llm_chat_fn, llm_chat_stream_fn=llm_chat_stream_fn,
        ):
            pass


@pytest.mark.anyio
async def test_execute_injects_cache_invalidation_wrapper():
    tool_registry = MagicMock()
    tool_registry.tool_map = {}
    tool_registry.tools_openai = []
    tool_registry._skill_registry = None
    service = ToolExecutionService(tool_registry=tool_registry)

    captured_run_fn: Any = None

    async def fake_loop(
        history, model, session_id, tagged, debug, phases_output,
        used_tools, tool_detail, run_fn, tool_map,
        repos=None, llm_chat_fn=None, llm_chat_stream_fn=None,
        tool_defs=None, skill_registry=None,
    ):
        nonlocal captured_run_fn
        captured_run_fn = run_fn
        yield "ok"

    with patch(
        "src.core.services.tool_execution_service.run_tool_loop_streaming",
        side_effect=fake_loop,
    ):
        async for _ in service.execute(history=[], model="m"):
            pass

    assert captured_run_fn is not None
    assert callable(captured_run_fn)


@pytest.mark.anyio
async def test_runtime_wrapper_injects_lan_signer():
    signer = object()
    captured_kwargs: dict[str, Any] = {}

    async def fake_parallel_tools(*args, **kwargs):
        captured_kwargs.update(kwargs)
        yield "ok"

    with patch(
        "src.core.services.tool_execution_service.run_parallel_tools",
        new=fake_parallel_tools,
    ):
        events = [
            event
            async for event in _wrap_run_with_runtime_dependencies(signer)(
                "tool-calls"
            )
        ]

    assert events == ["ok"]
    assert captured_kwargs["lan_request_signer"] is signer


@pytest.mark.anyio
async def test_execute_uses_default_registry_when_none():
    with patch(
        "src.core.services.tool_execution_service.tools.get_default_registry",
        return_value=MagicMock(tool_map={}, tools_openai=[], _skill_registry=None),
    ) as mock_get:
        service = ToolExecutionService()

    assert service.tool_registry is not None
    mock_get.assert_called_once()
