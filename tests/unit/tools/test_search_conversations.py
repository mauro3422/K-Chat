import pytest
from unittest.mock import AsyncMock, MagicMock

from src.tools.search_conversations import run, DEFINITION


def test_definition_structure():
    assert DEFINITION["type"] == "function"
    fdef = DEFINITION["function"]
    assert fdef["name"] == "search_conversations"
    props = fdef["parameters"]["properties"]
    assert props["query"]["type"] == "string"
    assert "query" in fdef["parameters"]["required"]
    assert props["role"]["default"] == "all"
    assert props["context"]["default"] == 1
    assert props["max_matches"]["default"] == 20
    assert props["case_sensitive"]["default"] is False


@pytest.mark.anyio
async def test_empty_query_returns_error():
    result = await run(query="  ", _repos=MagicMock())
    assert result.startswith("[ERROR]")
    assert "vacía" in result


@pytest.mark.anyio
async def test_no_repos_returns_error():
    result = await run(query="hello", _repos=None)
    assert result.startswith("[ERROR] Repositorios")


@pytest.mark.anyio
async def test_no_messages_in_db():
    repos = MagicMock()
    mock_conn = AsyncMock()
    mock_conn.close = AsyncMock()
    mock_cursor = AsyncMock()
    mock_cursor.fetchall = AsyncMock(return_value=[])
    mock_conn.execute = AsyncMock(return_value=mock_cursor)
    repos.messages._get_conn = AsyncMock(return_value=mock_conn)

    result = await run(query="test", _repos=repos)
    assert "[OK] No hay mensajes" in result


@pytest.mark.anyio
async def test_no_matches_returns_message():
    repos = MagicMock()
    mock_conn = AsyncMock()
    mock_conn.close = AsyncMock()
    mock_cursor = AsyncMock()
    mock_cursor.fetchall = AsyncMock(return_value=[
        {"id": 1, "session_id": "s1", "role": "user",
         "content": "hello world", "created_at": "2024-01-01 12:00:00",
         "session_name": "Chat1"},
    ])
    mock_conn.execute = AsyncMock(return_value=mock_cursor)
    repos.messages._get_conn = AsyncMock(return_value=mock_conn)

    result = await run(query="xyz", _repos=repos)
    assert "No se encontraron" in result


def _make_repos(rows: list[dict]) -> MagicMock:
    repos = MagicMock()
    mock_conn = AsyncMock()
    mock_conn.close = AsyncMock()
    mock_cursor = AsyncMock()
    mock_cursor.fetchall = AsyncMock(return_value=rows)
    mock_conn.execute = AsyncMock(return_value=mock_cursor)
    repos.messages._get_conn = AsyncMock(return_value=mock_conn)
    return repos


@pytest.mark.anyio
async def test_finds_matching_messages():
    rows = [
        {"id": 1, "session_id": "sess_1", "role": "user",
         "content": "hola mundo", "created_at": "2024-01-01 12:00:00",
         "session_name": "TestSess"},
        {"id": 2, "session_id": "sess_1", "role": "assistant",
         "content": "mundo feliz", "created_at": "2024-01-01 12:01:00",
         "session_name": "TestSess"},
    ]
    result = await run(query="mundo", _repos=_make_repos(rows))
    assert "2 ocurrencias" in result
    assert "mundo" in result.casefold()


@pytest.mark.anyio
async def test_role_filter_user():
    # role_filter="user" should add AND m.role = ? with param "user"
    repos = MagicMock()
    mock_conn = AsyncMock()
    mock_conn.close = AsyncMock()
    mock_cursor = AsyncMock()
    mock_cursor.fetchall = AsyncMock(return_value=[])
    mock_conn.execute = AsyncMock(return_value=mock_cursor)
    repos.messages._get_conn = AsyncMock(return_value=mock_conn)

    await run(query="test", role="user", _repos=repos)
    # Verify the execute call had "user" in the params
    call_args, call_kwargs = mock_conn.execute.call_args
    sql, params = call_args
    assert "AND m.role = ?" in sql
    assert params == ["user"]


@pytest.mark.anyio
async def test_role_filter_assistant():
    repos = MagicMock()
    mock_conn = AsyncMock()
    mock_conn.close = AsyncMock()
    mock_cursor = AsyncMock()
    mock_cursor.fetchall = AsyncMock(return_value=[])
    mock_conn.execute = AsyncMock(return_value=mock_cursor)
    repos.messages._get_conn = AsyncMock(return_value=mock_conn)

    await run(query="test", role="assistant", _repos=repos)
    call_args, _ = mock_conn.execute.call_args
    sql, params = call_args
    assert "AND m.role = ?" in sql
    assert params == ["assistant"]


