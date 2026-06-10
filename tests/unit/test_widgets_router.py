import pytest
from unittest.mock import patch

from fastapi import APIRouter, HTTPException

from web.routers.widgets import router, set_widget_state, get_widget_code, get_widget_versions, get_widget_version_code, save_widget, WidgetStatePayload, SaveWidgetPayload


def test_router_exists():
    assert isinstance(router, APIRouter)


def test_router_has_routes():
    assert len(router.routes) >= 1
    paths = [r.path for r in router.routes]
    assert "/sessions/{session_id}/widgets/{widget_id}/state" in paths
    assert "/sessions/{session_id}/widgets/{widget_id}/code" in paths
    assert "/sessions/{session_id}/widgets/{widget_id}/versions" in paths
    assert "/sessions/{session_id}/widgets/{widget_id}/versions/{version}/code" in paths
    assert "/sessions/{session_id}/widgets/{widget_id}/save" in paths


class TestSetWidgetState:
    @patch("web.routers.widgets.sanitize_widget_id", return_value="my-widget")
    @patch("web.routers.widgets.save_widget_state")
    def test_set_state_ok(self, mock_save, mock_sanitize):
        result = set_widget_state("sid-1", "my-widget", WidgetStatePayload(state='{"x":1}'))
        assert result == {"status": "ok"}
        mock_save.assert_called_once_with("sid-1", "my-widget", '{"x":1}')

    @patch("web.routers.widgets.sanitize_widget_id")
    @patch("web.routers.widgets.save_widget_state")
    def test_set_state_default_empty(self, mock_save, mock_sanitize):
        mock_sanitize.return_value = "w"
        result = set_widget_state("sid-1", "w", WidgetStatePayload())
        assert result == {"status": "ok"}
        mock_save.assert_called_once_with("sid-1", "w", "{}")


class TestGetWidgetCode:
    @patch("web.routers.widgets.db_get_widget")
    def test_found(self, mock_get):
        mock_get.return_value = {"id": "w1", "code": "alert(1)"}
        result = get_widget_code("sid-1", "w1")
        assert result == {"id": "w1", "code": "alert(1)"}

    @patch("web.routers.widgets.db_get_widget", return_value=None)
    def test_not_found(self, mock_get):
        with pytest.raises(HTTPException) as exc:
            get_widget_code("sid-1", "nonexistent")
        assert exc.value.status_code == 404


class TestGetWidgetVersions:
    @patch("web.routers.widgets.db_get_widget_versions", return_value=[1, 2])
    def test_returns_versions(self, mock_versions):
        result = get_widget_versions("sid-1", "w1")
        assert result == {"versions": [1, 2]}

    @patch("web.routers.widgets.db_get_widget_versions", return_value=[])
    def test_empty_versions(self, mock_versions):
        result = get_widget_versions("sid-1", "w1")
        assert result == {"versions": []}


class TestGetWidgetVersionCode:
    @patch("web.routers.widgets.db_get_widget_by_version")
    def test_found(self, mock_get):
        mock_get.return_value = {"version": 2, "code": "v2 code"}
        result = get_widget_version_code("sid-1", "w1", 2)
        assert result == {"version": 2, "code": "v2 code"}

    @patch("web.routers.widgets.db_get_widget_by_version", return_value=None)
    def test_not_found(self, mock_get):
        with pytest.raises(HTTPException) as exc:
            get_widget_version_code("sid-1", "w1", 99)
        assert exc.value.status_code == 404


class TestSaveWidget:
    @patch("web.routers.widgets.sanitize_widget_id", return_value="my-widget")
    @patch("web.routers.widgets.db_save_widget", return_value={"version": 1})
    def test_save_ok(self, mock_db, mock_sanitize):
        result = save_widget("sid-1", "my-widget", SaveWidgetPayload(code="alert(1)", description="test widget"))
        assert result == {"status": "ok", "widget_id": "my-widget", "version": 1}
        mock_db.assert_called_once_with("sid-1", "my-widget", "alert(1)", "test widget")

    @patch("web.routers.widgets.sanitize_widget_id", return_value="my-widget")
    @patch("web.routers.widgets.db_save_widget", return_value={"version": 2})
    def test_save_default_description(self, mock_db, mock_sanitize):
        result = save_widget("sid-1", "my-widget", SaveWidgetPayload(code="alert(1)"))
        assert result["version"] == 2
        mock_db.assert_called_once_with("sid-1", "my-widget", "alert(1)", "")

    def test_save_missing_code_raises_400(self):
        with pytest.raises(HTTPException) as exc:
            save_widget("sid-1", "my-widget", SaveWidgetPayload(code=""))
        assert exc.value.status_code == 400

    def test_save_empty_code_raises_400(self):
        with pytest.raises(HTTPException) as exc:
            save_widget("sid-1", "my-widget", SaveWidgetPayload(code=""))
        assert exc.value.status_code == 400

    @patch("web.routers.widgets.sanitize_widget_id", return_value="")
    def test_save_invalid_id_raises_400(self, mock_sanitize):
        with pytest.raises(HTTPException) as exc:
            save_widget("sid-1", "x@x", SaveWidgetPayload(code="alert(1)"))
        assert exc.value.status_code == 400

    @patch("web.routers.widgets.sanitize_widget_id", return_value="my-widget")
    @patch("web.routers.widgets.db_save_widget", side_effect=Exception("DB error"))
    def test_save_db_error_raises_500(self, mock_db, mock_sanitize):
        with pytest.raises(HTTPException) as exc:
            save_widget("sid-1", "my-widget", SaveWidgetPayload(code="alert(1)"))
        assert exc.value.status_code == 500
