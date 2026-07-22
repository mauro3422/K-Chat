import json

import pytest

from src.memory.repos import get_repos


@pytest.mark.anyio
async def test_stream_checkpoint_round_trip_and_clear(setup_test_db):
    repos = get_repos()
    await repos.sessions.ensure("checkpoint-session")

    await repos.stream_checkpoints.save(
        "checkpoint-session",
        original_message="investigá esto",
        model="model-a",
        history_json=json.dumps([
            {"role": "user", "content": "investigá esto"},
            {"role": "tool", "content": "resultado", "tool_call_id": "call-1"},
        ]),
        phases_json=json.dumps([{"tool_ids": ["call-1"]}]),
        partial_content="respuesta parcial",
        partial_reasoning="razonamiento parcial",
        status="interrupted",
        checkpoint_kind="tool_phase",
        error_type="network",
        error_message="connection lost",
        retry_count=1,
    )

    checkpoint = await repos.stream_checkpoints.get("checkpoint-session")
    assert checkpoint is not None
    assert checkpoint["original_message"] == "investigá esto"
    assert checkpoint["partial_content"] == "respuesta parcial"
    assert checkpoint["checkpoint_kind"] == "tool_phase"
    assert checkpoint["error_type"] == "network"

    await repos.stream_checkpoints.clear("checkpoint-session")
    assert await repos.stream_checkpoints.get("checkpoint-session") is None
