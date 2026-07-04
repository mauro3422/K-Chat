import json

import scripts.daily_memory_report as script


def _plan():
    return {
        "date": "2026-07-02",
        "pipeline_status": {"status": "attention", "issues": ["inbox pending"]},
        "health": {
            "git": {"branch": "master", "changed": 0, "untracked": 0},
            "preflight": {"ok": True, "issues": [], "snapshot": {}},
            "laptop": {"status": "ok", "available": True, "passed": 3, "total": 3},
        },
        "pending_inbox": [{"id": "i1"}],
        "inbox_groups": [],
        "candidate_cards": [],
        "ready_candidate_cards": [],
        "actions": [
            {
                "priority": 90,
                "kind": "inbox_item",
                "id": "i1",
                "title": "Revisar memoria temporal",
                "recommended_command": "curator_workbench action=preview_inbox item_id=i1",
            }
        ],
    }


def test_preview_compact_json_flag(monkeypatch, capsys, tmp_path):
    calls = {}

    def fake_build_morning_plan(**kwargs):
        calls.update(kwargs)
        return _plan()

    monkeypatch.setattr(script, "build_morning_plan", fake_build_morning_plan)
    monkeypatch.setattr(
        "sys.argv",
        [
            "daily_memory_report.py",
            "--root",
            str(tmp_path),
            "--date",
            "2026-07-02",
            "--preview",
            "--json",
            "--compact-json",
            "--laptop-status-timeout",
            "60",
        ],
    )

    assert script.main() == 0
    payload = json.loads(capsys.readouterr().out)

    assert calls["root"] == str(tmp_path)
    assert calls["target_date"].isoformat() == "2026-07-02"
    assert calls["laptop_status_timeout"] == 60
    assert payload["date"] == "2026-07-02"
    assert payload["summary"] == "status=attention; actions=1; preflight=ok; laptop=ok"
    assert payload["risk"].startswith("Curar cola de memoria")
    assert payload["priorities"][0]["command"] == "curator_workbench action=runbook item_id=i1"
    assert "pending_inbox" not in payload


def test_write_compact_json_flag_wraps_compact_plan(monkeypatch, capsys, tmp_path):
    written_path = tmp_path / "memory" / "plans" / "morning" / "2026" / "07" / "02.md"
    calls = {"build": [], "write": []}

    def fake_write_morning_plan(**kwargs):
        calls["write"].append(kwargs)
        return written_path

    def fake_build_morning_plan(**kwargs):
        calls["build"].append(kwargs)
        return _plan()

    monkeypatch.setattr(script, "write_morning_plan", fake_write_morning_plan)
    monkeypatch.setattr(script, "build_morning_plan", fake_build_morning_plan)
    monkeypatch.setattr(
        "sys.argv",
        [
            "daily_memory_report.py",
            "--root",
            str(tmp_path),
            "--date",
            "2026-07-02",
            "--json",
            "--compact-json",
        ],
    )

    assert script.main() == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["ok"] is True
    assert payload["path"] == str(written_path)
    assert calls["write"][0]["laptop_status_timeout"] == 45
    assert calls["build"][0]["laptop_status_timeout"] == 45
    assert payload["plan"]["summary"] == "status=attention; actions=1; preflight=ok; laptop=ok"
    assert payload["plan"]["priorities"][0]["command"] == "curator_workbench action=runbook item_id=i1"
    assert "pending_inbox" not in payload["plan"]
