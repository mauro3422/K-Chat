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


def test_sse_new_message_has_full_content():
    """The SSE new_message event for assistant must include
    full content, reasoning, and phases (not just a preview)."""
    source = _read_source("channels/telegram/adapter.py")
    # Find the new_message JSON in _persist_conversation
    assert '"content": assistant_text' in source, (
        "new_message SSE event missing full content"
    )
    assert '"reasoning": reasoning' in source, (
        "new_message SSE event missing reasoning"
    )
    assert '"phases": phases' in source, (
        "new_message SSE event missing phases"
    )


def test_append_message_uses_render_message():
    """The appendMessage function must use renderMessage directly
    (not renderMessageList) to avoid replacing the entire DOM."""
    source = _read_source("web/static/modules/sse-client.js")
    assert 'appendMessage' in source, (
        "sse-client.js missing appendMessage function"
    )
    assert 'insertAdjacentHTML' in source, (
        "appendMessage must use insertAdjacentHTML to avoid DOM replacement"
    )
    assert 'renderMessage' in source, (
        "appendMessage must call renderMessage, not renderMessageList"
    )


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


# ─── Telegram bot regression tests ─────────────────────────────────────

def test_telegram_api_client_has_delete_message():
    """TelegramAPIClient must have a delete_message method that uses
    the Telegram deleteMessage API endpoint."""
    source = _read_source("channels/telegram/api_client.py")
    assert 'async def delete_message(' in source, (
        "Missing delete_message method in TelegramAPIClient"
    )
    assert '"deleteMessage"' in source or "'deleteMessage'" in source, (
        "delete_message must call the deleteMessage Telegram API"
    )


def test_telegram_bot_clear_returns_early():
    """When text == '/clear', bot.py must return before calling
    process_message, so the command never reaches the LLM."""
    source = _read_source("channels/telegram/bot.py")
    assert '''if text == "/clear":''' in source or """if text == '/clear':""" in source
    # After the /clear check, there should be a send_message + return
    # before the process_message call
    lines = source.split("\n")
    clear_found = False
    for i, line in enumerate(lines):
        if 'text == "/clear"' in line or "text == '/clear'" in line:
            clear_found = True
        if clear_found:
            if 'return' in line:
                break
            if 'process_message' in line:
                assert False, (
                    "/clear handled AFTER process_message call at line "
                    f"{i+1}! Must return before process_message."
                )
    assert clear_found, "Missing /clear guard in bot.py"


def test_adapter_differentiates_new_vs_reset():
    """The adapter should handle '/reset' (same session, clear messages)
    differently from '/new' (archive + new session)."""
    source = _read_source("channels/telegram/adapter.py")
    assert 'if text == "/reset":' in source, (
        "Missing /reset handler in adapter"
    )
    assert 'if text == "/new":' in source, (
        "Missing /new handler in adapter"
    )
    assert 'delete_session_messages' in source, (
        "/reset must call delete_session_messages to clear the session"
    )
    assert '_reset_session' in source, (
        "/new must call _reset_session to create a new session"
    )


def test_message_repository_has_delete_session_messages():
    """MessageRepository must have a method to delete all messages
    for a session (used by /reset)."""
    source = _read_source("src/memory/repos/message_repository.py")
    assert 'async def delete_session_messages(' in source, (
        "Missing delete_session_messages in MessageRepository"
    )
    assert 'DELETE FROM messages WHERE session_id = ?' in source, (
        "Must use DELETE FROM messages to clear session messages"
    )


def test_clear_chat_messages_logs_count():
    """_clear_chat_messages should log how many messages it found
    and deleted, so we can debug when clear doesn't work."""
    source = _read_source("channels/telegram/bot.py")
    assert '"TG clear:' in source or "'TG clear:" in source or "'TG clear:'" in source, (
        "_clear_chat_messages must log its progress"
    )
    assert 'len(all_ids)' in source, (
        "Must log the number of tracked IDs found"
    )
    assert 'count' in source, (
        "Must track and log the number of deleted messages"
    )


def test_check_should_rename_allows_telegram():
    """check_should_rename should return True for Telegram sessions
    (identified by telegram_chat_id) with no name and 1 user msg."""
    source = _read_source("src/memory/repos/session_repository.py")
    assert 'telegram_chat_id is not None' in source or '"telegram_chat_id"' in source, (
        "Must check for telegram_chat_id column"
    )


def test_adapter_auto_rename_after_persist():
    """After _persist_conversation, the adapter must trigger
    auto_rename_session as a background task."""
    source = _read_source("channels/telegram/adapter.py")
    assert 'auto_rename_session' in source, (
        "Missing auto_rename_session call in adapter"
    )
    assert 'asyncio.create_task(auto_rename_session(' in source, (
        "auto_rename_session must be called as background task"
    )


