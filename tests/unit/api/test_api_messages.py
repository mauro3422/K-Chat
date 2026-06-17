import pytest
from unittest.mock import AsyncMock, MagicMock

from src._types import MessageRecord
from src.api.messages import save_message_record, get_session_messages


@pytest.mark.anyio
async def test_save_message_record_calls_save_record():
    repos = MagicMock()
    repos.messages = AsyncMock()

    record = MessageRecord(
        session_id="sess-1",
        role="user",
        content="hello",
        model="gpt-4",
    )

    await save_message_record(record, repos=repos)

    repos.messages.save_record.assert_awaited_once_with(record)


@pytest.mark.anyio
async def test_save_message_record_with_tool_calls():
    repos = MagicMock()
    repos.messages = AsyncMock()

    record = MessageRecord(
        session_id="sess-1",
        role="assistant",
        content="using tools",
        tool_calls='[{"id": "call_1", "function": {"name": "test_tool"}}]',
        tool_call_id=None,
    )

    await save_message_record(record, repos=repos)

    repos.messages.save_record.assert_awaited_once_with(record)


@pytest.mark.anyio
async def test_save_message_record_empty_session_id():
    repos = MagicMock()
    repos.messages = AsyncMock()

    record = MessageRecord(
        session_id="",
        role="user",
        content="no session",
    )

    await save_message_record(record, repos=repos)

    repos.messages.save_record.assert_awaited_once_with(record)


@pytest.mark.anyio
async def test_get_session_messages_calls_repo():
    repos = MagicMock()
    repos.messages = AsyncMock()
    repos.messages.get_session_messages = AsyncMock(
        return_value=[{"role": "user", "content": "hi"}]
    )

    result = await get_session_messages("sess-1", repos=repos)

    repos.messages.get_session_messages.assert_awaited_once_with("sess-1", 500)
    assert result == [{"role": "user", "content": "hi"}]


@pytest.mark.anyio
async def test_get_session_messages_with_custom_limit():
    repos = MagicMock()
    repos.messages = AsyncMock()
    repos.messages.get_session_messages = AsyncMock(return_value=[])

    result = await get_session_messages("sess-1", limit=10, repos=repos)

    repos.messages.get_session_messages.assert_awaited_once_with("sess-1", 10)
    assert result == []


@pytest.mark.anyio
async def test_get_session_messages_empty_session():
    repos = MagicMock()
    repos.messages = AsyncMock()
    repos.messages.get_session_messages = AsyncMock(return_value=[])

    result = await get_session_messages("", repos=repos)

    repos.messages.get_session_messages.assert_awaited_once_with("", 500)
    assert result == []


@pytest.mark.anyio
async def test_save_message_record_propagates_exception():
    repos = MagicMock()
    repos.messages = AsyncMock()
    repos.messages.save_record = AsyncMock(side_effect=ValueError("db error"))

    record = MessageRecord(session_id="sess-1", role="user", content="boom")

    with pytest.raises(ValueError, match="db error"):
        await save_message_record(record, repos=repos)
