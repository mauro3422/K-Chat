import json
from pathlib import Path

import pytest

from src.coordination.memory_write_queue import (
    get_memory_write_queue,
    reset_memory_write_queue,
)


@pytest.fixture(autouse=True)
def _reset_queue_state():
    reset_memory_write_queue()
    yield
    reset_memory_write_queue()


@pytest.mark.anyio
async def test_memory_write_queue_persists_and_reloads(monkeypatch, tmp_path):
    queue_path = tmp_path / "queue.json"
    monkeypatch.setenv("KAIROS_MEMORY_WRITE_QUEUE_PATH", str(queue_path))

    queue = get_memory_write_queue()
    queued = queue.enqueue("Preferencia", "Python", source_node="node-a", reason="primary_unavailable")
    assert queued.key == "Preferencia"
    assert queue_path.exists()

    raw = json.loads(queue_path.read_text(encoding="utf-8"))
    assert raw[0]["key"] == "Preferencia"
    assert raw[0]["value"] == "Python"

    reset_memory_write_queue()
    reloaded = get_memory_write_queue()
    snapshot = reloaded.snapshot()
    assert len(snapshot) == 1
    assert snapshot[0]["key"] == "Preferencia"
    assert snapshot[0]["reason"] == "primary_unavailable"


@pytest.mark.anyio
async def test_memory_write_queue_drain_persists_empty_state(monkeypatch, tmp_path):
    queue_path = tmp_path / "queue.json"
    monkeypatch.setenv("KAIROS_MEMORY_WRITE_QUEUE_PATH", str(queue_path))

    queue = get_memory_write_queue()
    queue.enqueue("Preferencia", "Python")
    drained = queue.drain()
    assert len(drained) == 1
    assert queue.snapshot() == []

    raw = json.loads(queue_path.read_text(encoding="utf-8"))
    assert raw == []
