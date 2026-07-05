import json

import pytest

from src.memory.curator.curation_events import (
    append_curation_decision,
    curation_decision_path,
    curation_report_path,
    load_curation_decisions,
    materialize_relation_hints,
    tracer_candidate_path,
    tracer_candidates_from_patterns,
    upsert_curator_relation,
    write_curation_report,
    write_tracer_candidates,
)


def test_curation_report_path_uses_daily_partition(tmp_path):
    path = curation_report_path("2026-07-02T09:30:00", root=tmp_path)

    assert path == tmp_path / "memory" / "2026" / "07" / "02" / "events" / "curation.md"


def test_curation_decision_path_uses_daily_partition(tmp_path):
    path = curation_decision_path("2026-07-02T09:30:00", root=tmp_path)

    assert path == (
        tmp_path
        / "memory"
        / "2026"
        / "07"
        / "02"
        / "events"
        / "decisions.jsonl"
    )


def test_append_and_load_curation_decision(tmp_path):
    payload = append_curation_decision(
        {"kind": "memory_inbox", "action": "promote", "group_id": "g1"},
        root=tmp_path,
        timestamp="2026-07-02T09:30:00",
    )

    decisions = load_curation_decisions(root=tmp_path)

    assert "events" in payload["artifact"] and payload["artifact"].endswith("decisions.jsonl")
    assert decisions[0]["kind"] == "memory_inbox"
    assert decisions[0]["action"] == "promote"
    assert decisions[0]["group_id"] == "g1"


def test_write_curation_report_writes_markdown_with_metadata(tmp_path):
    path = write_curation_report(
        ["# report", "- ok"],
        {"entries": 1},
        root=tmp_path,
        timestamp="2026-07-02T09:30:00",
    )

    text = path.read_text(encoding="utf-8")

    assert "# report" in text
    assert '"entries": 1' in text


def test_tracer_candidate_path_uses_daily_partition(tmp_path):
    path = tracer_candidate_path("2026-07-02T09:30:00", root=tmp_path)

    assert path == tmp_path / "memory" / "2026" / "07" / "02" / "candidates" / "tracer.jsonl"


def test_tracer_candidates_from_patterns_filters_low_signal():
    candidates = tracer_candidates_from_patterns([
        {"type": "repeated_query", "query": "low", "times": 2},
        {"type": "repeated_query", "query": "high", "times": 5, "avg_score": 0.8},
        {"type": "debug_session", "session_id": "abcdef123456"},
    ])

    assert [c["pattern_type"] for c in candidates] == ["repeated_query", "debug_session"]
    assert candidates[1]["urgency"] == "high"


def test_write_tracer_candidates_writes_jsonl(tmp_path):
    path = write_tracer_candidates(
        [{"candidate_id": "abc", "type": "tracer_pattern_candidate"}],
        root=tmp_path,
        timestamp="2026-07-02T09:30:00",
    )

    payload = json.loads(path.read_text(encoding="utf-8").splitlines()[0])

    assert payload["candidate_id"] == "abc"
    assert payload["created_at"] == "2026-07-02T09:30:00"


class FakeEntityRepo:
    def __init__(self):
        self.calls = []
        self.curated_calls = []

    async def upsert_relation(self, **kwargs):
        self.calls.append(kwargs)

    async def upsert_curated_relation(self, **kwargs):
        self.curated_calls.append(kwargs)
        return f"rel-{len(self.curated_calls)}"


@pytest.mark.anyio
async def test_materialize_relation_hints_writes_graph_relations(tmp_path):
    append_curation_decision(
        {
            "kind": "memory_inbox",
            "action": "promote",
            "group_id": "g1",
            "value": "Mauro usa Python.",
            "reinforcement_count": 2,
            "relation_hints": [
                {
                    "source_id": "inbox:i1",
                    "target_id": "memory:user:lenguaje",
                    "relation_type": "PROMOTED_TO",
                },
                {
                    "source_id": "inbox:i1",
                    "target_id": "memory:user:lenguaje",
                    "relation_type": "PROMOTED_TO",
                },
            ],
        },
        root=tmp_path,
        timestamp="2026-07-02T10:00:00",
    )
    repo = FakeEntityRepo()

    result = await materialize_relation_hints(
        repo,
        root=tmp_path,
        timestamp="2026-07-02T11:00:00",
    )

    assert result["materialized"] == 1
    assert result["skipped"] == 1
    assert repo.calls == [
        {
            "source_id": "inbox:i1",
            "target_id": "memory:user:lenguaje",
            "relation_type": "PROMOTED_TO",
            "weight": 2.0,
            "timestamp": "2026-07-02T11:00:00",
        }
    ]
    assert repo.curated_calls[0]["candidate_id"] == "g1"
    assert repo.curated_calls[0]["provenance"]["source"] == "curation_decision_relation_hint"
    assert repo.curated_calls[0]["metadata"]["relation_hint"]["source_id"] == "inbox:i1"


@pytest.mark.anyio
async def test_materialize_relation_hints_dry_run_previews_without_writes(tmp_path):
    append_curation_decision(
        {
            "kind": "memory_inbox",
            "action": "promote",
            "group_id": "g1",
            "value": "Mauro usa Python.",
            "reinforcement_count": 2,
            "relation_hints": [
                {
                    "source_id": "inbox:i1",
                    "target_id": "memory:user:lenguaje",
                    "relation_type": "PROMOTED_TO",
                }
            ],
        },
        root=tmp_path,
        timestamp="2026-07-02T10:00:00",
    )
    repo = FakeEntityRepo()

    result = await materialize_relation_hints(
        repo,
        root=tmp_path,
        timestamp="2026-07-02T11:00:00",
        dry_run=True,
    )

    assert result["dry_run"] is True
    assert result["materialized"] == 0
    assert result["previewed"] == 1
    assert result["relations"][0]["dry_run"] is True
    assert result["relations"][0]["candidate_id"] == "g1"
    assert repo.calls == []
    assert repo.curated_calls == []


@pytest.mark.anyio
async def test_upsert_curator_relation_writes_graph_and_decision(tmp_path):
    repo = FakeEntityRepo()

    result = await upsert_curator_relation(
        repo,
        source_id="memory:user:pref",
        target_id="entity:kairos",
        relation_type="supports",
        weight=0.82,
        evidence="Mauro reforzo esta preferencia.",
        reason="manual curator link",
        candidate_id="cand-1",
        root=tmp_path,
        timestamp="2026-07-02T11:00:00",
    )

    assert result["relation_type"] == "SUPPORTS"
    assert result["curated_relation_id"] == "rel-1"
    assert repo.calls == [
        {
            "source_id": "memory:user:pref",
            "target_id": "entity:kairos",
            "relation_type": "SUPPORTS",
            "weight": 0.82,
            "timestamp": "2026-07-02T11:00:00",
        }
    ]
    assert repo.curated_calls[0]["candidate_id"] == "cand-1"
    assert repo.curated_calls[0]["evidence"] == "Mauro reforzo esta preferencia."
    assert repo.curated_calls[0]["provenance"]["source"] == "curator_relation_upsert"
    decisions = load_curation_decisions(root=tmp_path)
    assert decisions[0]["action"] == "upsert_relation"
    assert decisions[0]["curated_relation_id"] == "rel-1"
