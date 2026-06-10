from web.ui_utils import render_msg_with_phases
from src.core.history import match_tools_to_msgs as _match_tools_to_msgs

def test_match_tools_to_msgs_empty():
    """Test matching with empty lists."""
    assert _match_tools_to_msgs([], []) == {}

def test_match_tools_to_msgs_basic():
    """Test matching tool calls to assistant messages chronologically."""
    # msgs format: (role, content, model, ts, reasoning, phases_str)
    msgs = [
        ("user", "Hello", "model", 10, None, None),
        ("assistant", "Hi there", "model", 20, "reasoning", "[]"),
        ("user", "Do search", "model", 30, None, None),
        ("assistant", "Here is search result", "model", 50, "reasoning", "[]"),
    ]
    # all_tools format: (name, inp, status, t_ts, turn)
    all_tools = [
        ("web_search", "query1", "ok", 15, 1),
        ("web_search", "query2", "ok", 40, 1),
        ("save_memory", "mem1", "ok", 45, 1),
    ]

    matched = _match_tools_to_msgs(msgs, all_tools)

    # Message at ts=20 should match tools <= 20 (only tool at t_ts=15)
    assert len(matched[20]) == 1
    assert matched[20][0][0] == "web_search"
    assert matched[20][0][1] == "query1"

    # Message at ts=50 should match tools <= 50 that weren't matched before (t_ts=40, 45)
    assert len(matched[50]) == 2
    assert matched[50][0][1] == "query2"
    assert matched[50][1][1] == "mem1"

def testrender_msg_with_phases_user():
    """Test rendering of a user message."""
    html_out = render_msg_with_phases("user", "Hello <world>", None, [], ts=123)
    assert '<div class="msg user">' in html_out
    assert '<div class="msg-label">Tu</div>' in html_out
    assert 'Hello &lt;world&gt;' in html_out
    assert '123' in html_out

def testrender_msg_with_phases_assistant_legacy():
    """Test rendering of a legacy assistant message (no phases, only content/reasoning)."""
    matched_tools = [
        ("web_search", "query1", "ok", 15, 1)
    ]
    html_out = render_msg_with_phases(
        "assistant",
        "Final content",
        "Thinking deep...",
        matched_tools,
        ts=20,
        phases=None
    )
    assert '<div class="msg assistant">' in html_out
    assert '<summary>Razonamiento</summary>' in html_out
    assert '<div class="rt">Thinking deep...</div>' in html_out
    assert '<div class="tool-calls">' in html_out
    assert 'tc-item ok' in html_out
    assert 'web_search' in html_out
    assert '<div class="msg-body md-content">Final content</div>' in html_out

def testrender_msg_with_phases_assistant_sequential():
    """Test rendering of sequential phases in assistant message."""
    phases = [
        {"reasoning": "First reasoning step", "content": "Introductory content"},
        {"reasoning": "Second reasoning step", "content": "Final conclusion"}
    ]
    # Tools matched are:
    # - Turn 1 (idx 1): web_search
    # - Turn 2 (idx 2): save_memory
    matched_tools = [
        ("web_search", "query1", "ok", 15, 1),
        ("save_memory", "mem1", "error", 18, 2)
    ]
    html_out = render_msg_with_phases(
        "assistant",
        "Introductory content\nFinal conclusion",
        "Final reasoning text",
        matched_tools,
        ts=30,
        phases=phases
    )

    # Check order of elements in HTML output:
    # 1. First reasoning
    # 2. First tool (turn 1)
    # 3. First content
    # 4. Second reasoning
    # 5. Second tool (turn 2)
    # 6. Second content

    idx_r1 = html_out.find("First reasoning step")
    idx_t1 = html_out.find("web_search")
    idx_c1 = html_out.find("Introductory content")
    idx_r2 = html_out.find("Second reasoning step")
    idx_t2 = html_out.find("save_memory")
    idx_c2 = html_out.find("Final conclusion")

    assert idx_r1 != -1
    assert idx_t1 != -1
    assert idx_c1 != -1
    assert idx_r2 != -1
    assert idx_t2 != -1
    assert idx_c2 != -1

    assert idx_r1 < idx_c1 < idx_t1 < idx_r2 < idx_c2 < idx_t2

def testrender_msg_with_phases_fallback_empty_phases():
    """Test retrocompatibility when phases key is empty list."""
    matched_tools = [
        ("web_search", "query1", "ok", 15, 1)
    ]
    html_out = render_msg_with_phases(
        "assistant",
        "Final content",
        "Thinking deep...",
        matched_tools,
        ts=20,
        phases=[]
    )
    assert '<div class="rt">Thinking deep...</div>' in html_out
    assert 'web_search' in html_out
    assert '<div class="msg-body md-content">Final content</div>' in html_out
