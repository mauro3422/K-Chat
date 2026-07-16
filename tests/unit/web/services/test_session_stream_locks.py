import pytest

from web.services.session_stream_locks import SessionStreamLockManager


@pytest.mark.anyio
async def test_session_stream_lock_manager_rejects_concurrent_acquire():
    manager = SessionStreamLockManager()

    first = await manager.try_acquire("sess-1")
    assert first is not None

    second = await manager.try_acquire("sess-1")
    assert second is None

    manager.release("sess-1", first)

    third = await manager.try_acquire("sess-1")
    assert third is not None
    manager.release("sess-1", third)
