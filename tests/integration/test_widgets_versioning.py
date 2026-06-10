from fastapi.testclient import TestClient


from web.server import app
from src.memory.database import init_db
from src.api import db_save_widget, db_get_widget, db_get_widget_versions, db_get_widget_by_version
from src.tools.save_widget import run as save_widget_run
from src.tools.get_widget_code import run as get_widget_code_run
from src.tools.update_widget import run as update_widget_run

client = TestClient(app)


def test_db_operations_saved_widgets():
    """Verify that saved_widgets and versions DB functions work correctly."""
    init_db()
    session_id = "test-session-widgets-db"
    widget_id = "calc"
    code_v1 = "<div>V1</div>"
    code_v2 = "<div>V2</div>"

    # Save V1
    res1 = db_save_widget(session_id, widget_id, code_v1, "v1 desc")
    assert res1["widget_id"] == widget_id
    assert res1["version"] == 1
    assert res1["status"] == "saved"

    # Get Active (V1)
    w = db_get_widget(session_id, widget_id)
    assert w is not None
    assert w["version"] == 1
    assert w["code"] == code_v1
    assert w["description"] == "v1 desc"

    # Save V2
    res2 = db_save_widget(session_id, widget_id, code_v2, "v2 desc")
    assert res2["version"] == 2

    # Get Active (V2)
    w_active = db_get_widget(session_id, widget_id)
    assert w_active["version"] == 2
    assert w_active["code"] == code_v2

    # Get versions list
    versions = db_get_widget_versions(session_id, widget_id)
    assert len(versions) == 2
    assert versions[0]["version"] == 2
    assert versions[0]["description"] == "v2 desc"
    assert versions[1]["version"] == 1

    # Get specific version
    w_v1 = db_get_widget_by_version(session_id, widget_id, 1)
    assert w_v1 is not None
    assert w_v1["code"] == code_v1


def test_widget_agent_tools():
    """Verify that agent tools (save, get, update) execute properly."""
    init_db()
    session_id = "test-session-widgets-tools"
    widget_id = "notes-app"
    code_initial = "<p>Initial</p>"
    code_updated = "<p>Updated</p>"

    # 1. Test get_widget_code for non-existent widget
    err_res = get_widget_code_run(widget_id, _session_id=session_id)
    assert "[ERROR]" in err_res

    # 2. Test save_widget
    save_res = save_widget_run(widget_id, code_initial, "init version", _session_id=session_id)
    assert "[OK]" in save_res
    assert "Version 1" in save_res

    # 3. Test get_widget_code for saved widget
    get_res = get_widget_code_run(widget_id, _session_id=session_id)
    assert "notes-app" in get_res
    assert "Active Version: 1" in get_res
    assert code_initial in get_res

    # 4. Test update_widget
    up_res = update_widget_run(widget_id, code_updated, "update version", _session_id=session_id)
    assert "[OK]" in up_res
    assert "Version 2" in up_res

    # 5. Test update_widget for non-existent widget
    up_err = update_widget_run("ghost-widget", code_updated, _session_id=session_id)
    assert "[ERROR]" in up_err


def test_widget_http_endpoints():
    """Verify widget endpoints: /code, /versions, /save."""
    init_db()
    session_id = "test-session-widgets-endpoints"
    widget_id = "game"
    code_str = "<canvas></canvas>"

    # 1. POST save
    resp_save = client.post(
        f"/sessions/{session_id}/widgets/{widget_id}/save",
        json={"code": code_str, "description": "game init"}
    )
    assert resp_save.status_code == 200
    assert resp_save.json()["status"] == "ok"
    assert resp_save.json()["version"] == 1

    # 2. GET code
    resp_code = client.get(f"/sessions/{session_id}/widgets/{widget_id}/code")
    assert resp_code.status_code == 200
    assert resp_code.json()["code"] == code_str
    assert resp_code.json()["version"] == 1

    # 3. GET versions
    resp_vers = client.get(f"/sessions/{session_id}/widgets/{widget_id}/versions")
    assert resp_vers.status_code == 200
    assert "versions" in resp_vers.json()
    assert len(resp_vers.json()["versions"]) == 1
    assert resp_vers.json()["versions"][0]["version"] == 1

    # 4. GET version code
    resp_vcode = client.get(f"/sessions/{session_id}/widgets/{widget_id}/versions/1/code")
    assert resp_vcode.status_code == 200
    assert resp_vcode.json()["code"] == code_str


def test_widget_portability_across_sessions():
    """Verify that widgets saved in one session are accessible and updatable from another session."""
    init_db()
    session_a = "session-a-test"
    session_b = "session-b-test"
    widget_id = "global-calc"
    code_v1 = "<div>Global V1</div>"
    code_v2 = "<div>Global V2</div>"

    # 1. Save in session A
    res1 = db_save_widget(session_a, widget_id, code_v1, "saved in A")
    assert res1["widget_id"] == widget_id
    assert res1["version"] == 1

    # 2. Get from session B (it should retrieve it globally)
    w_in_b = db_get_widget(session_b, widget_id)
    assert w_in_b is not None
    assert w_in_b["version"] == 1
    assert w_in_b["code"] == code_v1

    # 3. Update from session B
    res2 = db_save_widget(session_b, widget_id, code_v2, "updated in B")
    assert res2["version"] == 2

    # 4. Get active from session A (should be V2)
    w_in_a = db_get_widget(session_a, widget_id)
    assert w_in_a["version"] == 2
    assert w_in_a["code"] == code_v2

    # 5. Get versions list from session A
    versions = db_get_widget_versions(session_a, widget_id)
    assert len(versions) == 2
    assert versions[0]["version"] == 2
    assert versions[1]["version"] == 1

