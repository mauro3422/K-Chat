from unittest.mock import AsyncMock, patch

import pytest

from src.memory.curator.memory_inbox import append_memory_inbox_item
from src.tools.review_memory_inbox import DEFINITION, run


class FakeMemoryIndex:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.queries = []

    async def search(self, query):
        self.queries.append(query)
        return self.rows


class FakeMemoryRepos:
    def __init__(self, memory_index):
        self.memory_index = memory_index


class FakeRepos:
    def __init__(self, memory_index):
        self.memory = FakeMemoryRepos(memory_index)


def test_definition_structure():
    assert DEFINITION["type"] == "function"
    fdef = DEFINITION["function"]
    assert fdef["name"] == "review_memory_inbox"
    assert "inspect" in fdef["parameters"]["properties"]["action"]["enum"]
    assert "promote" in fdef["parameters"]["properties"]["action"]["enum"]
    assert "reject" in fdef["parameters"]["properties"]["action"]["enum"]
    assert "include_recall_context" in fdef["parameters"]["properties"]


@pytest.mark.anyio
async def test_list_groups(tmp_path):
    append_memory_inbox_item(
        {"key": "user:lenguaje", "value": "Mauro usa Python."},
        root=tmp_path,
        timestamp="2026-07-03T11:53:11",
    )

    result = await run(root=str(tmp_path), action="list")

    assert "Memory inbox groups" in result
    assert "user:lenguaje" in result


@pytest.mark.anyio
async def test_inspect_group_shows_context_and_next_commands(tmp_path):
    item = append_memory_inbox_item(
        {"key": "user:lenguaje", "value": "Mauro usa Python."},
        root=tmp_path,
        timestamp="2026-07-03T11:53:11",
    )

    result = await run(
        root=str(tmp_path),
        action="inspect",
        group_id=item["inbox_id"],
        _repos=FakeRepos(FakeMemoryIndex([])),
    )

    assert "Memory inbox group" in result
    assert "user:lenguaje" in result
    assert "promote_command" in result
    assert "reject_command" in result
    assert "recall_packet" in result
    assert "Canonical Check" in result
    assert "no exact canonical key/value match found" in result
    assert "Decision Guidance" in result
    assert "recommendation: `inspect_context_before_promote`" in result
    assert "safe_next" in result
    assert "after_promote_preview: `curator_workbench action=preview_hints`" in result
    assert "after_promote_materialize: `curator_workbench action=materialize_hints`" in result
    assert "after_materialize_verify: `curator_workbench action=graph memory_key=user:lenguaje`" in result
    assert "inbox_group:" in result
    assert "PROMOTED_TO" in result


@pytest.mark.anyio
async def test_inspect_group_shows_canonical_match_and_changes_guidance(tmp_path):
    item = append_memory_inbox_item(
        {"key": "user:lenguaje", "value": "Mauro usa Python."},
        root=tmp_path,
        timestamp="2026-07-03T11:53:11",
    )
    memory_index = FakeMemoryIndex(
        [
            {
                "key": "user:lenguaje",
                "value": "Mauro usa Python para scripts de memoria.",
                "updated_at": "2026-07-03T12:00:00",
            }
        ]
    )

    result = await run(
        root=str(tmp_path),
        action="inspect",
        group_id=item["inbox_id"],
        _repos=FakeRepos(memory_index),
    )

    assert "Canonical Check" in result
    assert "Mauro usa Python para scripts de memoria." in result
    assert "recommendation: `review_existing_canon`" in result
    assert "reason: `canonical_match_found`" in result
    assert memory_index.queries[0] == "user:lenguaje"


@pytest.mark.anyio
async def test_inspect_group_recommends_promote_when_reinforced(tmp_path):
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

    result = await run(
        root=str(tmp_path),
        action="inspect",
        group_id=first["inbox_id"],
        _repos=FakeRepos(FakeMemoryIndex([])),
    )

    assert "recommendation: `promote_if_context_confirms`" in result
    assert "reason: `reinforced_inbox_signal`" in result


@pytest.mark.anyio
async def test_inspect_group_can_include_recall_context(tmp_path):
    item = append_memory_inbox_item(
        {"key": "user:lenguaje", "value": "Mauro usa Python."},
        root=tmp_path,
        timestamp="2026-07-03T11:53:11",
    )

    async def fake_recall(**kwargs):
        assert kwargs["query"] == "user:lenguaje Mauro usa Python."
        assert kwargs["include_graph_context"] is True
        return "**Resultados para:** Python"

    with patch("src.tools.recall_memories.run", fake_recall):
        result = await run(
            root=str(tmp_path),
            action="inspect",
            group_id=item["inbox_id"],
            include_recall_context=True,
        )

    assert "Recall Context" in result
    assert "**Resultados para:** Python" in result


@pytest.mark.anyio
async def test_promote_group_calls_save_memory_and_marks_items(tmp_path):
    item = append_memory_inbox_item(
        {"key": "user:lenguaje", "value": "Mauro usa Python."},
        root=tmp_path,
        timestamp="2026-07-03T11:53:11",
    )
    save_memory = AsyncMock(return_value="[OK] saved")

    with patch("src.tools.save_memory.run", save_memory):
        result = await run(
            root=str(tmp_path),
            action="promote",
            group_id=item["inbox_id"],
            _force_local_write=True,
        )

    assert "[OK] Promoted inbox group" in result
    assert "target=`memory:user:lenguaje`" in result
    assert "relations=2" in result
    assert "next=`curator_workbench action=preview_hints`" in result
    assert "then=`curator_workbench action=materialize_hints`" in result
    assert "verify=`curator_workbench action=graph memory_key=user:lenguaje`" in result
    save_memory.assert_awaited_once()
    kwargs = save_memory.await_args.kwargs
    assert kwargs["key"] == "user:lenguaje"
    assert kwargs["value"] == "Mauro usa Python."
    assert kwargs["scope"] == "canonical"

    list_result = await run(root=str(tmp_path), action="list")
    assert "No memory inbox groups found." in list_result


@pytest.mark.anyio
async def test_reject_group_marks_items(tmp_path):
    item = append_memory_inbox_item(
        {"key": "noise", "value": "No guardar."},
        root=tmp_path,
        timestamp="2026-07-03T11:53:11",
    )

    result = await run(
        root=str(tmp_path),
        action="reject",
        group_id=item["inbox_id"],
        reason="ruido",
    )

    assert "[OK] Rejected inbox group" in result
    list_result = await run(root=str(tmp_path), action="list")
    assert "No memory inbox groups found." in list_result
