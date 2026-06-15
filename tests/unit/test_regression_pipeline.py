"""Regression tests for the SSE/WS streaming pipeline.

These tests verify that the streaming pipeline doesn't regress on key
behaviors: non-blocking WS sends, correct HTTP fallback URL, markdown
rendering path, and polling vs streaming coordination.
"""

import ast
import textwrap


# ─── Structural checks (static analysis of source code) ────────────────

def test_no_await_send_event_in_adapter():
    """send_event must always be fire-and-forget (asyncio.create_task),
    never awaited directly. An await would block the async generator."""
    source = _read_source("channels/telegram/adapter.py")
    tree = ast.parse(source)

    class SendEventAawaitFinder(ast.NodeVisitor):
        def __init__(self):
            self.found = []

        def visit_Await(self, node):
            # Check if the awaited expression calls send_event
            if isinstance(node.value, ast.Call):
                self._check_call(node.value, node.lineno)
            self.generic_visit(node)

        def _check_call(self, call, lineno):
            # Match: get_ws_client().send_event(...)
            if (isinstance(call.func, ast.Attribute)
                    and call.func.attr == "send_event"
                    and isinstance(call.func.value, ast.Call)
                    and isinstance(call.func.value.func, ast.Attribute)
                    and call.func.value.func.attr == "get_ws_client"):
                self.found.append(lineno)

    finder = SendEventAawaitFinder()
    finder.visit(tree)

    assert finder.found == [], (
        f"send_event is AWAITED at lines {finder.found}! "
        "Use asyncio.create_task() instead of await."
    )


def test_all_send_event_calls_use_create_task():
    """Every send_event call in adapter.py should be wrapped in
    asyncio.create_task()."""
    source = _read_source("channels/telegram/adapter.py")
    count_create_task = source.count("asyncio.create_task(get_ws_client().send_event(")
    # Count total send_event calls by looking for the pattern
    count_total = _count_occurrences(source, "get_ws_client().send_event(")
    # create_task count should match total (all should be wrapped)
    assert count_create_task >= count_total, (
        f"Found {count_total} send_event calls but only "
        f"{count_create_task} wrapped in create_task"
    )


def test_http_fallback_url_has_correct_scheme():
    """The HTTP fallback URL must replace ws:// with http:// and
    wss:// with https:// before making the HTTP request."""
    source = _read_source("channels/telegram/ws_client.py")
    assert '.replace("ws://", "http://")' in source, (
        "Missing ws:// → http:// replacement in HTTP fallback"
    )
    assert '.replace("wss://", "https://")' in source, (
        "Missing wss:// → https:// replacement in HTTP fallback"
    )


def test_send_event_calls_are_never_awaited():
    """Verify that ALL send_event() calls in adapter.py use
    asyncio.create_task(), never await."""
    source = _read_source("channels/telegram/adapter.py")
    tree = ast.parse(source)

    class SendEventAwaitFinder(ast.NodeVisitor):
        def __init__(self):
            self.found = []

        def visit_Await(self, node):
            if isinstance(node.value, ast.Call):
                self._check_call(node.value, node.lineno)
            self.generic_visit(node)

        def _check_call(self, call, lineno):
            if (isinstance(call.func, ast.Attribute)
                    and call.func.attr == "send_event"
                    and isinstance(call.func.value, ast.Call)
                    and isinstance(call.func.value.func, ast.Attribute)
                    and call.func.value.func.attr == "get_ws_client"):
                self.found.append(lineno)

    finder = SendEventAwaitFinder()
    finder.visit(tree)
    assert finder.found == [], (
        f"send_event is AWAITED at lines {finder.found}! "
        "Use asyncio.create_task() instead of await."
    )


def test_adapter_flush_intervals_are_small():
    """Flush intervals should be small (≤10) for smooth streaming."""
    source = _read_source("channels/telegram/adapter.py")
    # Find the interval assignments
    for interval_name in ("reasoning_flush_interval", "content_flush_interval"):
        for line in source.split("\n"):
            if interval_name in line and "=" in line:
                val = line.split("=")[-1].strip()
                try:
                    ival = int(val)
                    assert ival <= 10, (
                        f"{interval_name} = {ival} is too large (max 10)"
                    )
                except ValueError:
                    pass  # dynamic value, skip


def test_polling_skips_during_streaming():
    """The polling fallback must check for active NDJSON streaming
    before replacing messages."""
    source = _read_source("web/static/modules/session-page.js")
    assert 'isStreaming' in source, (
        "Missing streaming detection (isStreaming) in polling code"
    )
    assert '!isStreaming' in source, (
        "Polling doesn't skip when streaming is active"
    )


