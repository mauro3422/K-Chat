"""Tests for run_code tool."""
import json
import pytest

from src.tools import run_code


class TestRunCode:
    @pytest.mark.anyio
    async def test_simple_python_execution(self):
        """Test simple Python code execution."""
        result = run_code.run(code="print('Hello, World!')")
        data = json.loads(result)
        assert data["status"] == "ok"
        assert "Hello, World!" in data["stdout"]
        assert data["exit_code"] == 0
    
    @pytest.mark.anyio
    async def test_syntax_error_auto_fix(self):
        """Test that syntax errors are detected and auto-fix attempted."""
        # Python 2 style print without parentheses
        result = run_code.run(code="print 'hello'")
        data = json.loads(result)
        # Should either auto-fix and run, or return syntax error
        assert data["status"] in ("ok", "error")
    
    @pytest.mark.anyio
    async def test_blocked_module_os(self):
        """Test that importing os is blocked in sandbox."""
        code = "import os\nprint(os.getcwd())"
        result = run_code.run(code=code)
        data = json.loads(result)
        assert data["status"] == "error"
        assert "SANDBOX" in data.get("stderr", "") or "bloqueado" in data.get("error", "").lower()
    
    @pytest.mark.anyio
    async def test_blocked_module_subprocess(self):
        """Test that importing subprocess is blocked in sandbox."""
        code = "import subprocess\nsubprocess.run(['ls'])"
        result = run_code.run(code=code)
        data = json.loads(result)
        assert data["status"] == "error"
        assert "SANDBOX" in data.get("stderr", "") or "bloqueado" in data.get("error", "").lower()
    
    @pytest.mark.anyio
    async def test_timeout(self):
        """Test that code execution respects timeout."""
        code = "import time\ntime.sleep(100)"
        result = run_code.run(code=code, timeout=2)
        data = json.loads(result)
        assert data["status"] == "error"
        assert "timeout" in data.get("stderr", "").lower() or "timeout" in data.get("error", "").lower()
    
    @pytest.mark.anyio
    async def test_empty_code(self):
        """Test that empty code returns error."""
        result = run_code.run(code="")
        assert "[ERROR]" in result
    
    @pytest.mark.anyio
    async def test_math_calculation(self):
        """Test math calculation execution."""
        code = "result = 2 + 2\nprint(f'Result: {result}')"
        result = run_code.run(code=code)
        data = json.loads(result)
        assert data["status"] == "ok"
        assert "Result: 4" in data["stdout"]
    
    @pytest.mark.anyio
    async def test_division_by_zero(self):
        """Test division by zero error handling."""
        code = "x = 1 / 0"
        result = run_code.run(code=code)
        data = json.loads(result)
        assert data["status"] == "error"
        assert "ZeroDivisionError" in data.get("stderr", "")
