import pytest
from unittest.mock import AsyncMock
from httpx import AsyncClient, ASGITransport
from web.server import app
from src.memory.schema import init_db
from src.api.widgets import db_save_widget, db_get_widget, db_get_widget_versions, db_get_widget_by_version
from src.api.session import ensure_session
from src.tools.save_widget import run as save_widget_run
from src.tools.get_widget_code import run as get_widget_code_run
from src.tools.update_widget import run as update_widget_run

def _make_client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.anyio
async def test_db_operations_saved_widgets():
    """Verify that saved_widgets and versions DB functions work correctly."""
    await init_db()
    session_id = "test-session-widgets-db"
    await ensure_session(session_id)
    widget_id = "calc"
    code_v1 = "<div>V1</div>"
    code_v2 = "<div>V2</div>"

    # Save V1
    res1 = await db_save_widget(session_id, widget_id, code_v1, "v1 desc")
    assert res1["widget_id"] == widget_id
    assert res1["version"] == 1
    assert res1["status"] == "saved"

    # Get Active (V1)
    w = await db_get_widget(widget_id)
    assert w is not None
    assert w["version"] == 1
    assert w["code"] == code_v1
    assert w["description"] == "v1 desc"

    # Save V2
    res2 = await db_save_widget(session_id, widget_id, code_v2, "v2 desc")
    assert res2["version"] == 2

    # Get Active (V2)
    w_active = await db_get_widget(widget_id)
    assert w_active["version"] == 2
    assert w_active["code"] == code_v2

    # Get versions list
    versions = await db_get_widget_versions(widget_id)
    assert len(versions) == 2
    assert versions[0]["version"] == 2
    assert versions[0]["description"] == "v2 desc"
    assert versions[1]["version"] == 1

    # Get specific version
    w_v1 = await db_get_widget_by_version(widget_id, 1)
    assert w_v1 is not None
    assert w_v1["code"] == code_v1


@pytest.mark.anyio
async def test_widget_agent_tools():
    """Verify that agent tools (save, get, update) execute properly."""
    await init_db()
    session_id = "test-session-widgets-tools"
    await ensure_session(session_id)
    widget_id = "notes-app"
    code_initial = "<p>Initial</p>"
    code_updated = "<p>Updated</p>"

    from src.api.repos import get_repos
    repos = get_repos()

    # 1. Test get_widget_code for non-existent widget
    err_res = await get_widget_code_run(widget_id, _session_id=session_id, _repos=repos)
    assert "[ERROR]" in err_res

    # 2. Test save_widget
    save_res = await save_widget_run(widget_id, code_initial, "init version", _session_id=session_id, _repos=repos)
    assert "[OK]" in save_res
    assert "Version 1" in save_res

    # 3. Test get_widget_code for saved widget
    get_res = await get_widget_code_run(widget_id, _session_id=session_id, _repos=repos)
    assert "notes-app" in get_res
    assert "Active Version: 1" in get_res
    assert code_initial in get_res

    # 4. Test update_widget
    up_res = await update_widget_run(widget_id, code_updated, "update version", _session_id=session_id, _repos=repos)
    assert "[OK]" in up_res
    assert "Version 2" in up_res

    # 5. Test update_widget for non-existent widget
    up_err = await update_widget_run("ghost-widget", code_updated, _session_id=session_id, _repos=repos)
    assert "[ERROR]" in up_err


@pytest.mark.anyio
async def test_widget_http_endpoints():
    """Verify widget endpoints: /code, /versions, /save."""
    await init_db()
    session_id = "test-session-widgets-endpoints"
    await ensure_session(session_id)
    widget_id = "game"
    code_str = "<canvas></canvas>"

    async with _make_client() as client:
        # 1. POST save
        resp_save = await client.post(
            f"/sessions/{session_id}/widgets/{widget_id}/save",
            json={"code": code_str, "description": "game init"}
        )
        assert resp_save.status_code == 200
        assert resp_save.json()["status"] == "ok"
        assert resp_save.json()["version"] == 1

        # 2. GET code
        resp_code = await client.get(f"/sessions/{session_id}/widgets/{widget_id}/code")
        assert resp_code.status_code == 200
        assert resp_code.json()["code"] == code_str
        assert resp_code.json()["version"] == 1

        # 3. GET versions
        resp_vers = await client.get(f"/sessions/{session_id}/widgets/{widget_id}/versions")
        assert resp_vers.status_code == 200
        assert "versions" in resp_vers.json()
        assert len(resp_vers.json()["versions"]) == 1
        assert resp_vers.json()["versions"][0]["version"] == 1

        # 4. GET version code
        resp_vcode = await client.get(f"/sessions/{session_id}/widgets/{widget_id}/versions/1/code")
        assert resp_vcode.status_code == 200
        assert resp_vcode.json()["code"] == code_str


@pytest.mark.anyio
async def test_widget_portability_across_sessions():
    """Verify that widgets saved in one session are accessible and updatable from another session."""
    await init_db()
    session_a = "session-a-test"
    session_b = "session-b-test"
    await ensure_session(session_a)
    await ensure_session(session_b)
    widget_id = "global-calc"
    code_v1 = "<div>Global V1</div>"
    code_v2 = "<div>Global V2</div>"

    # 1. Save in session A
    res1 = await db_save_widget(session_a, widget_id, code_v1, "saved in A")
    assert res1["widget_id"] == widget_id
    assert res1["version"] == 1

    # 2. Get from session B (it should retrieve it globally)
    w_in_b = await db_get_widget(widget_id)
    assert w_in_b is not None
    assert w_in_b["version"] == 1
    assert w_in_b["code"] == code_v1

    # 3. Update from session B
    res2 = await db_save_widget(session_b, widget_id, code_v2, "updated in B")
    assert res2["version"] == 2

    # 4. Get active from session A (should be V2)
    w_in_a = await db_get_widget(widget_id)
    assert w_in_a["version"] == 2
    assert w_in_a["code"] == code_v2

    # 5. Get versions list from session A
    versions = await db_get_widget_versions(widget_id)
    assert len(versions) == 2
    assert versions[0]["version"] == 2
    assert versions[1]["version"] == 1
