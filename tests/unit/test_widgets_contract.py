from types import SimpleNamespace

from src.api.widgets_contract import WidgetOpsDeps
from src.api.widgets import save_widget_state, db_save_widget


def test_widget_ops_deps_defaults_are_empty():
    deps = WidgetOpsDeps()

    assert deps.widget_state_repo is None
    assert deps.saved_widget_repo is None


def test_widget_contract_allows_injected_repos():
    calls = []

    class FakeWidgetStateRepo:
        def save_state(self, session_id, widget_id, state):
            calls.append(("state", session_id, widget_id, state))

    class FakeSavedWidgetRepo:
        def save(self, session_id, widget_id, code, description=""):
            calls.append(("saved", session_id, widget_id, code, description))
            return {"widget_id": widget_id, "version": 7, "status": "saved"}

    deps = WidgetOpsDeps(
        widget_state_repo=FakeWidgetStateRepo(),
        saved_widget_repo=FakeSavedWidgetRepo(),
    )

    save_widget_state("s1", "w1", "{}", deps=deps)
    res = db_save_widget("s1", "w1", "<div/>", "desc", deps=deps)

    assert calls[0] == ("state", "s1", "w1", "{}")
    assert calls[1] == ("saved", "s1", "w1", "<div/>", "desc")
    assert res["version"] == 7
