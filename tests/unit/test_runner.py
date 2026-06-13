"""Tests for runner.py"""
import json
from unittest.mock import MagicMock


class TestExecuteToolBatch:
    def test_empty_tcs_info_returns_no_output(self):
        from src.tools.runner import _execute_tool_batch
        repos = MagicMock()
        results = {}
        gen = _execute_tool_batch([], {}, "ses", False, results, repos)
        assert list(gen) == []
        assert results == {}

    def test_executes_tool_and_populates_results(self):
        from src.tools.runner import _execute_tool_batch
        repos = MagicMock()
        tool_fn = MagicMock(return_value="some result")
        tool_map = {"web_search": tool_fn}
        tc = MagicMock()
        tc.id = "call_1"
        tcs_info = [(tc, "web_search", {"query": "test"})]

        results = {}
        gen = _execute_tool_batch(tcs_info, tool_map, "ses", False, results, repos)
        list(gen)

        tool_fn.assert_called_once_with(query="test", _session_id="ses", _repos=repos)
        assert results["call_1"] == ("some result", "ok")

    def test_passes_repos_to_tool(self):
        from src.tools.runner import _execute_tool_batch
        repos = MagicMock()
        tool_fn = MagicMock(return_value="result")
        tool_map = {"web_search": tool_fn}
        tc = MagicMock()
        tc.id = "call_1"
        tcs_info = [(tc, "web_search", {"query": "test"})]

        results = {}
        gen = _execute_tool_batch(tcs_info, tool_map, "ses", False, results, repos)
        list(gen)

        tool_fn.assert_called_once_with(query="test", _session_id="ses", _repos=repos)

    def test_tagged_yields_tool_call_events(self):
        from src.tools.runner import _execute_tool_batch
        repos = MagicMock()
        tool_fn = MagicMock(return_value="result")
        tool_map = {"web_search": tool_fn}
        tc = MagicMock()
        tc.id = "call_1"
        tcs_info = [(tc, "web_search", {"query": "test"})]

        results = {}
        gen = _execute_tool_batch(tcs_info, tool_map, "ses", True, results, repos)
        yielded = list(gen)

        assert len(yielded) == 1
        assert yielded[0][0] == "tool_call"
        data = json.loads(yielded[0][1])
        assert data["id"] == "call_1"
        assert data["name"] == "web_search"
        assert data["status"] == "ok"

    def test_error_prefix_results_in_error_status(self):
        from src.tools.runner import _execute_tool_batch
        repos = MagicMock()
        tool_fn = MagicMock(return_value="[ERROR] something broke")
        tool_map = {"web_search": tool_fn}
        tc = MagicMock()
        tc.id = "call_1"
        tcs_info = [(tc, "web_search", {})]

        results = {}
        gen = _execute_tool_batch(tcs_info, tool_map, "ses", False, results, repos)
        list(gen)

        assert results["call_1"][1] == "error"

    def test_exception_in_tool_is_caught_and_returns_error(self):
        from src.tools.runner import _execute_tool_batch
        repos = MagicMock()
        tool_fn = MagicMock(side_effect=ValueError("boom"))
        tool_map = {"web_search": tool_fn}
        tc = MagicMock()
        tc.id = "call_1"
        tcs_info = [(tc, "web_search", {})]

        results = {}
        gen = _execute_tool_batch(tcs_info, tool_map, "ses", False, results, repos)
        list(gen)

        assert results["call_1"][1] == "error"
        assert "[ERROR" in results["call_1"][0]

    def test_result_truncated_if_too_long(self):
        from src.tools.runner import _execute_tool_batch
        repos = MagicMock()
        long_result = "x" * 40000
        tool_fn = MagicMock(return_value=long_result)
        tool_map = {"web_search": tool_fn}
        tc = MagicMock()
        tc.id = "call_1"
        tcs_info = [(tc, "web_search", {})]

        results = {}
        gen = _execute_tool_batch(tcs_info, tool_map, "ses", False, results, repos)
        list(gen)

        truncated = results["call_1"][0]
        assert len(truncated) == 30000 + len("\n...[truncado]")
        assert truncated.endswith("[truncado]")

    def test_multiple_tools_executed_in_parallel(self):
        from src.tools.runner import _execute_tool_batch
        repos = MagicMock()
        tool_fn = MagicMock(return_value="ok")
        tool_map = {"tool_a": tool_fn, "tool_b": tool_fn}
        tc_a = MagicMock()
        tc_a.id = "call_a"
        tc_b = MagicMock()
        tc_b.id = "call_b"

        tcs_info = [
            (tc_a, "tool_a", {"x": 1}),
            (tc_b, "tool_b", {"y": 2}),
        ]

        results = {}
        gen = _execute_tool_batch(tcs_info, tool_map, "ses", False, results, repos)
        list(gen)

        assert set(results.keys()) == {"call_a", "call_b"}
        assert results["call_a"] == ("ok", "ok")
        assert results["call_b"] == ("ok", "ok")
