import pytest
from unittest.mock import AsyncMock, MagicMock
from types import SimpleNamespace

from src.api.session_contract import SessionOpsDeps
from src.api.session import (
    ensure_session,
    rename_session,
    delete_session,
    get_sessions,
    _require_session,
)
from src.api.exceptions import ServiceException


@pytest.mark.anyio
async def test_ensure_session_calls_repo_ensure():
    session_repo = AsyncMock()
    session_repo.ensure = AsyncMock()

    await ensure_session("sess-1", session_repo=session_repo)

    session_repo.ensure.assert_awaited_once_with("sess-1", origin_node_id="")


@pytest.mark.anyio
async def test_ensure_session_uses_deps():
    session_repo = AsyncMock()
    deps = SessionOpsDeps(session_repo=session_repo)

    await ensure_session("sess-x", deps=deps)

    session_repo.ensure.assert_awaited_once_with("sess-x", origin_node_id="")


@pytest.mark.anyio
async def test_rename_session_calls_repo_rename():
    session_repo = AsyncMock()
    session_repo.rename = AsyncMock()

    await rename_session("sess-1", "new name", session_repo=session_repo)

    session_repo.rename.assert_awaited_once_with("sess-1", "new name")


@pytest.mark.anyio
async def test_rename_session_uses_deps():
    session_repo = AsyncMock()
    deps = SessionOpsDeps(session_repo=session_repo)

    await rename_session("sess-1", "new name", deps=deps)

    session_repo.rename.assert_awaited_once_with("sess-1", "new name")


@pytest.mark.anyio
async def test_delete_session_uses_injected_contract():
    deleted = []

    class FakeRepo:
        async def delete_by_session(self, session_id, cursor):
            deleted.append((session_id, cursor))

    class FakeSessionsRepo:
        async def delete_cascade(self, session_id, repos):
            cursor = "cursor"
            for repo in (
                repos.messages,
                repos.tool_calls,
                repos.debug,
                repos.widget_states,
                repos.saved_widgets,
                repos.memory_index,
            ):
                await repo.delete_by_session(session_id, cursor)
            deleted.append(("sessions", session_id))

    fake_repos = SimpleNamespace(
        messages=FakeRepo(),
        tool_calls=FakeRepo(),
        debug=FakeRepo(),
        widget_states=FakeRepo(),
        saved_widgets=FakeRepo(),
        memory_index=FakeRepo(),
        sessions=FakeSessionsRepo(),
    )

    await delete_session("sess-x", repos=fake_repos, deps=SessionOpsDeps(repos=fake_repos))

    assert deleted[0] == ("sess-x", "cursor")
    assert deleted[-1] == ("sessions", "sess-x")


@pytest.mark.anyio
async def test_delete_session_with_repos_and_session_repo():
    deleted = []

    class FakeRepo:
        async def delete_by_session(self, session_id, cursor):
            deleted.append((session_id, cursor))

    class FakeSessionsRepo:
        async def delete_cascade(self, session_id, repos):
            cursor = "cursor"
            for repo in (
                repos.messages,
                repos.tool_calls,
                repos.debug,
                repos.widget_states,
                repos.saved_widgets,
                repos.memory_index,
            ):
                await repo.delete_by_session(session_id, cursor)
            deleted.append(("sessions", session_id))

    fake_repos = SimpleNamespace(
        messages=FakeRepo(),
        tool_calls=FakeRepo(),
        debug=FakeRepo(),
        widget_states=FakeRepo(),
        saved_widgets=FakeRepo(),
        memory_index=FakeRepo(),
        sessions=FakeSessionsRepo(),
    )

    await delete_session(
        "sess-x",
        repos=fake_repos,
        session_repo=FakeSessionsRepo(),
    )

    assert deleted[0] == ("sess-x", "cursor")
    assert deleted[-1] == ("sessions", "sess-x")


@pytest.mark.anyio
async def test_get_sessions_calls_repo():
    session_repo = AsyncMock()
    session_repo.get_all = AsyncMock(return_value=[{"session_id": "sess-1"}])

    result = await get_sessions(session_repo=session_repo)

    session_repo.get_all.assert_awaited_once_with(50)
    assert result == [{"session_id": "sess-1"}]


@pytest.mark.anyio
async def test_get_sessions_with_custom_limit():
    session_repo = AsyncMock()
    session_repo.get_all = AsyncMock(return_value=[])

    result = await get_sessions(limit=10, session_repo=session_repo)

    session_repo.get_all.assert_awaited_once_with(10)
    assert result == []


@pytest.mark.anyio
async def test_get_sessions_uses_deps():
    session_repo = AsyncMock()
    session_repo.get_all = AsyncMock(return_value=[])
    deps = SessionOpsDeps(session_repo=session_repo)

    result = await get_sessions(deps=deps)

    session_repo.get_all.assert_awaited_once_with(50)
    assert result == []


@pytest.mark.anyio
async def test_require_session_passes_for_existing():
    session_repo = AsyncMock()
    session_repo.exists = AsyncMock(return_value=True)

    result = await _require_session("sess-1", session_repo=session_repo)

    session_repo.exists.assert_awaited_once_with("sess-1")
    assert result is None


@pytest.mark.anyio
async def test_require_session_raises_404_for_missing():
    session_repo = AsyncMock()
    session_repo.exists = AsyncMock(return_value=False)

    with pytest.raises(ServiceException) as exc:
        await _require_session("sess-1", session_repo=session_repo)

    assert exc.value.status_code == 404


@pytest.mark.anyio
async def test_require_session_raises_404_for_empty():
    session_repo = AsyncMock()

    with pytest.raises(ServiceException) as exc:
        await _require_session("", session_repo=session_repo)

    assert exc.value.status_code == 404
    session_repo.exists.assert_not_called()


@pytest.mark.anyio
async def test_require_session_raises_404_for_whitespace():
    session_repo = AsyncMock()

    with pytest.raises(ServiceException) as exc:
        await _require_session("   ", session_repo=session_repo)

    assert exc.value.status_code == 404
    session_repo.exists.assert_not_called()