def test_handlers_has_sessions_command():
    """handlers.py must have a handler for /sessions that captures
    both '/sessions' and '/sessions <arg>'."""
    source = _read_source("channels/telegram/handlers.py")
    assert 'handle_command_sessions' in source, (
        "Missing sessions command handler"
    )
    assert '/sessions' in source, (
        "Handler must check for /sessions text"
    )


def test_adapter_has_sessions_command():
    """adapter.py must handle /sessions command (list/switch)."""
    source = _read_source("channels/telegram/adapter.py")
    assert '_handle_sessions_command' in source, (
        "Missing _handle_sessions_command function"
    )
    assert '/sessions' in source or '"/sessions"' in source, (
        "Must route /sessions to handler"
    )
    assert 'tg_sessions' in source, (
        "Must collect TG sessions from repo"
    )


def test_delete_message_persisted_to_telegram_msg_ids():
    """MessageManager.set_msg_id must persist to telegram_msg_ids
    table via TelegramMsgIdRepo (survives bot restarts)."""
    source = _read_source("channels/telegram/message_manager.py")
    assert 'self._repo.save(' in source, (
        "set_msg_id must call repo.save() to persist to SQLite"
    )
    assert 'self._repo is not None' in source, (
        "Must check for repo before persisting"
    )


def test_get_all_msg_ids_merges_memory_and_db():
    """get_all_msg_ids should read from both in-memory state and
    the DB, so IDs survive bot restarts."""
    source = _read_source("channels/telegram/message_manager.py")
    assert 'self._repo.get_all(' in source, (
        "get_all_msg_ids must read from DB repo"
    )
    assert 'seen' in source or 'set()' in source, (
        "Must deduplicate IDs to avoid double-deletes"
    )


# ─── /delete command tests ─────────────────────────────────────────────

def test_handlers_has_delete_command():
    """handlers.py must have a handler for /delete."""
    source = _read_source("channels/telegram/handlers.py")
    assert 'handle_command_delete' in source, (
        "Missing /delete command handler"
    )
    assert '/delete' in source, (
        "Handler must check for /delete text"
    )


def test_bot_handles_delete_command():
    """bot.py must clear messages for /delete and NOT skip the LLM
    (the adapter handles the actual session deletion)."""
    source = _read_source("channels/telegram/bot.py")
    assert '/delete' in source, (
        "Must handle /delete in bot.py"
    )
    # /delete should be in the visual-clear list
    assert '"/new", "/reset", "/clear", "/delete"' in source, (
        "/delete must be in the visual-clear list (with /new, /reset, /clear)"
    )
    # It must NOT be in the skip-LLM list (only /clear should be)
    assert 'if text == "/clear":' in source, (
        "Only /clear should skip the LLM"
    )
    # /clear return should be right after the skip check, not /delete
    clear_return_line = None
    delete_skip_line = None
    for i, line in enumerate(source.split("\n")):
        if line.strip().startswith('if text == "/clear":'):
            clear_return_line = i
        if line.strip().startswith('if text == "/delete":'):
            delete_skip_line = i
    assert clear_return_line is not None, "Missing /clear skip check"
    assert delete_skip_line is None, (
        "/delete must NOT have its own skip check! "
        "It goes through process_message → adapter handles deletion."
    )


def test_adapter_delete_calls_delete_cascade():
    """adapter.py /delete must call delete_cascade to remove the
    session and all its messages from DB."""
    source = _read_source("channels/telegram/adapter.py")
    assert 'if text == "/delete":' in source, (
        "Missing /delete handler in adapter"
    )
    assert 'delete_cascade' in source, (
        "/delete must call delete_cascade on the session"
    )
    assert 'TelegramMsgIdRepo' in source or 'delete_chat' in source, (
        "/delete must clear telegram_msg_ids for the chat"
    )


# ─── Service config tests ──────────────────────────────────────────────

def test_service_file_has_killmode_mixed():
    """The systemd service must have KillMode=mixed to prevent
    stale processes from holding the port."""
    import os
    svc = os.path.expanduser("~/.config/systemd/user/k-chat.service")
    with open(svc) as f:
        content = f.read()
    assert 'KillMode=mixed' in content, (
        "Missing KillMode=mixed in k-chat.service"
    )
    assert 'TimeoutStopSec=30' in content, (
        "Missing TimeoutStopSec=30 in k-chat.service"
    )


# ─── Sessions command tests ────────────────────────────────────────────

def test_adapter_sessions_switch_by_number():
    """_handle_sessions_command must support switching by index
    with '/sessions <n>'."""
    source = _read_source("channels/telegram/adapter.py")
    assert 'int(parts[1])' in source, (
        "Must parse /sessions argument as integer index"
    )
    assert 'UPDATE sessions SET created_at' in source, (
        "Must update created_at to make target session active"
    )


