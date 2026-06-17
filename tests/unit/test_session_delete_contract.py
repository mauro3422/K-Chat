"""Anti-regression: session delete must be idempotent (not 500 on second delete).

Deleting a session twice should succeed both times — the second delete is a no-op
(DELETE FROM is idempotent in SQL). A 500 error on second delete is a regression.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.api.session import delete_session
from src.api.session_contract import SessionOpsDeps

pytestmark = pytest.mark.anyio


async def test_delete_session_idempotent() -> None:
    """Calling delete_session twice on the same session must not raise."""
    deleted: list[tuple[str, str | None]] = []

    class FakeRepo:
        async def delete_by_session(
            self, session_id: str, cursor: object = None
        ) -> None:
            deleted.append((session_id, cursor))

    class FakeSessionsRepo:
        async def delete_cascade(
            self, session_id: str, repos: object = None
        ) -> None:
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

    # First delete — should succeed
    await delete_session(
        "sess-idempotent",
        repos=fake_repos,
        deps=SessionOpsDeps(repos=fake_repos),
    )

    first_count = len(deleted)

    # Second delete — must NOT raise (idempotent)
    await delete_session(
        "sess-idempotent",
        repos=fake_repos,
        deps=SessionOpsDeps(repos=fake_repos),
    )

    # Both calls should have produced records
    assert len(deleted) == first_count * 2, (
        f"Expected {first_count * 2} total delete records, got {len(deleted)}"
    )
    # First delete's records should all reference sess-idempotent
    for i, entry in enumerate(deleted):
        if entry[0] == "sessions":
            assert entry[1] == "sess-idempotent", f"entry[{i}]: wrong session_id"
        else:
            assert entry[0] == "sess-idempotent", f"entry[{i}]: wrong session_id"


async def test_delete_session_without_deps_direct_repo() -> None:
    """delete_session works when called with just repos= (no deps)."""
    deleted: list[str] = []

    class FakeSessionsRepo:
        async def delete_cascade(
            self, session_id: str, repos: object = None
        ) -> None:
            deleted.append(session_id)

    fake_repos = SimpleNamespace(
        messages=SimpleNamespace(delete_by_session=lambda sid, c: None),
        tool_calls=SimpleNamespace(delete_by_session=lambda sid, c: None),
        debug=SimpleNamespace(delete_by_session=lambda sid, c: None),
        widget_states=SimpleNamespace(delete_by_session=lambda sid, c: None),
        saved_widgets=SimpleNamespace(delete_by_session=lambda sid, c: None),
        memory_index=SimpleNamespace(delete_by_session=lambda sid, c: None),
        sessions=FakeSessionsRepo(),
    )

    # Pasamos SessionOpsDeps con session_repo=None para forzar el fallback a repos.sessions
    await delete_session(
        "sess-no-deps",
        repos=fake_repos,
        deps=SessionOpsDeps(repos=fake_repos),
    )

    assert deleted == ["sess-no-deps"]
