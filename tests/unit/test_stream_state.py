import pytest
from unittest.mock import AsyncMock
from web.services.stream_state import StreamState


@pytest.mark.anyio
async def test_stream_state_accumulates_and_resets():
    state = StreamState()

    state.append("content", "hola")
    state.append("reasoning", "pienso")
    state.append("tool_call", "ignored")

    assert state.full_content == "hola"
    assert state.full_reasoning == "pienso"
    assert state.has_output() is True

    state.reset_on_tool_call()

    assert state.full_content == ""
    assert state.full_reasoning == ""
    assert state.has_output() is False


@pytest.mark.anyio
async def test_stream_state_persistence_clock():
    state = StreamState(save_interval=10.0)
    state.append("content", "hola")

    assert state.should_persist(state.last_persisted_at + 9.9) is False
    assert state.should_persist(state.last_persisted_at + 10.1) is True

    state.mark_persisted(state.last_persisted_at + 10.1)
    assert state.persisted is True
    assert state.should_persist(state.last_persisted_at + 1.0) is False
