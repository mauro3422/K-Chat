import json

import pytest

from src.memory.curator.memory_inbox import append_memory_inbox_item
from src.tools.daily_memory_report import DEFINITION, run


def test_definition_structure():
    assert DEFINITION["type"] == "function"
    fdef = DEFINITION["function"]
    assert fdef["name"] == "daily_memory_report"
    assert "write" in fdef["parameters"]["properties"]
    assert "preflight" in fdef["parameters"]["properties"]
    assert fdef["parameters"]["properties"]["preflight"]["default"] is True
    assert "format" in fdef["parameters"]["properties"]
    assert "compact" in fdef["parameters"]["properties"]
    assert "laptop_status_json" in fdef["parameters"]["properties"]
    assert fdef["parameters"]["properties"]["laptop_status_timeout"]["default"] == 45


@pytest.mark.anyio
async def test_preview_daily_memory_report(tmp_path):
    append_memory_inbox_item(
        {"key": "plan:test", "value": "Revisar inbox."},
        root=tmp_path,
        timestamp="2026-07-02T08:00:00",
    )

    result = await run(root=str(tmp_path), date="2026-07-02", write=False)

    assert "Morning Memory Plan - 2026-07-02" in result
    assert "Health" in result
    assert "Memory preflight: " in result
    assert "Memory preflight: not run" not in result
    assert "plan:test" in result


@pytest.mark.anyio
async def test_preview_daily_memory_report_json(tmp_path):
    status_path = tmp_path / "laptop-status.json"
    status_path.write_text('{"available": true, "status": "ok"}', encoding="utf-8")

    result = await run(
        root=str(tmp_path),
        date="2026-07-02",
        write=False,
        format="json",
        laptop_status_json=str(status_path),
    )
    payload = json.loads(result)

    assert payload["date"] == "2026-07-02"
    assert payload["health"]["laptop"]["status"] == "ok"


@pytest.mark.anyio
async def test_preview_daily_memory_report_compact_json(tmp_path):
    append_memory_inbox_item(
        {"key": "plan:test", "value": "Revisar inbox."},
        root=tmp_path,
        timestamp="2026-07-02T08:00:00",
    )

    result = await run(
        root=str(tmp_path),
        date="2026-07-02",
        write=False,
        format="json",
        compact=True,
    )
    payload = json.loads(result)

    assert payload["date"] == "2026-07-02"
    assert payload["summary"].startswith("status=")
    assert payload["risk"]
    assert payload["counts"]["actions"] == 1
    assert payload["runbook"]["top"] == "curator_workbench action=runbook item_id=top"
    assert payload["priorities"][0]["command"].startswith("curator_workbench action=runbook item_id=")
    assert payload["actions"][0]["runbook_command"].startswith("curator_workbench action=runbook item_id=")
    assert "pending_inbox" not in payload


@pytest.mark.anyio
async def test_write_daily_memory_report(tmp_path):
    result = await run(root=str(tmp_path), date="2026-07-02", write=True)

    assert "[OK]" in result
    assert "memory" in result
    assert (tmp_path / "memory" / "plans" / "morning" / "2026" / "07" / "02.md").exists()


@pytest.mark.anyio
async def test_write_daily_memory_report_json(tmp_path):
    result = await run(root=str(tmp_path), date="2026-07-02", write=True, format="json")
    payload = json.loads(result)

    assert payload["ok"] is True
    assert payload["path"].endswith("memory/plans/morning/2026/07/02.md") or payload["path"].endswith(
        "memory\\plans\\morning\\2026\\07\\02.md"
    )
    assert payload["plan"]["date"] == "2026-07-02"


@pytest.mark.anyio
async def test_write_daily_memory_report_compact_json(tmp_path):
    result = await run(root=str(tmp_path), date="2026-07-02", write=True, format="json", compact=True)
    payload = json.loads(result)

    assert payload["ok"] is True
    assert payload["plan"]["date"] == "2026-07-02"
    assert "counts" in payload["plan"]
    assert "priorities" in payload["plan"]
    assert "pending_inbox" not in payload["plan"]
