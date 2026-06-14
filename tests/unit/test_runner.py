import pytest
from unittest.mock import AsyncMock, MagicMock
"""Tests for runner.py"""
import json


class TestExecuteToolBatch:
    @pytest.mark.anyio
    async def test_empty_tcs_info_returns_no_output(self, repos):
        from src.tools.runner import _execute_tool_batch
        results = {}
        gen = _execute_tool_batch([], {}, "ses", False, results, repos)
        items = [item async for item in gen]
        assert items == []
        assert results == {}

    @pytest.mark.anyio
    async def test_executes_tool_and_populates_results(self, repos):
        from src.tools.runner import _execute_tool_batch
        tool_fn = AsyncMock(return_value="some result")
        tool_map = {"web_search": tool_fn}
        tc = MagicMock()
        tc.id = "call_1"
        tcs_info = [(tc, "web_search", {"query": "test"})]

        results = {}
        gen = _execute_tool_batch(tcs_info, tool_map, "ses", False, results, repos)
        async for _ in gen:
            pass

        tool_fn.assert_called_once_with(query="test", _session_id="ses", _repos=repos)
        assert results["call_1"] == ("some result", "ok")

    @pytest.mark.anyio
    async def test_passes_repos_to_tool(self, repos):
        from src.tools.runner import _execute_tool_batch
        tool_fn = AsyncMock(return_value="result")
        tool_map = {"web_search": tool_fn}
        tc = MagicMock()
        tc.id = "call_1"
        tcs_info = [(tc, "web_search", {"query": "test"})]

        results = {}
        gen = _execute_tool_batch(tcs_info, tool_map, "ses", False, results, repos)
        async for _ in gen:
            pass

        tool_fn.assert_called_once_with(query="test", _session_id="ses", _repos=repos)

    @pytest.mark.anyio
    async def test_tagged_yields_tool_call_events(self, repos):
        from src.tools.runner import _execute_tool_batch
        tool_fn = AsyncMock(return_value="result")
        tool_map = {"web_search": tool_fn}
        tc = MagicMock()
        tc.id = "call_1"
        tcs_info = [(tc, "web_search", {"query": "test"})]

        results = {}
        gen = _execute_tool_batch(tcs_info, tool_map, "ses", True, results, repos)
        yielded = [item async for item in gen]

        assert len(yielded) == 1
        assert yielded[0][0] == "tool_call"
        data = json.loads(yielded[0][1])
        assert data["id"] == "call_1"
        assert data["name"] == "web_search"
        assert data["status"] == "ok"

    @pytest.mark.anyio
    async def test_error_prefix_results_in_error_status(self, repos):
        from src.tools.runner import _execute_tool_batch
        tool_fn = AsyncMock(return_value="[ERROR] something broke")
        tool_map = {"web_search": tool_fn}
        tc = MagicMock()
        tc.id = "call_1"
        tcs_info = [(tc, "web_search", {})]

        results = {}
        gen = _execute_tool_batch(tcs_info, tool_map, "ses", False, results, repos)
        async for _ in gen:
            pass

        assert results["call_1"][1] == "error"

    @pytest.mark.anyio
    async def test_exception_in_tool_is_caught_and_returns_error(self, repos):
        from src.tools.runner import _execute_tool_batch
        tool_fn = AsyncMock(side_effect=ValueError("boom"))
        tool_map = {"web_search": tool_fn}
        tc = MagicMock()
        tc.id = "call_1"
        tcs_info = [(tc, "web_search", {})]

        results = {}
        gen = _execute_tool_batch(tcs_info, tool_map, "ses", False, results, repos)
        async for _ in gen:
            pass

        assert results["call_1"][1] == "error"
        assert "[ERROR" in results["call_1"][0]

    @pytest.mark.anyio
    async def test_result_truncated_if_too_long(self, repos):
        from src.tools.runner import _execute_tool_batch
        long_result = "x" * 40000
        tool_fn = AsyncMock(return_value=long_result)
        tool_map = {"web_search": tool_fn}
        tc = MagicMock()
        tc.id = "call_1"
        tcs_info = [(tc, "web_search", {})]

        results = {}
        gen = _execute_tool_batch(tcs_info, tool_map, "ses", False, results, repos)
        async for _ in gen:
            pass

        truncated = results["call_1"][0]
        assert len(truncated) == 30000 + len("\n...[truncated]")
        assert truncated.endswith("[truncated]")

    @pytest.mark.anyio
    async def test_multiple_tools_executed_in_parallel(self, repos):
        from src.tools.runner import _execute_tool_batch
        tool_fn = AsyncMock(return_value="ok")
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
        async for _ in gen:
            pass

        assert set(results.keys()) == {"call_a", "call_b"}
        assert results["call_a"] == ("ok", "ok")
        assert results["call_b"] == ("ok", "ok")
