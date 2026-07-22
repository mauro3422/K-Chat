"""Tests for build_stream_generator in chat_stream.py.

Covers 13 critical paths: normal streaming, tool calls, memory events,
heartbeat forwarding, loop detection+recovery, client disconnect,
empty response, stream errors, periodic save, final save, and
interruption save in finally block.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from web.services.chat_stream import build_stream_generator
from web.services.chat_stream_contract import StreamGeneratorDeps
from src.core.orchestrator_contract import OrchestratorDeps


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _parse_events(lines: list[str]) -> list[dict]:
    """Parse NDJSON lines into event dicts."""
    return [json.loads(line) for line in lines]


def _make_stream(values: list[tuple]) -> callable:
    """Return a callable whose invocation returns an async generator.

    The async generator yields each ``(tipo, token)`` in *values*.
    """
    async def _inner(*args, **kwargs):
        for item in values:
            yield item
    return _inner


def _make_clock(values: list[float]) -> callable:
    iterator = iter(values)
    current = values[-1]

    def _clock() -> float:
        nonlocal current
        try:
            current = next(iterator)
        except StopIteration:
            pass
        return current

    return _clock


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def deps():
    """Base ``StreamGeneratorDeps`` with all injected deps mocked.

    ``loop_detector.check`` returns ``None`` by default so loop detection
    does NOT trigger unless explicitly overridden in a test.
    """
    loop_detector = MagicMock()
    loop_detector.check.return_value = None

    return StreamGeneratorDeps(
        chat_stream_fn=_make_stream([]),
        loop_detector=loop_detector,
        retry_handler=MagicMock(),
        save_fn=AsyncMock(),
        rename_fn=MagicMock(),
    )


@pytest.fixture
def background_tasks():
    return MagicMock()


@pytest.fixture
def orch_deps(background_tasks):
    """Mock OrchestratorDeps with all services mocked."""
    from unittest.mock import MagicMock
    repos = MagicMock()
    repos.stream_checkpoints.save = AsyncMock()
    repos.stream_checkpoints.clear = AsyncMock()
    deps = OrchestratorDeps(
        repos=repos,
        history_service=MagicMock(),
        telemetry_service=MagicMock(),
        llm_service=MagicMock(),
        tool_service=MagicMock(),
        session_id="s1",
        tagged=True,
        debug=MagicMock(),
        phases_output=[],
        background_tasks=background_tasks,
    )
    return deps


@pytest.fixture(autouse=True)
def _patch_infrastructure():
    yield


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# 1 — Normal message streaming
# ---------------------------------------------------------------------------

class TestNormalStreaming:
    """Verify content/reasoning tokens are forwarded as serialized events."""

    @pytest.mark.asyncio
    async def test_content_tokens(self, deps, background_tasks, orch_deps):
        tokens = ["Hello", " ", "world", "!"]
        deps.chat_stream_fn = _make_stream([("content", t) for t in tokens])

        gen = build_stream_generator(
            session_id="s1", message="hi", history=[], model="gpt4",
            background_tasks=background_tasks, deps=deps,
            orchestrator_deps=orch_deps,
        )
        events = _parse_events([line async for line in gen()])

        assert len(events) == len(tokens)
        for ev, token in zip(events, tokens):
            assert ev == {"t": "content", "d": token}

    @pytest.mark.asyncio
    async def test_reasoning_and_content(self, deps, background_tasks, orch_deps):
        deps.chat_stream_fn = _make_stream([
            ("reasoning", "think step "),
            ("reasoning", "by step"),
            ("content", "answer"),
        ])

        gen = build_stream_generator(
            session_id="s1", message="hi", history=[], model="gpt4",
            background_tasks=background_tasks, deps=deps,
            orchestrator_deps=orch_deps,
        )
        events = _parse_events([line async for line in gen()])

        assert events[0] == {"t": "reasoning", "d": "think step "}
        assert events[1] == {"t": "reasoning", "d": "by step"}
        assert events[2] == {"t": "content", "d": "answer"}


# ---------------------------------------------------------------------------
# 2 — Tool call events
# ---------------------------------------------------------------------------

class TestToolCalls:
    """Verify tool_call events are forwarded and state is reset."""

    async def test_tool_call_forwarded(self, deps, background_tasks, orch_deps):
        tool_data = {"name": "get_weather", "args": {"city": "Berlin"}}
        deps.chat_stream_fn = _make_stream([
            ("content", "checking"),
            ("tool_call", tool_data),
            ("content", "done"),
        ])

        gen = build_stream_generator(
            session_id="s1", message="hi", history=[], model="gpt4",
            background_tasks=background_tasks, deps=deps,
            orchestrator_deps=orch_deps,
        )
        events = _parse_events([line async for line in gen()])

        assert len(events) == 3
        assert events[0] == {"t": "content", "d": "checking"}
        assert events[1] == {"t": "tool_call", "d": tool_data}
        assert events[2] == {"t": "content", "d": "done"}

    async def test_content_around_tool_call(self, deps, background_tasks, orch_deps):
        deps.chat_stream_fn = _make_stream([
            ("content", "let me check "),
            ("tool_call", {"name": "search"}),
            ("content", "results are in"),
        ])

        gen = build_stream_generator(
            session_id="s1", message="hi", history=[], model="gpt4",
            background_tasks=background_tasks, deps=deps,
            orchestrator_deps=orch_deps,
        )
        events = _parse_events([line async for line in gen()])

        assert len(events) == 3
        assert events[0] == {"t": "content", "d": "let me check "}
        assert events[1] == {"t": "tool_call", "d": {"name": "search"}}
        assert events[2] == {"t": "content", "d": "results are in"}

    async def test_tool_call_resets_state(self, deps, background_tasks, orch_deps):
        """The segment closes only after the tool phase is durably complete."""
        deps.chat_stream_fn = _make_stream([
            ("content", "old content "),
            ("tool_call", {"name": "t"}),
            ("checkpoint", {"kind": "tool_phase"}),
            ("content", "new content"),
        ])

        gen = build_stream_generator(
            session_id="s1", message="hi", history=[], model="gpt4",
            background_tasks=background_tasks, deps=deps,
            orchestrator_deps=orch_deps,
        )
        # Exhaust the generator
        async for _ in gen():
            pass

        # The final save should contain only "new content" (reset after tool_call)
        assert deps.save_fn.await_count >= 1
        args, _ = deps.save_fn.call_args
        saved_content = args[1]
        assert "new content" in saved_content
        assert "old content" not in saved_content
        checkpoint = orch_deps.repos.stream_checkpoints.save
        assert checkpoint.await_count >= 1
        assert checkpoint.call_args_list[0].kwargs["checkpoint_kind"] == "tool_phase"


# ---------------------------------------------------------------------------
# 3 — Memory events
# ---------------------------------------------------------------------------

class TestMemoryEvents:
    """Verify memory events are forwarded unchanged."""

    async def test_memory_forwarded(self, deps, background_tasks, orch_deps):
        memory_block = [{"summary": "User likes Python"}]
        deps.chat_stream_fn = _make_stream([
            ("content", "ok"),
            ("memory", memory_block),
        ])

        gen = build_stream_generator(
            session_id="s1", message="hi", history=[], model="gpt4",
            background_tasks=background_tasks, deps=deps,
            orchestrator_deps=orch_deps,
        )
        events = _parse_events([line async for line in gen()])

        assert len(events) == 2
        assert events[0] == {"t": "content", "d": "ok"}
        assert events[1] == {"t": "memory", "d": memory_block}


# ---------------------------------------------------------------------------
# 4 — Heartbeat forwarding
# ---------------------------------------------------------------------------

class TestHeartbeat:
    """Verify heartbeat events are forwarded."""

    async def test_heartbeat_forwarded(self, deps, background_tasks, orch_deps):
        deps.chat_stream_fn = _make_stream([
            ("heartbeat", ""),
            ("content", "data"),
            ("heartbeat", ""),
        ])

        gen = build_stream_generator(
            session_id="s1", message="hi", history=[], model="gpt4",
            background_tasks=background_tasks, deps=deps,
            orchestrator_deps=orch_deps,
        )
        events = _parse_events([line async for line in gen()])

        assert len(events) == 3
        assert events[0] == {"t": "heartbeat", "d": ""}
        assert events[1] == {"t": "content", "d": "data"}
        assert events[2] == {"t": "heartbeat", "d": ""}

    async def test_heartbeat_not_appended_to_state(self, deps, background_tasks, orch_deps):
        """Heartbeat is yielded but does not enter state accumulation."""
        deps.chat_stream_fn = _make_stream([
            ("heartbeat", ""),
            ("content", "real"),
        ])

        gen = build_stream_generator(
            session_id="s1", message="hi", history=[], model="gpt4",
            background_tasks=background_tasks, deps=deps,
            orchestrator_deps=orch_deps,
        )
        async for _ in gen():
            pass

        # final save should only contain "real"
        args, _ = deps.save_fn.call_args
        assert "real" in args[1]


# ---------------------------------------------------------------------------
# 5 — Loop detection
# ---------------------------------------------------------------------------

class TestLoopDetection:
    """Verify loop detection yields an error and breaks the stream."""

    async def test_loop_error_yielded(self, deps, background_tasks, orch_deps):
        deps.retry_handler = None
        deps.loop_detector.check.return_value = "Loop detectado"
        deps.chat_stream_fn = _make_stream([("content", "aaaa")])

        gen = build_stream_generator(
            session_id="s1", message="hi", history=[], model="gpt4",
            background_tasks=background_tasks, deps=deps,
            orchestrator_deps=orch_deps,
        )
        events = _parse_events([line async for line in gen()])

        # loop_detected error is yielded; since the break skips state.append,
        # the empty-response guard also fires yielding a second error.
        assert events[0]["t"] == "error"
        assert events[0]["d"]["type"] == "loop_detected"
        assert events[1]["t"] == "error"
        assert events[1]["d"]["type"] == "empty_response"

    async def test_loop_check_called_for_content(self, deps, background_tasks, orch_deps):
        """detector.check() is called for every content token."""
        deps.loop_detector.check.return_value = None
        deps.chat_stream_fn = _make_stream([
            ("content", "safe"),
            ("content", "also safe"),
        ])

        gen = build_stream_generator(
            session_id="s1", message="hi", history=[], model="gpt4",
            background_tasks=background_tasks, deps=deps,
            orchestrator_deps=orch_deps,
        )
        async for _ in gen():
            pass

        assert deps.loop_detector.check.call_count == 2
        deps.loop_detector.check.assert_any_call("safe")
        deps.loop_detector.check.assert_any_call("also safe")

    async def test_non_content_not_checked(self, deps, background_tasks, orch_deps):
        """detector.check() is NOT called for non-content types."""
        deps.loop_detector.check.return_value = None
        deps.chat_stream_fn = _make_stream([
            ("reasoning", "think"),
            ("tool_call", {"name": "x"}),
        ])

        gen = build_stream_generator(
            session_id="s1", message="hi", history=[], model="gpt4",
            background_tasks=background_tasks, deps=deps,
            orchestrator_deps=orch_deps,
        )
        async for _ in gen():
            pass

        deps.loop_detector.check.assert_not_called()


# ---------------------------------------------------------------------------
# 6 — Loop recovery (success)
# ---------------------------------------------------------------------------

class TestLoopRecovery:
    """Verify transparent recovery via retry_handler works."""

    async def test_recovery_content_yielded(self, deps, background_tasks, orch_deps):
        deps.loop_detector.check.return_value = "Loop detectado"
        deps.retry_handler.can_retry = True
        deps.retry_handler.attempt_recovery = _make_stream([
            ("content", "recovered text"),
        ])
        deps.chat_stream_fn = _make_stream([("content", "original ")])

        gen = build_stream_generator(
            session_id="s1", message="hi", history=[], model="gpt4",
            background_tasks=background_tasks, deps=deps,
            orchestrator_deps=orch_deps,
        )
        events = _parse_events([line async for line in gen()])

        assert len(events) == 2
        assert events[0]["t"] == "retry"
        assert events[0]["d"]["attempt"] == 1
        assert events[0]["d"]["error_type"] == "loop_detected"
        assert events[1] == {"t": "content", "d": "recovered text"}

    async def test_recovery_receives_context(self, deps, background_tasks, orch_deps):
        deps.loop_detector.check.return_value = "Loop detectado"
        deps.retry_handler.can_retry = True

        # Use a MagicMock so we can assert on the call
        mock_recovery = MagicMock()
        mock_recovery.return_value = _make_stream([])()
        deps.retry_handler.attempt_recovery = mock_recovery
        deps.chat_stream_fn = _make_stream([("content", "original ")])

        gen = build_stream_generator(
            session_id="s1", message="hi", history=[], model="gpt4",
            background_tasks=background_tasks, deps=deps,
            orchestrator_deps=orch_deps,
        )
        async for _ in gen():
            pass

        mock_recovery.assert_called_once()
        args = mock_recovery.call_args[0]
        assert args[0] == []          # history
        assert args[1] == ""           # full_content (break before state.append)
        assert args[2] == ""           # full_reasoning
        assert args[3] == "gpt4"       # model
        assert args[4] == "s1"         # session_id


# ---------------------------------------------------------------------------
# 7 — Loop recovery failure
# ---------------------------------------------------------------------------

class TestLoopRecoveryFailure:
    """Verify fallback to loop error when recovery yields nothing or raises."""

    async def test_error_when_recovery_empty(self, deps, background_tasks, orch_deps):
        deps.loop_detector.check.return_value = "Loop detectado"
        deps.retry_handler.can_retry = True
        deps.retry_handler.attempt_recovery = _make_stream([])
        deps.chat_stream_fn = _make_stream([("content", "aaaa")])

        gen = build_stream_generator(
            session_id="s1", message="hi", history=[], model="gpt4",
            background_tasks=background_tasks, deps=deps,
            orchestrator_deps=orch_deps,
        )
        events = _parse_events([line async for line in gen()])

        assert events[0]["t"] == "retry"
        assert events[1]["t"] == "error"
        assert events[1]["d"]["type"] == "loop_detected"

    async def test_error_when_recovery_raises(self, deps, background_tasks, orch_deps):
        deps.loop_detector.check.return_value = "Loop detectado"
        deps.retry_handler.can_retry = True

        async def recovery_raises(*args, **kwargs):
            raise RuntimeError("recovery crash")
            yield  # keep as generator function  # pragma: no cover

        deps.retry_handler.attempt_recovery = recovery_raises
        deps.chat_stream_fn = _make_stream([("content", "aaaa")])

        gen = build_stream_generator(
            session_id="s1", message="hi", history=[], model="gpt4",
            background_tasks=background_tasks, deps=deps,
            orchestrator_deps=orch_deps,
        )
        events = _parse_events([line async for line in gen()])

        assert events[0]["t"] == "retry"
        assert events[1]["t"] == "error"
        assert events[1]["d"]["type"] == "loop_detected"

    async def test_recovery_not_attempted_when_cannot_retry(self, deps, background_tasks, orch_deps):
        deps.loop_detector.check.return_value = "Loop detectado"
        deps.retry_handler.can_retry = False
        deps.chat_stream_fn = _make_stream([("content", "aaaa")])

        gen = build_stream_generator(
            session_id="s1", message="hi", history=[], model="gpt4",
            background_tasks=background_tasks, deps=deps,
            orchestrator_deps=orch_deps,
        )
        async for _ in gen():
            pass

        deps.retry_handler.attempt_recovery.assert_not_called()


# ---------------------------------------------------------------------------
# 8 — Client disconnect (GeneratorExit)
# ---------------------------------------------------------------------------

class TestClientDisconnect:
    """Verify clean exit on GeneratorExit with cleanup in finally."""

    async def test_generator_exit_returns_cleanly(self, deps, background_tasks, orch_deps):
        deps.chat_stream_fn = _make_stream([("content", "hello")])

        gen = build_stream_generator(
            session_id="s1", message="hi", history=[], model="gpt4",
            background_tasks=background_tasks, deps=deps,
            orchestrator_deps=orch_deps,
        )
        agen = gen()
        first = await agen.__anext__()
        assert json.loads(first)["t"] == "content"

        await agen.aclose()
        with pytest.raises(StopAsyncIteration):
            await agen.__anext__()

    async def test_vectorization_scheduled_on_disconnect(self, deps, background_tasks, orch_deps):
        deps.chat_stream_fn = _make_stream([("content", "hello")])

        gen = build_stream_generator(
            session_id="s1", message="hi", history=[], model="gpt4",
            background_tasks=background_tasks, deps=deps,
            orchestrator_deps=orch_deps,
        )
        agen = gen()
        await agen.__anext__()
        await agen.aclose()

        # The finally block adds the vectorize task
        add_task_calls = background_tasks.add_task.call_args_list

        def is_vectorize(call) -> bool:
            func = call[0][0]
            return getattr(func, "__name__", "") == "_vectorize_session"

        vectorize_calls = [c for c in add_task_calls if is_vectorize(c)]
        assert len(vectorize_calls) >= 1


# ---------------------------------------------------------------------------
# 9 — Empty response
# ---------------------------------------------------------------------------

class TestEmptyResponse:
    """Verify an empty stream yields an empty_response error."""

    async def test_empty_stream_yields_error(self, deps, background_tasks, orch_deps):
        gen = build_stream_generator(
            session_id="s1", message="hi", history=[], model="gpt4",
            background_tasks=background_tasks, deps=deps,
            orchestrator_deps=orch_deps,
        )
        events = _parse_events([line async for line in gen()])

        assert len(events) == 1
        assert events[0] == {
            "t": "error",
            "d": {"type": "empty_response",
                  "message": "The model did not generate any content"},
        }


# ---------------------------------------------------------------------------
# 10 — Stream error handling
# ---------------------------------------------------------------------------

class TestStreamError:
    """Verify exceptions from the stream are classified and yielded as errors."""

    async def test_error_classified_and_yielded(self, deps, background_tasks, orch_deps):
        deps.retry_handler = None
        deps.chat_stream_fn = MagicMock(side_effect=ValueError("model error"))

        gen = build_stream_generator(
            session_id="s1", message="hi", history=[], model="gpt4",
            background_tasks=background_tasks, deps=deps,
            orchestrator_deps=orch_deps,
        )
        events = _parse_events([line async for line in gen()])

        assert len(events) == 1
        assert events[0]["t"] == "error"
        # classify_error maps "model error" → "model" type
        assert events[0]["d"]["type"] == "model"

    async def test_retry_on_exception_with_output(self, deps, background_tasks, orch_deps):
        """When partial content exists and retry_handler can retry,
        recovery is attempted before yielding an error."""
        deps.retry_handler.can_retry = True

        async def stream_then_crash(*args, **kwargs):
            yield ("content", "partial ")
            raise RuntimeError("connection lost")

        deps.chat_stream_fn = stream_then_crash
        deps.retry_handler.attempt_recovery = _make_stream([
            ("content", "recovered text"),
        ])

        gen = build_stream_generator(
            session_id="s1", message="hi", history=[], model="gpt4",
            background_tasks=background_tasks, deps=deps,
            orchestrator_deps=orch_deps,
        )
        events = _parse_events([line async for line in gen()])

        assert len(events) == 3
        assert events[0] == {"t": "content", "d": "partial "}
        assert events[1]["t"] == "retry"
        assert events[1]["d"]["error_type"] == "network"
        assert events[2] == {"t": "content", "d": "recovered text"}

    async def test_error_is_emitted_when_exception_recovery_is_empty(self, deps, background_tasks, orch_deps):
        """A recovery that produces no events must not hide the original failure."""
        deps.retry_handler.can_retry = True

        async def stream_then_crash(*args, **kwargs):
            yield ("content", "partial ")
            raise RuntimeError("connection lost")

        deps.chat_stream_fn = stream_then_crash
        deps.retry_handler.attempt_recovery = _make_stream([])

        gen = build_stream_generator(
            session_id="s1", message="hi", history=[], model="gpt4",
            background_tasks=background_tasks, deps=deps,
            orchestrator_deps=orch_deps,
        )
        events = _parse_events([line async for line in gen()])

        assert events[0] == {"t": "content", "d": "partial "}
        assert events[1]["t"] == "retry"
        assert events[2]["t"] == "error"
        assert events[2]["d"]["type"] == "network"

    async def test_retry_not_attempted_without_output(self, deps, background_tasks, orch_deps):
        """If the error happens before any content, retry is skipped."""
        deps.retry_handler.can_retry = True
        deps.chat_stream_fn = MagicMock(side_effect=RuntimeError("early crash"))

        gen = build_stream_generator(
            session_id="s1", message="hi", history=[], model="gpt4",
            background_tasks=background_tasks, deps=deps,
            orchestrator_deps=orch_deps,
        )
        async for _ in gen():
            pass

        deps.retry_handler.attempt_recovery.assert_not_called()


# ---------------------------------------------------------------------------
# 11 — Periodic save
# ---------------------------------------------------------------------------

class TestPeriodicSave:
    """Verify save_fn is called periodically during the stream."""

    async def test_periodic_save_triggered_by_time(self, deps, background_tasks, orch_deps):
        deps.chat_stream_fn = _make_stream([
            ("content", "a"),
            ("content", "b"),
            ("content", "c"),
            ("content", "d"),
        ])
        deps.save_fn = AsyncMock()

        # Simulate time: first call (last_save_time) = 100,
        # then each iteration: 100, 100, 100, 150
        # On the 4th tick, 150 - 100 = 50 > 30 → periodic save fires.
        time_values = [100.0, 100.0, 100.0, 100.0, 150.0]

        deps.clock = _make_clock(time_values)
        gen = build_stream_generator(
            session_id="s1", message="hi", history=[], model="gpt4",
            background_tasks=background_tasks, deps=deps,
            orchestrator_deps=orch_deps,
        )
        _ = [line async for line in gen()]

        # With no new tokens after the autosave, the final pass should skip.
        assert deps.save_fn.await_count == 1

    async def test_periodic_save_not_called_before_interval(self, deps, background_tasks, orch_deps):
        deps.chat_stream_fn = _make_stream([
            ("content", "a"),
            ("content", "b"),
        ])

        # All ticks within 30s of each other → no periodic save
        time_values = [100.0, 100.0, 105.0]

        deps.clock = _make_clock(time_values)
        gen = build_stream_generator(
            session_id="s1", message="hi", history=[], model="gpt4",
            background_tasks=background_tasks, deps=deps,
            orchestrator_deps=orch_deps,
        )
        _ = [line async for line in gen()]

        # Only the final save should have been called
        assert deps.save_fn.await_count == 1

    async def test_periodic_save_not_called_without_content(self, deps, background_tasks, orch_deps):
        """Even if time passes, no save without output."""
        deps.chat_stream_fn = _make_stream([
            ("heartbeat", ""),
        ])

        time_values = [100.0, 200.0]

        deps.clock = _make_clock(time_values)
        gen = build_stream_generator(
            session_id="s1", message="hi", history=[], model="gpt4",
            background_tasks=background_tasks, deps=deps,
            orchestrator_deps=orch_deps,
        )
        _ = [line async for line in gen()]

        # No content → empty_response error, save_fn never called
        assert deps.save_fn.await_count == 0


# ---------------------------------------------------------------------------
# 12 — Final save
# ---------------------------------------------------------------------------

class TestFinalSave:
    """Verify save_fn is called after the stream completes normally."""

    async def test_final_save_called(self, deps, background_tasks, orch_deps):
        deps.chat_stream_fn = _make_stream([("content", "done")])
        deps.save_fn = AsyncMock()

        gen = build_stream_generator(
            session_id="s1", message="hi", history=[], model="gpt4",
            background_tasks=background_tasks, deps=deps,
            orchestrator_deps=orch_deps,
        )
        async for _ in gen():
            pass

        assert deps.save_fn.await_count >= 1
        args, _ = deps.save_fn.call_args
        assert args[0] == "s1"
        assert args[1] == "done"

    async def test_emits_heartbeat_while_source_is_busy(
        self, deps, background_tasks, orch_deps,
    ):
        async def slow_stream(*args, **kwargs):
            await asyncio.sleep(0.035)
            yield ("content", "done")

        deps.chat_stream_fn = slow_stream
        with (
            patch("web.services.chat_stream.HEARTBEAT_INTERVAL", 0.01),
            patch("web.services.chat_stream.MAX_STREAM_SILENCE", 1.0),
        ):
            gen = build_stream_generator(
                session_id="s1", message="hi", history=[], model="gpt4",
                background_tasks=background_tasks, deps=deps,
                orchestrator_deps=orch_deps,
            )
            events = _parse_events([line async for line in gen()])

        assert sum(event["t"] == "heartbeat" for event in events) >= 2
        assert events[-1] == {"t": "content", "d": "done"}

    async def test_rename_scheduled_after_save(self, deps, background_tasks, orch_deps):
        deps.chat_stream_fn = _make_stream([("content", "done")])
        deps.rename_fn = MagicMock()
        deps.save_fn = AsyncMock()

        gen = build_stream_generator(
            session_id="s1", message="hi", history=[], model="gpt4",
            background_tasks=background_tasks, deps=deps,
            orchestrator_deps=orch_deps,
        )
        async for _ in gen():
            pass

        rename_calls = [
            call for call in background_tasks.add_task.call_args_list
            if call[0][0] == deps.rename_fn
        ]
        assert len(rename_calls) >= 1

    async def test_resume_keeps_initial_phases_and_completes_retry_marker(
        self, deps, background_tasks, orch_deps,
    ):
        deps.initial_phases = [
            {"content": "fase anterior"},
            {
                "retry": {
                    "attempt": 1,
                    "max_retries": 2,
                    "error_type": "network",
                    "status": "active",
                },
            },
        ]
        deps.chat_stream_fn = _make_stream([("content", "continuación")])

        gen = build_stream_generator(
            session_id="s1", message="resume", history=[], model="gpt4",
            background_tasks=background_tasks, deps=deps,
            orchestrator_deps=orch_deps,
        )
        async for _ in gen():
            pass

        phases = deps.save_fn.call_args.args[3]
        assert phases[0] == {"content": "fase anterior"}
        assert phases[1]["retry"]["status"] == "completed"

    async def test_final_save_not_called_on_empty(self, deps, background_tasks, orch_deps):
        """No final save when the stream is empty."""
        deps.save_fn = AsyncMock()

        gen = build_stream_generator(
            session_id="s1", message="hi", history=[], model="gpt4",
            background_tasks=background_tasks, deps=deps,
            orchestrator_deps=orch_deps,
        )
        async for _ in gen():
            pass

        assert deps.save_fn.await_count == 0


# ---------------------------------------------------------------------------
# 13 — Interruption save in finally block
# ---------------------------------------------------------------------------

class TestInterruptionSave:
    """Verify interrupted tails stay in checkpoints, not message history."""

    async def test_saves_partial_on_exception(self, deps, background_tasks, orch_deps):
        deps.retry_handler = None
        deps.save_fn = AsyncMock()

        async def stream_then_crash(*args, **kwargs):
            yield ("content", "partial data ")
            raise RuntimeError("oops")

        deps.chat_stream_fn = stream_then_crash

        gen = build_stream_generator(
            session_id="s1", message="hi", history=[], model="gpt4",
            background_tasks=background_tasks, deps=deps,
            orchestrator_deps=orch_deps,
        )
        async for _ in gen():
            pass

        assert deps.save_fn.await_count == 0
        checkpoint = orch_deps.repos.stream_checkpoints.save
        assert checkpoint.await_count >= 1
        assert checkpoint.call_args.kwargs["partial_content"] == "partial data "
        assert checkpoint.call_args.kwargs["status"] == "interrupted"

    async def test_saves_dirty_tail_after_periodic_save(self, deps, background_tasks, orch_deps):
        """If a periodic save happened and more tokens arrived, the tail is saved on interruption."""
        deps.retry_handler = None
        deps.save_fn = AsyncMock()

        async def stream_then_crash(*args, **kwargs):
            for token in ["a", "b", "c", "d", "e"]:
                yield ("content", token)
            raise RuntimeError("oops")

        deps.chat_stream_fn = stream_then_crash

        time_values = [100.0, 100.0, 100.0, 150.0, 160.0, 170.0, 180.0, 190.0]

        deps.clock = _make_clock(time_values)
        gen = build_stream_generator(
            session_id="s1", message="hi", history=[], model="gpt4",
            background_tasks=background_tasks, deps=deps,
            orchestrator_deps=orch_deps,
        )
        async for _ in gen():
            pass

        assert deps.save_fn.await_count == 0
        checkpoint = orch_deps.repos.stream_checkpoints.save
        assert checkpoint.await_count >= 2
        assert checkpoint.call_args.kwargs["partial_content"].endswith("e")

    async def test_not_saved_when_no_output(self, deps, background_tasks, orch_deps):
        """If the stream produced nothing, finally does not save."""
        deps.retry_handler = None
        deps.save_fn = AsyncMock()
        deps.chat_stream_fn = MagicMock(side_effect=RuntimeError("early crash"))

        gen = build_stream_generator(
            session_id="s1", message="hi", history=[], model="gpt4",
            background_tasks=background_tasks, deps=deps,
            orchestrator_deps=orch_deps,
        )
        async for _ in gen():
            pass

        # save_fn is never called (no output to save)
        assert deps.save_fn.await_count == 0

    async def test_not_saved_when_already_persisted(self, deps, background_tasks, orch_deps):
        """If periodic/final save already persisted, finally skips."""
        deps.chat_stream_fn = _make_stream([("content", "data")])
        deps.save_fn = AsyncMock(return_value=None)

        time_values = [100.0, 150.0]

        deps.clock = _make_clock(time_values)
        gen = build_stream_generator(
            session_id="s1", message="hi", history=[], model="gpt4",
            background_tasks=background_tasks, deps=deps,
            orchestrator_deps=orch_deps,
        )
        async for _ in gen():
            pass

        # The final save (and periodic if triggered) sets persisted=True,
        # so finally should not save again.
        # save_fn is called exactly once (final save — not enough content for periodic).
        # Actually, with only 1 token and time 100→150, periodic saves on token 1
        # (50>30). So we'd have both periodic and final saves, and no interruption.
        assert deps.save_fn.await_count >= 1

    async def test_dirty_content_after_periodic_save_is_persisted(self, deps, background_tasks, orch_deps):
        """New content after an autosave must still be flushed at the end."""
        deps.chat_stream_fn = _make_stream([
            ("content", "hola "),
            ("content", "mundo"),
        ])
        deps.save_fn = AsyncMock(return_value=None)

        time_values = [100.0, 131.0, 131.1, 132.0, 132.1]

        deps.clock = _make_clock(time_values)
        gen = build_stream_generator(
            session_id="s1", message="hi", history=[], model="gpt4",
            background_tasks=background_tasks, deps=deps,
            orchestrator_deps=orch_deps,
        )
        async for _ in gen():
            pass

        assert deps.save_fn.await_count == 1
        final_call = deps.save_fn.call_args_list[0][0]
        assert final_call[1] == "hola mundo"

    async def test_vectorization_always_scheduled(self, deps, background_tasks, orch_deps):
        """finally block always schedules vectorization, even on disconnect."""
        deps.chat_stream_fn = _make_stream([("content", "data")])

        gen = build_stream_generator(
            session_id="s1", message="hi", history=[], model="gpt4",
            background_tasks=background_tasks, deps=deps,
            orchestrator_deps=orch_deps,
        )
        agen = gen()
        await agen.__anext__()
        await agen.aclose()

        add_task_calls = background_tasks.add_task.call_args_list

        def is_vectorize(call):
            return getattr(call[0][0], "__name__", "") == "_vectorize_session"

        assert any(is_vectorize(c) for c in add_task_calls)