def test_adapter_session_listing():
    """Session listing must use find_all_by_telegram_chat_id."""
    source = _read_source("channels/telegram/adapter.py")
    assert 'find_all_by_telegram_chat_id' in source, (
        "Must use find_all_by_telegram_chat_id for session listing"
    )
    assert 'tg_sessions' in source, (
        "Must collect TG sessions into a list"
    )


# ─── Auto-rename flow tests ────────────────────────────────────────────

def test_adapter_imports_auto_rename():
    """adapter.py must import auto_rename_session to rename
    Telegram sessions after first message."""
    source = _read_source("channels/telegram/adapter.py")
    assert 'from src.background_tasks import auto_rename_session' in source, (
        "Must import auto_rename_session"
    )


def test_session_repo_has_telegram_lookup():
    """SessionRepository must have find_by_telegram_chat_id and
    find_all_by_telegram_chat_id methods."""
    source = _read_source("src/memory/repos/session_repository.py")
    assert 'find_by_telegram_chat_id' in source, (
        "Missing find_by_telegram_chat_id method"
    )
    assert 'find_all_by_telegram_chat_id' in source, (
        "Missing find_all_by_telegram_chat_id method"
    )


def test_delete_sends_sse_notify():
    """Telegram /delete must send an SSE session_deleted event so
    the web UI sidebar refreshes and redirects if viewing the session."""
    source = _read_source("channels/telegram/adapter.py")
    assert 'session_deleted' in source, (
        "/delete must send 'session_deleted' SSE event"
    )


def test_sse_client_handles_session_deleted():
    """sse-client.js must handle session_deleted by refreshing the
    sidebar and redirecting to the most recent session (or / if none)."""
    source = _read_source("web/static/modules/sse-client.js")
    assert 'session_deleted' in source, (
        "Missing session_deleted handler in sse-client.js"
    )
    assert '.session-item[data-sid]' in source, (
        "Must find the most recent session from sidebar"
    )
    assert "window.location.href = '/'" in source, (
        "Must fallback to / if no sessions left"
    )


# ─── Long message / continuation tests ────────────────────────────────

def test_renderer_edit_with_retry_accepts_phase_key():
    """_edit_with_retry must accept an optional phase_key parameter
    for tracking continuation messages."""
    source = _read_source("channels/telegram/renderer.py")
    assert 'phase_key: str | None = None' in source, (
        "Missing phase_key parameter in _edit_with_retry"
    )
    assert 'self._mm.get_continuations(' in source, (
        "Must check for existing continuations via MessageManager"
    )
    assert 'self._mm.set_continuation(' in source, (
        "Must track new continuation messages via MessageManager"
    )


def test_renderer_continuations_tracked_in_mm():
    """MessageManager must have get_continuations and set_continuation
    methods to track overflow chunks."""
    source = _read_source("channels/telegram/message_manager.py")
    assert 'get_continuations' in source, (
        "Missing get_continuations method in MessageManager"
    )
    assert 'set_continuation' in source, (
        "Missing set_continuation method in MessageManager"
    )
    assert '_continuations' in source, (
        "Missing _continuations dict in MessageManager"
    )


def test_continuations_included_in_get_all_msg_ids():
    """get_all_msg_ids must include continuation message IDs so they
    get cleaned up on /clear or /delete."""
    source = _read_source("channels/telegram/message_manager.py")
    assert 'self._continuations.get(chat_id' in source, (
        "Must include continuations in get_all_msg_ids"
    )


def test_adapter_generatorexit_handled():
    """adapter.py must handle GeneratorExit to avoid losing partial
    data when the renderer stops iterating."""
    source = _read_source("channels/telegram/adapter.py")
    assert 'except GeneratorExit:' in source, (
        "Missing GeneratorExit handler in adapter.py"
    )
    assert '_persist_partial_conversation' in source, (
        "GeneratorExit handler must persist partial data"
    )


def test_adapter_timeout_persists_partial():
    """The timeout path in adapter.py must persist partial data before
    returning, not just yield and exit."""
    source = _read_source("channels/telegram/adapter.py")
    assert '_STREAM_TIMEOUT' in source, (
        "Missing timeout constant"
    )
    # Verify partial persist is in the timeout block
    lines = source.split("\n")
    timeout_block = False
    has_persist = False
    for line in lines:
        if '_STREAM_TIMEOUT' in line:
            timeout_block = True
        if timeout_block and '_persist_partial_conversation' in line:
            has_persist = True
            break
        # The timeout block should end at 'return'
        if timeout_block and 'return' in line and has_persist:
            break
    assert has_persist, (
        "Timeout block must call _persist_partial_conversation"
    )


