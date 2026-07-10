import pytest
from unittest.mock import AsyncMock

from src.memory.curator import tracer


@pytest.mark.anyio
async def test_trace_includes_recall_candidates(monkeypatch):
    monkeypatch.setattr(tracer, "detect_repeated_queries", lambda cfg: [])
    monkeypatch.setattr(tracer, "detect_entity_clusters", lambda cfg: [])
    monkeypatch.setattr(tracer, "detect_debug_sessions", lambda cfg: [])

    async def noop_save(key, value):
        return "[OK]"

    from src.memory.curator import recall_events

    monkeypatch.setattr(
        recall_events,
        "detect_recall_candidates",
        lambda root, lookback_days, limit: [
            {
                "type": "recall_link_candidate",
                "candidate_id": "abc123",
                "relation_type": "LINKS_TO",
                "query": "Kairos memoria",
            }
        ],
    )

    result = await tracer.trace(
        {"dry_run": True, "lookback_days": 7, "max_patterns": 5},
        save_memory_fn=noop_save,
    )

    assert result["total"] == 1
    assert result["count_by_type"]["recall_link_candidate"] == 1
    assert result["patterns"][0]["relation_type"] == "LINKS_TO"


@pytest.mark.anyio
async def test_trace_materializes_recall_candidates_when_not_dry(monkeypatch, tmp_path):
    monkeypatch.setattr(tracer, "detect_repeated_queries", lambda cfg: [])
    monkeypatch.setattr(tracer, "detect_entity_clusters", lambda cfg: [])
    monkeypatch.setattr(tracer, "detect_debug_sessions", lambda cfg: [])

    from src.memory.curator import recall_events

    monkeypatch.setattr(
        recall_events,
        "detect_recall_candidates",
        lambda root, lookback_days, limit: [
            {
                "type": "recall_link_candidate",
                "candidate_id": "abc123",
                "relation_type": "LINKS_TO",
                "query": "Kairos memoria",
            }
        ],
    )

    result = await tracer.trace(
        {
            "dry_run": False,
            "lookback_days": 7,
            "max_patterns": 5,
            "artifact_root": tmp_path,
        },
        save_memory_fn=None,
    )

    assert result["total"] == 1
    files = list((tmp_path / "memory").glob("*/*/*/candidates/recall_links.jsonl"))
    assert len(files) == 1
    assert "abc123" in files[0].read_text(encoding="utf-8")


@pytest.mark.anyio
async def test_trace_materializes_high_signal_patterns_without_saving_memory(monkeypatch, tmp_path):
    save_memory = AsyncMock(return_value="[OK]")
    monkeypatch.setattr(
        tracer,
        "detect_repeated_queries",
        lambda cfg: [
            {
                "type": "repeated_query",
                "query": "memoria por capas",
                "times": 5,
                "sessions": 2,
                "avg_score": 0.8,
            }
        ],
    )
    monkeypatch.setattr(tracer, "detect_entity_clusters", lambda cfg: [])
    monkeypatch.setattr(tracer, "detect_debug_sessions", lambda cfg: [])

    result = await tracer.trace(
        {
            "dry_run": False,
            "lookback_days": 7,
            "max_patterns": 5,
            "artifact_root": tmp_path,
        },
        save_memory_fn=save_memory,
    )

    files = list((tmp_path / "memory").glob("*/*/*/candidates/tracer.jsonl"))

    assert result["candidate_path"]
    assert files
    assert "memoria por capas" in files[0].read_text(encoding="utf-8")
    save_memory.assert_not_awaited()
