from types import SimpleNamespace

from src.api.session_contract import SessionOpsDeps
from src.api.session import delete_session


def test_session_ops_deps_defaults_are_empty():
    deps = SessionOpsDeps()

    assert deps.session_repo is None
    assert deps.repos is None


def test_delete_session_uses_injected_contract():
    deleted = []

    class FakeRepo:
        def delete_by_session(self, session_id, cursor):
            deleted.append((session_id, cursor))

    class FakeSessionsRepo:
        def delete_cascade(self, session_id, repos):
            cursor = "cursor"
            for repo in (
                repos.messages,
                repos.tool_calls,
                repos.debug,
                repos.widget_states,
                repos.saved_widgets,
                repos.memory_index,
            ):
                repo.delete_by_session(session_id, cursor)
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

    delete_session(
        "sess-x",
        deps=SessionOpsDeps(
            repos=fake_repos,
        ),
    )

    assert deleted[0] == ("sess-x", "cursor")
    assert deleted[-1] == ("sessions", "sess-x")