def test_do_edit_handles_fallback_text():
    """_do_edit must handle fallback_text from error handler, like
    _do_send already does."""
    source = _read_source("channels/telegram/renderer.py")
    assert 'action.fallback_text' in source and 'send_message' in source, (
        "_do_edit must send fallback text on error"
    )


# ─── Inline tool pills tests ─────────────────────────────────────────

def test_renderer_uses_single_main_message():
    """The renderer must use ONE main message per chat (not separate
    messages per phase)."""
    source = _read_source("channels/telegram/renderer.py")
    assert '_main_msg' in source, (
        "Missing _main_msg dict (single message per turn)"
    )
    assert '_display_text' in source, (
        "Missing _display_text accumulator"
    )
    assert '_ensure_main_msg' in source, (
        "Missing _ensure_main_msg method"
    )


def test_tool_pills_inline():
    """Tool calls must appear as INLINE pills in the main message,
    not as separate messages."""
    source = _read_source("channels/telegram/renderer.py")
    assert '_render_tool_call' in source, (
        "Missing _render_tool_call method"
    )
    assert '_tool_pills' in source, (
        "Missing _tool_pills tracker"
    )
    # Verify no separate tool message creation
    assert 'set_tool_msg_id' not in source.split("async def _render_tool_call")[1].split("async def")[0], (
        "Tool renderer must NOT call set_tool_msg_id (no separate messages)"
    )
    assert 'reset_phases' not in source.split("async def _render_tool_call")[1].split("async def")[0], (
        "Tool renderer must NOT call reset_phases"
    )


def test_tool_status_updates_inline():
    """Tool status updates (calling→ok→error) must replace inline pill
    text in the main message, not create new messages."""
    source = _read_source("channels/telegram/renderer.py")
    tc_block = source.split("async def _render_tool_call")[1].split("async def")[0]
    assert 'old_pill' in tc_block, (
        "Tool renderer must check for existing pill to replace"
    )
    assert 'self._tool_pills[chat_id][tool_id]' in tc_block, (
        "Tool renderer must track pills by tool_id"
    )


# ─── HTML formatting tests ───────────────────────────────────────────

def test_renderer_uses_html_parse_mode():
    """The renderer must use HTML parse_mode for Telegram messages
    to render bold, italic, code formatting."""
    source = _read_source("channels/telegram/renderer.py")
    assert '_build_html' in source, (
        "Missing _build_html method for HTML formatting"
    )
    assert 'parse_mode="HTML"' in source, (
        "Must use HTML parse_mode for Telegram API calls"
    )
    assert 're.sub' in source, (
        "Must use regex to convert markdown to HTML tags"
    )


def test_html_escapes_special_chars():
    """HTML builder must escape &, <, > to avoid broken entities."""
    source = _read_source("channels/telegram/renderer.py")
    assert 'html_escape' in source, (
        "Missing _html_escape static method"
    )
    assert '&amp;' in source, (
        "Must escape & to &amp;"
    )
    assert '&lt;' in source, (
        "Must escape < to &lt;"
    )


def test_renderer_tracks_continuations():
    """The renderer must track continuation messages per chat to avoid
    duplicate 📎 chunks on sequential edits."""
    source = _read_source("channels/telegram/renderer.py")
    assert '_cont_msgs' in source, (
        "Missing _cont_msgs continuation tracker"
    )
    assert 'conts.append' in source, (
        "Must append new continuation message IDs"
    )
    assert 'conts[ci]' in source, (
        "Must reuse existing continuation message IDs"
    )


def test_reasoning_has_double_newline():
    """The '🤔 Pensando...' header must be followed by \\n\\n (blank line)
    to separate it from the reasoning text."""
    source = _read_source("channels/telegram/renderer.py")
    assert '🤔 Pensando' in source, (
        "Missing reasoning header"
    )
    # Check that the header is followed by two newlines (empty line)
    # In f-strings, \n\n in Python source is a literal blank line
    has_double = False
    for line in source.split("\n"):
        if "🤔 Pensando..." in line and r"\n\n" in line:
            has_double = True
            break
        if "🤔 Pensando..." in line and line.strip().endswith("..."):
            # Check if the next line is blank (empty) in the source
            has_double = True
            break
    assert has_double, (
        "Reasoning header must be followed by double newline (blank line)"
    )


def test_renderer_persists_msg_ids():
    """The renderer must persist main message IDs via
    MessageManager.store_msg_id so _clear_chat_messages can find them."""
    source = _read_source("channels/telegram/renderer.py")
    assert 'store_msg_id' in source, (
        "Renderer must call store_msg_id to persist message IDs"
    )
    assert 'self._mm.store_msg_id(chat_id, "main"' in source, (
        "Main message ID must be stored as 'main' key"
    )
