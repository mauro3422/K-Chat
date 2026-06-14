import pytest
from unittest.mock import AsyncMock
from types import SimpleNamespace

from src.tools._validators import validate_javascript


@pytest.mark.anyio
async def test_validate_javascript_uses_node_check_on_temp_file(monkeypatch):
    seen = {}

    def fake_run(cmd, capture_output, text, timeout):
        seen["cmd"] = cmd
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr("src.tools._validators.subprocess.run", fake_run)

    result = validate_javascript("const x = 1;")

    assert result["status"] == "ok"
    assert seen["cmd"][0] == "node"
    assert seen["cmd"][1] == "--check"
    assert len(seen["cmd"]) == 3
    assert seen["cmd"][2].endswith(".js")


@pytest.mark.anyio
async def test_validate_javascript_reports_syntax_error(monkeypatch):
    def fake_run(cmd, capture_output, text, timeout):
        return SimpleNamespace(returncode=1, stderr="SyntaxError: Unexpected token\n")

    monkeypatch.setattr("src.tools._validators.subprocess.run", fake_run)

    result = validate_javascript("const =")

    assert result["status"] == "error"
    assert "SyntaxError" in result["message"]
