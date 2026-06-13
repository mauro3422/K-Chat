"""Tests for _tool_persister.py"""
from unittest.mock import MagicMock

from src.tools._tool_persister import _persist_tool_results


def test_empty_tcs_info_does_nothing():
    repos = MagicMock()
    history: list = []
    tool_detail: list = []
    _persist_tool_results(
        tcs_info=[],
        results={},
        session_id="s1",
        turn=1,
        history=history,
        tool_detail=tool_detail,
        repos=repos,
    )
    repos.tool_calls.record_execution.assert_not_called()
    assert history == []
    assert tool_detail == []


def test_persists_tool_calls():
    repos = MagicMock()
    tc1 = MagicMock(); tc1.id = "call_1"
    tc2 = MagicMock(); tc2.id = "call_2"

    tcs_info = [
        (tc1, "get_weather", {"city": "Buenos Aires"}),
        (tc2, "get_time", {"zone": "UTC"}),
    ]
    results = {
        "call_1": ('{"temp": 22}', "success"),
        "call_2": ('{"time": "12:00"}', "success"),
    }
    history: list = []
    tool_detail: list = []

    _persist_tool_results(
        tcs_info=tcs_info,
        results=results,
        session_id="s1",
        turn=3,
        history=history,
        tool_detail=tool_detail,
        repos=repos,
    )

    assert repos.tool_calls.record_execution.call_count == 2
    repos.tool_calls.record_execution.assert_any_call(
        "s1", "get_weather", '{"city": "Buenos Aires"}',
        "success", '{"temp": 22}', turn=3, tool_call_id="call_1",
    )
    repos.tool_calls.record_execution.assert_any_call(
        "s1", "get_time", '{"zone": "UTC"}',
        "success", '{"time": "12:00"}', turn=3, tool_call_id="call_2",
    )

    assert len(history) == 2
    assert history[0] == {"role": "tool", "content": '{"temp": 22}', "tool_call_id": "call_1"}
    assert history[1] == {"role": "tool", "content": '{"time": "12:00"}', "tool_call_id": "call_2"}

    assert len(tool_detail) == 2
    assert tool_detail[0]["name"] == "get_weather"
    assert tool_detail[0]["status"] == "success"
    assert tool_detail[1]["name"] == "get_time"


def test_result_truncated_to_300_chars():
    repos = MagicMock()
    tc = MagicMock(); tc.id = "call_1"
    long_result = "x" * 500
    results = {"call_1": (long_result, "success")}
    tool_detail: list = []

    _persist_tool_results(
        tcs_info=[(tc, "test_func", {})],
        results=results,
        session_id="s1",
        turn=1,
        history=[],
        tool_detail=tool_detail,
        repos=repos,
    )
    assert len(tool_detail[0]["result_truncated"]) == 300


def test_missing_result_defaults_to_error():
    repos = MagicMock()
    tc = MagicMock(); tc.id = "call_missing"
    tool_detail: list = []
    history: list = []

    _persist_tool_results(
        tcs_info=[(tc, "missing_func", {})],
        results={},
        session_id="s1",
        turn=1,
        history=history,
        tool_detail=tool_detail,
        repos=repos,
    )
    assert history[0]["content"] == "[ERROR]: Missing"
    assert tool_detail[0]["status"] == "error"


def test_empty_session_id_skips_db():
    repos = MagicMock()
    tc = MagicMock(); tc.id = "call_1"

    _persist_tool_results(
        tcs_info=[(tc, "test", {})],
        results={"call_1": ("ok", "success")},
        session_id="",
        turn=1,
        history=[],
        tool_detail=[],
        repos=repos,
    )
    repos.tool_calls.record_execution.assert_not_called()
