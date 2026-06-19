import pytest
from unittest.mock import AsyncMock, MagicMock
from unittest.mock import patch
import json

from src.core.debug_info import DebugInfo
from src.memory.repos import MessageRecord
from web.services.message_persister_contract import MessagePersisterDeps
from web.services.message_persister import save_assistant_message


@patch("web.services.message_persister.get_repos")
@pytest.mark.anyio
async def test_save_with_full_data(mock_get_repos):
    phases = [{"phase": "reasoning", "content": "thinking..."}]
    debug = DebugInfo(
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
        phases="already set",
    )
    mock_repos = MagicMock()
    mock_repos.messages.save_record = AsyncMock()
    mock_repos.debug.save_info = AsyncMock()
    mock_get_repos.return_value = mock_repos

    await save_assistant_message(
        session_id="s1",
        user_msg="hello",
        full_content="Hello!",
        full_reasoning="thinking",
        phases_output=phases,
        debug_info=debug,
        model="gpt-4",
    )

    saved_record = mock_repos.messages.save_record.call_args[0][0]
    assert isinstance(saved_record, MessageRecord)
    assert saved_record.session_id == "s1"
    assert saved_record.role == "assistant"
    assert saved_record.content == "Hello!"
    assert saved_record.model == "gpt-4"
    assert saved_record.reasoning == "thinking"
    assert saved_record.phases == json.dumps(phases, ensure_ascii=False)
    assert saved_record.prompt_tokens == 100
    assert saved_record.completion_tokens == 50
    assert saved_record.total_tokens == 150
    saved_debug = mock_repos.debug.save_info.call_args[0][1]
    assert saved_debug["prompt_tokens"] == 100
    assert saved_debug["phases"] == "already set"


@patch("web.services.message_persister.get_repos")
@pytest.mark.anyio
async def test_save_with_empty_debug_info(mock_get_repos):
    phases = [{"phase": "answer", "content": "done"}]
    debug = DebugInfo()
    mock_repos = MagicMock()
    mock_repos.messages.save_record = AsyncMock()
    mock_repos.debug.save_info = AsyncMock()
    mock_get_repos.return_value = mock_repos

    await save_assistant_message(
        session_id="s2",
        user_msg="hi",
        full_content="Response",
        full_reasoning="",
        phases_output=phases,
        debug_info=debug,
        model="gpt-4",
    )

    saved_record = mock_repos.messages.save_record.call_args[0][0]
    assert saved_record.content == "Response"
    assert saved_record.reasoning == ""
    assert saved_record.phases == json.dumps(phases, ensure_ascii=False)
    saved_debug = mock_repos.debug.save_info.call_args[0][1]
    assert saved_debug["phases"] == json.dumps(phases, ensure_ascii=False)


@patch("web.services.message_persister.get_repos")
@pytest.mark.anyio
async def test_save_with_empty_phases(mock_get_repos):
    debug = DebugInfo(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    mock_repos = MagicMock()
    mock_repos.messages.save_record = AsyncMock()
    mock_repos.debug.save_info = AsyncMock()
    mock_get_repos.return_value = mock_repos

    await save_assistant_message(
        session_id="s3",
        user_msg="hey",
        full_content="Short reply",
        full_reasoning="reason",
        phases_output=[],
        debug_info=debug,
        model="gpt-4",
    )

    saved_record = mock_repos.messages.save_record.call_args[0][0]
    assert saved_record.content == "Short reply"
    assert saved_record.reasoning == "reason"
    assert saved_record.phases == json.dumps([], ensure_ascii=False)
    saved_debug = mock_repos.debug.save_info.call_args[0][1]
    assert saved_debug["phases"] == json.dumps([], ensure_ascii=False)


@patch("web.services.message_persister.get_repos")
@pytest.mark.anyio
async def test_existing_phases_not_overwritten(mock_get_repos):
    phases = [{"phase": "new"}]
    debug = DebugInfo(phases="original_value")
    mock_repos = MagicMock()
    mock_repos.messages.save_record = AsyncMock()
    mock_repos.debug.save_info = AsyncMock()
    mock_get_repos.return_value = mock_repos

    await save_assistant_message(
        session_id="s4",
        user_msg="question",
        full_content="Content",
        full_reasoning="",
        phases_output=phases,
        debug_info=debug,
        model="gpt-4",
    )

    saved_debug = mock_repos.debug.save_info.call_args[0][1]
    assert saved_debug["phases"] == "original_value"


@pytest.mark.anyio
async def test_save_assistant_message_with_explicit_deps():
    captured = {}

    class FakeRecord:
        def __init__(self, **kwargs):
            captured["record_kwargs"] = kwargs

    async def save_message_fn(record):
        captured["record"] = record

    def save_debug_fn(session_id, debug_info):
        captured["debug"] = (session_id, debug_info)

    debug = DebugInfo(prompt_tokens=1, completion_tokens=2, total_tokens=3)
    phases = [{"phase": "answer", "content": "done"}]

    await save_assistant_message(
        session_id="s5",
        user_msg="hello",
        full_content="Ok",
        full_reasoning="",
        phases_output=phases,
        debug_info=debug,
        model="gpt-4",
        deps=MessagePersisterDeps(
            save_message_fn=save_message_fn,
            save_debug_fn=save_debug_fn,
            message_record_cls=FakeRecord,
        ),
    )

    assert "record" in captured
    assert captured["record_kwargs"]["session_id"] == "s5"
    assert captured["record_kwargs"]["content"] == "Ok"
    assert captured["debug"][0] == "s5"
