import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from web.routers.sessions import delete
from web.services.chat_stream import _vectorize_session
from web.services.session_artifact_coordinator import SessionArtifactCoordinator


def _request(repos, coordinator):
    event_bus = MagicMock()
    event_bus.publish = AsyncMock()
    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                repos=repos,
                event_bus=event_bus,
                session_artifact_coordinator=coordinator,
            )
        )
    )


@pytest.mark.anyio
async def test_delete_waits_for_started_vectorization(monkeypatch):
    coordinator = SessionArtifactCoordinator()
    vectorization_started = asyncio.Event()
    allow_vectorization = asyncio.Event()
    delete_started = asyncio.Event()
    artifacts: set[str] = set()
    session_present = True

    repos = MagicMock()
    repos.sessions.get_all = AsyncMock()
    repos.sessions.exists = AsyncMock(side_effect=lambda _session_id: session_present)

    async def fake_pipeline(session_id, _repos):
        vectorization_started.set()
        await allow_vectorization.wait()
        artifacts.add(session_id)

    async def fake_delete_cascade(session_id, *, repos):
        nonlocal session_present
        delete_started.set()
        session_present = False
        artifacts.discard(session_id)

    repos.sessions.delete_cascade = AsyncMock(side_effect=fake_delete_cascade)
    monkeypatch.setattr(
        "web.services.chat_stream._run_vectorization_pipeline",
        fake_pipeline,
    )

    vectorize_task = asyncio.create_task(
        _vectorize_session(
            "sid-1",
            SimpleNamespace(repos=repos),
            coordinator,
        )
    )
    await asyncio.wait_for(vectorization_started.wait(), timeout=2)

    with patch("web.routers.sessions.log_event"):
        delete_task = asyncio.create_task(
            delete("sid-1", _request(repos, coordinator))
        )
        await asyncio.sleep(0)
        assert not delete_started.is_set()

        allow_vectorization.set()
        await asyncio.wait_for(
            asyncio.gather(vectorize_task, delete_task),
            timeout=2,
        )

    assert artifacts == set()
    repos.sessions.delete_cascade.assert_awaited_once_with("sid-1", repos=repos)
    assert coordinator.tracked_session_count == 0


@pytest.mark.anyio
async def test_vectorization_waiting_for_delete_skips_deleted_session(monkeypatch):
    coordinator = SessionArtifactCoordinator()
    delete_started = asyncio.Event()
    allow_delete = asyncio.Event()
    session_present = True

    repos = MagicMock()
    repos.sessions.get_all = AsyncMock()
    repos.sessions.exists = AsyncMock(side_effect=lambda _session_id: session_present)

    async def fake_delete_cascade(_session_id, *, repos):
        nonlocal session_present
        delete_started.set()
        await allow_delete.wait()
        session_present = False

    repos.sessions.delete_cascade = AsyncMock(side_effect=fake_delete_cascade)
    pipeline = AsyncMock()
    monkeypatch.setattr(
        "web.services.chat_stream._run_vectorization_pipeline",
        pipeline,
    )

    with patch("web.routers.sessions.log_event"):
        delete_task = asyncio.create_task(
            delete("sid-1", _request(repos, coordinator))
        )
        await asyncio.wait_for(delete_started.wait(), timeout=2)
        vectorize_task = asyncio.create_task(
            _vectorize_session(
                "sid-1",
                SimpleNamespace(repos=repos),
                coordinator,
            )
        )
        await asyncio.sleep(0)

        allow_delete.set()
        await asyncio.wait_for(
            asyncio.gather(delete_task, vectorize_task),
            timeout=2,
        )

    pipeline.assert_not_awaited()
    assert coordinator.tracked_session_count == 0


@pytest.mark.anyio
async def test_cancelled_waiter_is_removed_without_leaking_session_state():
    coordinator = SessionArtifactCoordinator()
    holder_entered = asyncio.Event()
    release_holder = asyncio.Event()
    waiter_started = asyncio.Event()

    async def holder():
        async with coordinator.coordinate("sid-1"):
            holder_entered.set()
            await release_holder.wait()

    async def waiter():
        waiter_started.set()
        async with coordinator.coordinate("sid-1"):
            raise AssertionError("cancelled waiter must not enter")

    holder_task = asyncio.create_task(holder())
    await asyncio.wait_for(holder_entered.wait(), timeout=2)
    waiter_task = asyncio.create_task(waiter())
    await asyncio.wait_for(waiter_started.wait(), timeout=2)
    await asyncio.sleep(0)

    waiter_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter_task

    assert coordinator.tracked_session_count == 1
    release_holder.set()
    await asyncio.wait_for(holder_task, timeout=2)
    assert coordinator.tracked_session_count == 0