@pytest.mark.anyio
async def test_invalid_role_defaults_to_all():
    repos = MagicMock()
    mock_conn = AsyncMock()
    mock_conn.close = AsyncMock()
    mock_cursor = AsyncMock()
    mock_cursor.fetchall = AsyncMock(return_value=[])
    mock_conn.execute = AsyncMock(return_value=mock_cursor)
    repos.messages._get_conn = AsyncMock(return_value=mock_conn)

    await run(query="test", role="invalid_role", _repos=repos)
    call_args, _ = mock_conn.execute.call_args
    sql, params = call_args
    assert "AND m.role = ?" not in sql
    assert params == []


@pytest.mark.anyio
async def test_context_lines_clamped_to_max_3():
    repos = MagicMock()
    mock_conn = AsyncMock()
    mock_conn.close = AsyncMock()
    mock_cursor = AsyncMock()
    mock_cursor.fetchall = AsyncMock(return_value=[])
    mock_conn.execute = AsyncMock(return_value=mock_cursor)
    repos.messages._get_conn = AsyncMock(return_value=mock_conn)

    await run(query="test", context=10, _repos=repos)
    # context=10 should be clamped to 3 — no crash


@pytest.mark.anyio
async def test_max_matches_clamped_to_50():
    repos = MagicMock()
    mock_conn = AsyncMock()
    mock_conn.close = AsyncMock()
    mock_cursor = AsyncMock()
    mock_cursor.fetchall = AsyncMock(return_value=[])
    mock_conn.execute = AsyncMock(return_value=mock_cursor)
    repos.messages._get_conn = AsyncMock(return_value=mock_conn)

    await run(query="test", max_matches=999, _repos=repos)


@pytest.mark.anyio
async def test_case_sensitive_matching():
    rows = [
        {"id": 1, "session_id": "s1", "role": "user",
         "content": "Hola Mundo", "created_at": "2024-01-01",
         "session_name": "Chat"},
    ]
    # case_sensitive=True, query lowercase should NOT match uppercase content
    result = await run(query="mundo", case_sensitive=True, _repos=_make_repos(rows))
    assert "No se encontraron" in result

    # case_sensitive=False (default) should match
    result = await run(query="mundo", case_sensitive=False, _repos=_make_repos(rows))
    assert "1 ocurrencia" in result


@pytest.mark.anyio
async def test_session_name_fallback_to_sid():
    rows = [
        {"id": 1, "session_id": "abcdef123456", "role": "user",
         "content": "test match", "created_at": "2024-01-01",
         "session_name": None},
    ]
    result = await run(query="match", _repos=_make_repos(rows))
    # session_name is None → fallback to sid[:12] = "abcdef123456"
    assert "abcdef123456" in result


@pytest.mark.anyio
async def test_created_at_none_handled():
    rows = [
        {"id": 1, "session_id": "s1", "role": "user",
         "content": "match", "created_at": None,
         "session_name": "Chat"},
    ]
    # Should not crash on None created_at
    result = await run(query="match", _repos=_make_repos(rows))
    assert "1 ocurrencia" in result


@pytest.mark.anyio
async def test_max_matches_limits_output():
    rows = []
    for i in range(5):
        rows.append({
            "id": i, "session_id": "s1", "role": "user",
            "content": f"match numero {i}",
            "created_at": "2024-01-01", "session_name": "Chat",
        })
    result = await run(query="match", max_matches=3, _repos=_make_repos(rows))
    assert "5 ocurrencias" in result
    assert "(mostrando 3" in result


@pytest.mark.anyio
async def test_context_groups_merge():
    rows = [
        {"id": 1, "session_id": "s1", "role": "user",
         "content": "primer match", "created_at": "2024-01-01 12:00:00",
         "session_name": "Chat"},
        {"id": 2, "session_id": "s1", "role": "assistant",
         "content": "intermedio", "created_at": "2024-01-01 12:01:00",
         "session_name": "Chat"},
        {"id": 3, "session_id": "s1", "role": "user",
         "content": "segundo match", "created_at": "2024-01-01 12:02:00",
         "session_name": "Chat"},
    ]
    result = await run(query="match", context=1, _repos=_make_repos(rows))
    # Both matches (id 1 and 3) are within context distance 1 through id 2
    # So they should be merged into one context group
    assert "2 ocurrencias" in result


@pytest.mark.anyio
async def test_exception_handling():
    repos = MagicMock()
    repos.messages._get_conn = AsyncMock(side_effect=ValueError("db crash"))

    result = await run(query="test", _repos=repos)
    assert result.startswith("[ERROR]")
