import sqlite3
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from web.routers.health import router


def _make_client(config):
    app = FastAPI()
    app.state.config = config
    app.include_router(router)
    return TestClient(app, raise_server_exceptions=False)


def test_health_reports_database_ok(tmp_path):
    db_path = tmp_path / "sessions.db"
    sqlite3.connect(db_path).close()

    config = SimpleNamespace(
        testing=False,
        sessions_db_path=str(db_path),
        opencode_zen_api_key="",
        node_role="secondary",
        cluster_name="kairos",
    )

    with _make_client(config) as client:
        response = client.get("/health")

    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "ok"
    assert body["checks"]["database"] == "ok"


def test_health_marks_missing_database_degraded_when_not_testing(tmp_path):
    config = SimpleNamespace(
        testing=False,
        sessions_db_path=str(tmp_path / "missing.db"),
        opencode_zen_api_key="",
        node_role="secondary",
        cluster_name="kairos",
    )

    with _make_client(config) as client:
        response = client.get("/health")

    body = response.json()
    assert response.status_code == 503
    assert body["status"] == "degraded"
    assert body["checks"]["database"] == "error"


def test_health_skips_missing_database_when_testing(tmp_path):
    config = SimpleNamespace(
        testing=True,
        sessions_db_path=str(tmp_path / "missing.db"),
        opencode_zen_api_key="",
        node_role="secondary",
        cluster_name="kairos",
    )

    with _make_client(config) as client:
        response = client.get("/health")

    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "ok"
    assert body["checks"]["database"] == "skipped"
