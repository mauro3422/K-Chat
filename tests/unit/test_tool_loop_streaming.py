import json
from types import SimpleNamespace

from src.core.debug_info import DebugInfo
from src.core.tool_loop import run_tool_loop_streaming


def _tool_call(tc_id: str, name: str, args: dict[str, object]) -> SimpleNamespace:
    tc = SimpleNamespace()
    tc.id = tc_id
    tc.function = SimpleNamespace()
    tc.function.name = name
    tc.function.arguments = json.dumps(args)
    return tc


def test_streaming_duplicate_content_after_tool_turn_breaks_without_reexecuting_tools():
    stream_calls: list[int] = []
    tool_runs: list[int] = []
    phases_output: list[dict[str, object]] = []
    history = [{"role": "system", "content": "test"}]

    def llm_chat_stream_fn(messages, model, **kwargs):
        idx = len(stream_calls)
        stream_calls.append(idx)
        tool_calls_output = kwargs.get("tool_calls_output")
        if idx == 0:
            if tool_calls_output is not None:
                tool_calls_output[:] = [_tool_call("c1", "web_search", {"query": "test"})]
            return iter([("content", "Repeated answer"), ("tool_call", json.dumps({"name": "web_search", "status": "calling"}))])
        if tool_calls_output is not None:
            tool_calls_output[:] = []
        return iter([("content", "Repeated answer")])

    def run_parallel_tools_fn(*args, **kwargs):
        tool_runs.append(1)
        return iter([])

    tokens = list(run_tool_loop_streaming(
        history=history,
        model="test-model",
        session_id="sess-1",
        tagged=True,
        debug=DebugInfo(),
        phases_output=phases_output,
        used_tools=[],
        tool_detail=[],
        run_parallel_tools_fn=run_parallel_tools_fn,
        tool_map={"web_search": lambda **kw: "ok"},
        max_turns=3,
        llm_chat_stream_fn=llm_chat_stream_fn,
        llm_chat_fn=lambda *a, **kw: None,
        tool_defs=[],
    ))

    assert tool_runs == [1]
    assert len(stream_calls) == 2
    assert any(t[0] == "content" for t in tokens)
    assert len(phases_output) >= 1
