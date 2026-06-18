from unittest.mock import AsyncMock
import pytest

from web.services.stream_contract import (
    STREAM_EVENT_TYPES,
    build_stream_event,
    serialize_stream_event,
)


@pytest.mark.anyio
async def test_stream_event_types_include_expected_entries():
    assert STREAM_EVENT_TYPES == {"heartbeat", "content", "reasoning", "tool_call", "error", "memory", "notification"}


@pytest.mark.anyio
async def test_build_stream_event_rejects_unknown_type():
    with pytest.raises(ValueError):
        build_stream_event("nope", "x")


@pytest.mark.anyio
async def test_serialize_stream_event_roundtrip():
    line = serialize_stream_event("content", "hola")
    assert line.endswith("\n")
    assert '"t": "content"' in line
    assert '"d": "hola"' in line
