import json

import scripts.generate_session_summaries as script


def test_daily_synthesis_and_curation_report_flags(monkeypatch, capsys, tmp_path):
    calls = {}

    async def fake_generate_session_summaries(db_path, root=None, target_date=None):
        calls["summaries"] = {"db_path": db_path, "root": root, "target_date": target_date}
        return []

    async def fake_generate_daily_synthesis(db_path, root=None, target_date=None):
        calls["daily"] = {"db_path": db_path, "root": root, "target_date": target_date}
        return str(tmp_path / "memory" / "2026" / "07" / "02" / "daily.md")

    monkeypatch.setattr(script, "resolve_db_path", lambda: "sessions.db")
    monkeypatch.setattr(script, "generate_session_summaries", fake_generate_session_summaries)
    monkeypatch.setattr(script, "generate_daily_synthesis", fake_generate_daily_synthesis)
    monkeypatch.setattr(
        "sys.argv",
        [
            "generate_session_summaries.py",
            "--root",
            str(tmp_path),
            "--date",
            "2026-07-02",
            "--daily-synthesis",
            "--curation-report",
            "--json",
        ],
    )

    assert script.main() == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["daily_synthesis"].endswith("daily.md")
    assert payload["curation_report"].endswith("curation.md")
    assert calls["daily"]["db_path"] == "sessions.db"
    assert calls["daily"]["root"] == str(tmp_path)
    assert calls["daily"]["target_date"].isoformat() == "2026-07-02"
    report_path = tmp_path / "memory" / "2026" / "07" / "02" / "events" / "curation.md"
    assert report_path.exists()
    assert "Morning Memory Pipeline" in report_path.read_text(encoding="utf-8")


def test_embed_candidates_flag(monkeypatch, capsys, tmp_path):
    calls = {}

    async def fake_generate_session_summaries(db_path, root=None, target_date=None):
        calls["summaries"] = {"db_path": db_path, "root": root, "target_date": target_date}
        return []

    async def fake_vectorize_memory_candidates(root=None):
        calls["candidate_embedding"] = {"root": root}
        return {"candidates": 1, "embedded": 1, "deduped": 0, "unchanged": 0, "failed": 0}

    monkeypatch.setattr(script, "resolve_db_path", lambda: "sessions.db")
    monkeypatch.setattr(script, "generate_session_summaries", fake_generate_session_summaries)
    monkeypatch.setattr(script, "vectorize_memory_candidates", fake_vectorize_memory_candidates)
    monkeypatch.setattr(
        "sys.argv",
        [
            "generate_session_summaries.py",
            "--root",
            str(tmp_path),
            "--embed-candidates",
            "--json",
        ],
    )

    assert script.main() == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["candidate_embedding"]["embedded"] == 1
    assert calls["candidate_embedding"]["root"] == str(tmp_path)


def test_embed_inbox_flag(monkeypatch, capsys, tmp_path):
    calls = {}

    async def fake_generate_session_summaries(db_path, root=None, target_date=None):
        calls["summaries"] = {"db_path": db_path, "root": root, "target_date": target_date}
        return []

    async def fake_vectorize_memory_inbox_items(root=None):
        calls["inbox_embedding"] = {"root": root}
        return {"inbox_items": 1, "embedded": 1, "deduped": 0, "unchanged": 0, "failed": 0}

    monkeypatch.setattr(script, "resolve_db_path", lambda: "sessions.db")
    monkeypatch.setattr(script, "generate_session_summaries", fake_generate_session_summaries)
    monkeypatch.setattr(script, "vectorize_memory_inbox_items", fake_vectorize_memory_inbox_items)
    monkeypatch.setattr(
        "sys.argv",
        [
            "generate_session_summaries.py",
            "--root",
            str(tmp_path),
            "--embed-inbox",
            "--json",
        ],
    )

    assert script.main() == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["inbox_embedding"]["embedded"] == 1
    assert calls["inbox_embedding"]["root"] == str(tmp_path)


def test_conceptual_pipeline_flags_and_queue(monkeypatch, capsys, tmp_path):
    async def fake_generate_session_summaries(db_path, root=None, target_date=None):
        return []

    async def fake_generate_conceptual_synthesis(target_date, root=None):
        return str(tmp_path / "memory" / "2026" / "07" / "02" / "conceptual.md")

    async def fake_vectorize_conceptual(root):
        return {"artifacts": 1, "embedded": 1, "deduped": 0, "unchanged": 0, "failed": 0}

    monkeypatch.setattr(script, "resolve_db_path", lambda: "sessions.db")
    monkeypatch.setattr(script, "generate_session_summaries", fake_generate_session_summaries)
    monkeypatch.setattr(script, "generate_conceptual_synthesis", fake_generate_conceptual_synthesis)
    monkeypatch.setattr(script, "vectorize_conceptual_synthesis_artifacts", fake_vectorize_conceptual)
    monkeypatch.setattr(script, "build_queue", lambda root: tmp_path / "memory" / "curator-review-queue.jsonl")
    monkeypatch.setattr(
        "sys.argv",
        [
            "generate_session_summaries.py",
            "--root", str(tmp_path),
            "--date", "2026-07-02",
            "--conceptual-synthesis",
            "--embed-conceptual",
            "--curator-review-queue",
            "--json",
        ],
    )

    assert script.main() == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["conceptual_synthesis"].endswith("conceptual.md")
    assert payload["conceptual_embedding"]["embedded"] == 1
    assert payload["curator_review_queue"].endswith("curator-review-queue.jsonl")


def test_conceptual_pipeline_without_date_uses_default_target(monkeypatch, capsys, tmp_path):
    seen = {}

    async def fake_generate_session_summaries(db_path, root=None, target_date=None):
        seen["summaries"] = {"db_path": db_path, "root": root, "target_date": target_date}
        return []

    async def fake_generate_conceptual_synthesis(target_date, root=None):
        seen["conceptual"] = {"target_date": target_date, "root": root}
        return str(tmp_path / "memory" / "2026" / "07" / "12" / "conceptual.md")

    monkeypatch.setattr(script, "resolve_db_path", lambda: "sessions.db")
    monkeypatch.setattr(script, "generate_session_summaries", fake_generate_session_summaries)
    monkeypatch.setattr(script, "generate_conceptual_synthesis", fake_generate_conceptual_synthesis)
    monkeypatch.setattr(
        "sys.argv",
        [
            "generate_session_summaries.py",
            "--root",
            str(tmp_path),
            "--conceptual-synthesis",
            "--json",
        ],
    )

    assert script.main() == 0
    payload = json.loads(capsys.readouterr().out)

    assert seen["conceptual"]["target_date"] is None
    assert seen["conceptual"]["root"] == str(tmp_path)
    assert payload["conceptual_synthesis"].endswith("conceptual.md")
