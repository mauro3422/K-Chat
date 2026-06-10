from unittest.mock import patch
import json

from web.services.message_persister import save_assistant_message


@patch("web.services.message_persister.save_debug_info")
@patch("web.services.message_persister.db_save_message")
def test_save_with_full_data(mock_db_save, mock_debug_save):
    phases = [{"phase": "reasoning", "content": "thinking..."}]
    debug = {
        "prompt_tokens": 100,
        "completion_tokens": 50,
        "total_tokens": 150,
        "phases": "already set",
    }

    save_assistant_message(
        session_id="s1",
        full_content="Hello!",
        full_reasoning="thinking",
        phases_output=phases,
        debug_info=debug,
        model="gpt-4",
    )

    mock_db_save.assert_called_once_with(
        "s1", "assistant", "Hello!", "gpt-4",
        reasoning="thinking",
        phases=json.dumps(phases, ensure_ascii=False),
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
    )
    mock_debug_save.assert_called_once_with("s1", debug)


@patch("web.services.message_persister.save_debug_info")
@patch("web.services.message_persister.db_save_message")
def test_save_with_empty_debug_info(mock_db_save, mock_debug_save):
    phases = [{"phase": "answer", "content": "done"}]
    debug = {}

    save_assistant_message(
        session_id="s2",
        full_content="Response",
        full_reasoning="",
        phases_output=phases,
        debug_info=debug,
        model="gpt-4",
    )

    mock_db_save.assert_called_once_with(
        "s2", "assistant", "Response", "gpt-4",
        reasoning="",
        phases=json.dumps(phases, ensure_ascii=False),
        prompt_tokens=0,
        completion_tokens=0,
        total_tokens=0,
    )
    saved_debug = mock_debug_save.call_args[0][1]
    assert saved_debug["phases"] == json.dumps(phases, ensure_ascii=False)


@patch("web.services.message_persister.save_debug_info")
@patch("web.services.message_persister.db_save_message")
def test_save_with_empty_phases(mock_db_save, mock_debug_save):
    debug = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}

    save_assistant_message(
        session_id="s3",
        full_content="Short reply",
        full_reasoning="reason",
        phases_output=[],
        debug_info=debug,
        model="gpt-4",
    )

    mock_db_save.assert_called_once_with(
        "s3", "assistant", "Short reply", "gpt-4",
        reasoning="reason",
        phases=json.dumps([], ensure_ascii=False),
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
    )
    saved_debug = mock_debug_save.call_args[0][1]
    assert saved_debug["phases"] == json.dumps([], ensure_ascii=False)


@patch("web.services.message_persister.save_debug_info")
@patch("web.services.message_persister.db_save_message")
def test_existing_phases_not_overwritten(mock_db_save, mock_debug_save):
    phases = [{"phase": "new"}]
    debug = {"phases": "original_value"}

    save_assistant_message(
        session_id="s4",
        full_content="Content",
        full_reasoning="",
        phases_output=phases,
        debug_info=debug,
        model="gpt-4",
    )

    saved_debug = mock_debug_save.call_args[0][1]
    assert saved_debug["phases"] == "original_value"
