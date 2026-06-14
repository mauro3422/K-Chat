import pytest
from unittest.mock import AsyncMock
from unittest.mock import patch, MagicMock

import dependencies.manage as manage


@pytest.mark.anyio
async def test_searxng_start_does_not_auto_install_by_default(monkeypatch):
    monkeypatch.setattr(manage, "searxng_is_installed", lambda: False)
    monkeypatch.setattr(manage, "SEARXNG_AUTO_INSTALL", False)
    install_mock = MagicMock()
    monkeypatch.setattr(manage, "install_searxng_deps", install_mock)

    result = manage.searxng_start()

    assert result == "SearXNG dependencies are not installed. Set SEARXNG_AUTO_INSTALL=1 to install them."
    install_mock.assert_not_called()


@pytest.mark.anyio
async def test_searxng_start_installs_when_explicitly_enabled(monkeypatch):
    monkeypatch.setattr(manage, "searxng_is_installed", lambda: False)
    monkeypatch.setattr(manage, "SEARXNG_AUTO_INSTALL", True)
    install_mock = MagicMock(return_value=None)
    monkeypatch.setattr(manage, "install_searxng_deps", install_mock)
    popen_mock = MagicMock()
    monkeypatch.setattr(manage.subprocess, "Popen", popen_mock)

    result = manage.searxng_start()

    assert result is None
    install_mock.assert_called_once()
    popen_mock.assert_called_once()
