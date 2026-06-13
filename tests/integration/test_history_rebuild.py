import os
import json
import tempfile


from src.api.messages import save_message_record, get_session_messages
from src.api.session import ensure_session
from src.core.history_rebuilder import rebuild_history
from src.memory.schema import init_db
from src.memory.repos import get_repos
from src.memory.repos import MessageRecord
from src.tools.read_file import run as read_file_run
from src.tools.write_file import run as write_file_run


def save_message(
    session_id,
    role,
    content,
    model,
    reasoning="",
    phases="[]",
    tool_calls=None,
    tool_call_id=None,
    **kwargs,
):
    return save_message_record(MessageRecord(
        session_id=session_id,
        role=role,
        content=content,
        model=model,
        reasoning=reasoning,
        phases=phases,
        tool_calls=tool_calls,
        tool_call_id=tool_call_id,
    ))


def test_read_write_file_tools():
    """Verify that read_file and write_file tools work as expected."""
    temp_dir = tempfile.mkdtemp()
    test_file_path = os.path.join(temp_dir, "test_tool_file.txt")
    test_content = "Hola Mundo 123"

    # Write file
    write_res = write_file_run(path=test_file_path, content=test_content)
    assert "[OK]" in write_res
    assert os.path.exists(test_file_path)

    # Read file
    read_res = read_file_run(path=test_file_path)
    assert "[File: " in read_res
    assert "1: Hola Mundo 123" in read_res


def test_read_file_pagination_and_numbering():
    """Verify pagination and line numbering in read_file."""
    temp_dir = tempfile.mkdtemp()
    test_file_path = os.path.join(temp_dir, "test_pagination.txt")
    test_content = "Linea Uno\nLinea Dos\nLinea Tres\nLinea Cuatro"

    # Write
    write_file_run(path=test_file_path, content=test_content)

    # Read range 2 to 3
    res_range = read_file_run(path=test_file_path, start_line=2, end_line=3)
    assert "[File: " in res_range
    assert "Total lines: 4" in res_range
    assert "Displayed range: 2-3" in res_range
    assert "1: Linea Uno" not in res_range
    assert "2: Linea Dos\n" in res_range
    assert "3: Linea Tres\n" in res_range
    assert "4: Linea Cuatro" not in res_range



def test_history_rebuild_preserves_tools():
    """Verify that saving and rebuilding history preserves tool calls and tool responses."""
    session_id = "test-session-history-tools"
    ensure_session(session_id)

    # 1. Save user message
    save_message(session_id, "user", "Hola, guarda esto", "test-model")

    # 2. Save assistant message with tool calls
    tcs = [
        {
            "id": "call_abc123",
            "type": "function",
            "function": {
                "name": "save_memory",
                "arguments": '{"key":"preferencia","value":"mate"}'
            }
        }
    ]
    save_message(
        session_id,
        "assistant",
        None,
        model="test-model",
        tool_calls=json.dumps(tcs)
    )

    # 3. Save tool response
    save_message(
        session_id,
        "tool",
        "Éxito: Se ha guardado en MEMORY.md",
        model=None,
        tool_call_id="call_abc123"
    )

    # 4. Save final assistant response
    save_message(
        session_id,
        "assistant",
        "Listo, ya lo guardé en tu memoria.",
        model="test-model"
    )

    # 5. Fetch messages from database
    msgs = get_session_messages(session_id)
    assert len(msgs) == 4

    # Check that tool_calls and tool_call_id columns are retrieved correctly
    # msgs columns are: role, content, model, created_at, reasoning, phases, tool_calls, tool_call_id
    assert msgs[0][0] == "user"
    assert msgs[0][1] == "Hola, guarda esto"

    assert msgs[1][0] == "assistant"
    assert msgs[1][1] is None or msgs[1][1] == ""
    assert msgs[1][6] is not None
    assert "call_abc123" in msgs[1][6]

    assert msgs[2][0] == "tool"
    assert msgs[2][1] == "Éxito: Se ha guardado en MEMORY.md"
    assert msgs[2][7] == "call_abc123"

    assert msgs[3][0] == "assistant"
    assert msgs[3][1] == "Listo, ya lo guardé en tu memoria."

    # 6. Rebuild history for next turn
    history = rebuild_history(session_id, "test-model", messages_repo=get_repos().messages)
    
    # Assert rebuild_history formats everything correctly for OpenAI/OpenCode API
    # First message in history is the system prompt, so we skip it
    assert len(history) == 5
    assert history[0]["role"] == "system"
    
    assert history[1]["role"] == "user"
    assert history[1]["content"].endswith("Hola, guarda esto")
    assert history[1]["content"].startswith("[")

    assert history[2]["role"] == "assistant"
    assert history[2]["content"] is None
    assert len(history[2]["tool_calls"]) == 1
    assert history[2]["tool_calls"][0]["id"] == "call_abc123"
    assert history[2]["tool_calls"][0]["function"]["name"] == "save_memory"

    assert history[3]["role"] == "tool"
    assert history[3]["content"].endswith("Éxito: Se ha guardado en MEMORY.md")
    assert history[3]["tool_call_id"] == "call_abc123"
    assert history[3]["content"].startswith("[")

    assert history[4]["role"] == "assistant"
    assert history[4]["content"].endswith("Listo, ya lo guardé en tu memoria.")
    assert history[4]["content"].startswith("[")


def test_history_rebuild_sanitizes_orphaned_tools():
    """Verify that rebuilding history filters out assistant messages with orphaned tool calls."""
    session_id = "test-session-orphaned-tools"
    ensure_session(session_id)

    # 1. Save user message
    save_message(session_id, "user", "Hola, guarda esto", "test-model")

    # 2. Save assistant message with an ORPHANED tool call (no tool response will be saved for this)
    tcs_orphaned = [
        {
            "id": "call_orphaned_123",
            "type": "function",
            "function": {
                "name": "save_memory",
                "arguments": '{"key":"temp","value":"lost"}'
            }
        }
    ]
    save_message(
        session_id,
        "assistant",
        None,
        model="test-model",
        tool_calls=json.dumps(tcs_orphaned)
    )

    # 3. Save assistant message with a VALID tool call
    tcs_valid = [
        {
            "id": "call_valid_456",
            "type": "function",
            "function": {
                "name": "save_memory",
                "arguments": '{"key":"preferencia","value":"mate"}'
            }
        }
    ]
    save_message(
        session_id,
        "assistant",
        None,
        model="test-model",
        tool_calls=json.dumps(tcs_valid)
    )

    # 4. Save tool response for the valid tool call
    save_message(
        session_id,
        "tool",
        "Éxito: Se ha guardado en MEMORY.md",
        model=None,
        tool_call_id="call_valid_456"
    )

    # Rebuild history
    history = rebuild_history(session_id, "test-model", messages_repo=get_repos().messages)

    # The rebuilt history should contain:
    # 0. System prompt
    # 1. User message
    # 2. Valid Assistant message (orphaned assistant message should be removed!)
    # 3. Valid Tool response
    assert len(history) == 4
    assert history[0]["role"] == "system"
    
    assert history[1]["role"] == "user"
    assert history[1]["content"].endswith("Hola, guarda esto")

    assert history[2]["role"] == "assistant"
    assert history[2]["content"] is None
    assert len(history[2]["tool_calls"]) == 1
    assert history[2]["tool_calls"][0]["id"] == "call_valid_456"

    assert history[3]["role"] == "tool"
    assert history[3]["content"].endswith("Éxito: Se ha guardado en MEMORY.md")
    assert history[3]["tool_call_id"] == "call_valid_456"
