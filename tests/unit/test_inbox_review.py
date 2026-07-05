import json

import pytest

from src.memory.curator.inbox_review import (
    find_inbox_group,
    list_inbox_groups,
    promote_inbox_group,
    reject_inbox_group,
)
from src.memory.curator.memory_inbox import append_memory_inbox_item


def test_list_and_find_inbox_groups_coalesces_sources(tmp_path):
    append_memory_inbox_item(
        {"key": "user:lenguaje", "value": "Mauro usa Python."},
        root=tmp_path,
        timestamp="2026-07-03T11:53:11",
    )
    second = append_memory_inbox_item(
        {"key": "user:lenguaje", "value": "Mauro usa Python."},
        root=tmp_path,
        timestamp="2026-07-03T11:53:12",
    )

    groups = list_inbox_groups(root=tmp_path)
    found = find_inbox_group(second["inbox_id"], root=tmp_path)

    assert len(groups) == 1
    assert groups[0]["reinforcement_count"] == 2
    assert found is not None
    assert found["group_id"] == groups[0]["group_id"]


@pytest.mark.anyio
async def test_promote_inbox_group_writes_canonical_and_marks_sources(tmp_path):
    first = append_memory_inbox_item(
        {"key": "user:lenguaje", "value": "Mauro usa Python."},
        root=tmp_path,
        timestamp="2026-07-03T11:53:11",
    )
    append_memory_inbox_item(
        {"key": "user:lenguaje", "value": "Mauro usa Python."},
        root=tmp_path,
        timestamp="2026-07-03T11:53:12",
    )
    writes = []

    async def writer(key, value):
        writes.append((key, value))
        return "[OK] saved"

    result = await promote_inbox_group(
        first["inbox_id"],
        writer,
        root=tmp_path,
        timestamp="2026-07-03T12:00:00",
    )

    assert writes == [("user:lenguaje", "Mauro usa Python.")]
    assert result["status"] == "promoted"
    assert result["updated_count"] == 2
    assert result["decision_event"]["action"] == "promote"
    assert result["decision_event"]["reinforcement_count"] == 2
    assert result["target_id"] == "memory:user:lenguaje"
    assert result["preview_command"] == "curator_workbench action=preview_hints"
    assert result["materialize_command"] == "curator_workbench action=materialize_hints"
    assert result["verify_graph_command"] == "curator_workbench action=graph memory_key=user:lenguaje"
    assert len(result["relation_hints"]) == 3
    assert result["relation_hints"][0]["source_id"].startswith("inbox:")
    assert result["relation_hints"][0]["target_id"] == "memory:user:lenguaje"
    assert result["relation_hints"][0]["relation_type"] == "PROMOTED_TO"
    assert result["decision_event"]["relation_hints"] == result["relation_hints"]

    path = tmp_path / "memory" / "2026" / "07" / "03" / "inbox.jsonl"
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert {record["status"] for record in records} == {"promoted"}
    assert {record["promoted_key"] for record in records} == {"user:lenguaje"}
    assert {record["reviewed_at"] for record in records} == {"2026-07-03T12:00:00"}


def test_reject_inbox_group_marks_all_sources(tmp_path):
    first = append_memory_inbox_item(
        {"key": "noise", "value": "No guardar."},
        root=tmp_path,
        timestamp="2026-07-03T11:53:11",
    )
    append_memory_inbox_item(
        {"key": "noise", "value": "No guardar."},
        root=tmp_path,
        timestamp="2026-07-03T11:53:12",
    )

    result = reject_inbox_group(
        first["inbox_id"],
        "ruido",
        root=tmp_path,
        timestamp="2026-07-03T12:00:00",
    )

    assert result["status"] == "rejected"
    assert result["updated_count"] == 2
    assert result["decision_event"]["action"] == "reject"
    assert list_inbox_groups(root=tmp_path) == []