def test_markdown_renderer_dynamic_imports_use_namespace():
    """Dynamic imports of markdown-renderer must access
    MarkdownRenderer.renderAll, not renderAll directly (the module
    exports it wrapped in an object).

    This checks the dynamic import paths (inside Promise.all or
    reloadMessages callbacks), not static import usage.
    """
    source_sse = _read_source("web/static/modules/sse-client.js")
    source_session = _read_source("web/static/modules/session-page.js")

    # Dynamic import callbacks should use .MarkdownRenderer.renderAll
    # Find all .renderAll calls inside .then() or Promise patterns
    import re

    for source, name in [(source_sse, "sse-client.js"),
                         (source_session, "session-page.js")]:
        # Find all lines that have both "renderAll" and "modules" or
        # "Promise" — these are the dynamic import paths
        has_dynamic_import_with_renderall = False
        for line in source.split("\n"):
            if "renderAll" in line and ("modules" in line or "Promise" in line):
                has_dynamic_import_with_renderall = True
                assert "MarkdownRenderer" in line, (
                    f"{name}: dynamic import uses bare renderAll "
                    f"instead of MarkdownRenderer.renderAll:\n{line}"
                )
        # If no dynamic import with renderAll exists, that's OK
        # (the test passes vacuously if there are none)


# ─── EventBus unit tests ───────────────────────────────────────────────

import asyncio
import json
import pytest

from web.services.event_bus import EventBus


@pytest.mark.asyncio
async def test_eventbus_publish_delivers_to_subscribed():
    bus = EventBus()
    q1 = await bus.subscribe("client_a")
    q2 = await bus.subscribe("client_b")
    await bus.publish("test_event", {"key": "val"})

    expected = {"type": "test_event", "data": {"key": "val"}}
    for q in (q1, q2):
        got = await asyncio.wait_for(q.get(), timeout=1)
        assert got == expected


@pytest.mark.asyncio
async def test_eventbus_unsubscribe_removes_queue():
    bus = EventBus()
    q = await bus.subscribe("client_a")
    await bus.unsubscribe("client_a")
    await bus.publish("test_event", {})
    # Queue should NOT receive anything after unsubscribe
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(q.get(), timeout=0.1)


@pytest.mark.asyncio
async def test_eventbus_stream_formats_sse():
    bus = EventBus()
    client_id = "test_sse"
    gen = bus.stream(client_id)
    # Start generator (subscribes), then publish
    async def _publish_after_delay():
        await asyncio.sleep(0.05)
        await bus.publish("ping_event", {"msg": "hello"})

    async with asyncio.TaskGroup() as tg:
        tg.create_task(_publish_after_delay())
        output = await asyncio.wait_for(gen.__anext__(), timeout=2)

    data = json.loads(output.split("data: ", 1)[1].strip())
    assert data["type"] == "ping_event"
    assert data["data"]["msg"] == "hello"


@pytest.mark.asyncio
async def test_eventbus_stream_with_id_field():
    """Each event should have an id: field."""
    bus = EventBus()
    client_id = "test_id"
    gen = bus.stream(client_id)

    async def _publish_after_delay():
        await asyncio.sleep(0.05)
        await bus.publish("evt", {})

    async with asyncio.TaskGroup() as tg:
        tg.create_task(_publish_after_delay())
        output = await asyncio.wait_for(gen.__anext__(), timeout=2)

    assert output.startswith("id: 1"), f"Expected 'id: 1', got: {output[:30]}"


@pytest.mark.asyncio
async def test_eventbus_multiple_subscribers():
    bus = EventBus()
    queues = [await bus.subscribe(f"c{i}") for i in range(3)]
    await bus.publish("evt", {"n": 42})
    for q in queues:
        got = await asyncio.wait_for(q.get(), timeout=0.5)
        assert got["data"]["n"] == 42


@pytest.mark.asyncio
async def test_subscribe_returns_same_queue():
    bus = EventBus()
    q1 = await bus.subscribe("same_id")
    q2 = await bus.subscribe("same_id")
    assert q1 is q2


# ─── Helpers ───────────────────────────────────────────────────────────

def _read_source(rel_path: str) -> str:
    import os
    repo_root = os.path.join(os.path.dirname(__file__), "..", "..")
    full = os.path.normpath(os.path.join(repo_root, rel_path))
    with open(full) as f:
        return f.read()


def _count_occurrences(text: str, substr: str) -> int:
    return text.count(substr)


def _count_renderall_without_namespace(source: str) -> int:
    """Count .renderAll calls NOT preceded by .MarkdownRenderer"""
    import re
    # Match .renderAll but NOT preceded by MarkdownRenderer (with or without ?)
    # We use a simpler approach: find all .renderAll and subtract those
    # that have MarkdownRenderer before them
    all_matches = list(re.finditer(r'\.renderAll\b', source))
    namespace_matches = list(re.finditer(r'\.MarkdownRenderer\??\.renderAll\b', source))
    return len(all_matches) - len(namespace_matches)


def _get_call_name(call_node):
    """Extract the function name from a Call node."""
    if isinstance(call_node.func, ast.Attribute):
        return call_node.func.attr
    if isinstance(call_node.func, ast.Name):
        return call_node.func.id
    return None
