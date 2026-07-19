import pytest
"""Tests for src/config_loader.py"""
import os
from src import config_loader as _config_loader
from src.config_loader import Config, load_config


@pytest.fixture(autouse=True)
def _no_dotenv_reload():
    """Prevent load_dotenv() from re-populating env vars during tests."""
    _config_loader._ensure_dotenv_loaded._loaded = True
    yield


class TestConfigDataclass:
    @pytest.mark.anyio
    async def test_default_values(self):
        """Config with no args uses defaults."""
        cfg = Config()
        assert cfg.opencode_zen_api_key == ""
        assert cfg.opencode_zen_base_url == "https://opencode.ai/zen/v1"
        assert cfg.llm_provider == "openai"
        assert cfg.host == "127.0.0.1"
        assert cfg.port == 8000
        assert cfg.log_level == "INFO"
        assert cfg.http_rate_limit == 60
        assert cfg.testing is False
        assert cfg.environment == "production"
        assert cfg.user_name == "user"

    @pytest.mark.anyio
    async def test_custom_values(self):
        """Config accepts explicit overrides."""
        cfg = Config(
            opencode_zen_api_key="test-key-123",
            opencode_zen_base_url="http://localhost:8080/v1",
            llm_provider="anthropic",
            memory_db_path="/tmp/test.db",
            searxng_url="http://search:8888",
            host="0.0.0.0",
            port=3000,
            log_level="DEBUG",
            http_rate_limit=10,
            kairos_log_dir="/var/log/kairos",
            testing=True,
            environment="development",
            user_name="testbot",
        )
        assert cfg.opencode_zen_api_key == "test-key-123"
        assert cfg.opencode_zen_base_url == "http://localhost:8080/v1"
        assert cfg.llm_provider == "anthropic"
        assert cfg.memory_db_path == "/tmp/test.db"
        assert cfg.searxng_url == "http://search:8888"
        assert cfg.host == "0.0.0.0"
        assert cfg.port == 3000
        assert cfg.log_level == "DEBUG"
        assert cfg.http_rate_limit == 10
        assert cfg.kairos_log_dir == "/var/log/kairos"
        assert cfg.testing is True
        assert cfg.environment == "development"
        assert cfg.user_name == "testbot"


class TestLoadConfig:
    @pytest.mark.anyio
    async def test_loads_from_env(self, monkeypatch):
        """load_config() reads environment variables."""
        monkeypatch.setenv("OPENCODE_ZEN_API_KEY", "env-key-456")
        monkeypatch.setenv("LLM_PROVIDER", "google")
        monkeypatch.setenv("HOST", "192.168.1.1")
        monkeypatch.setenv("PORT", "9000")
        monkeypatch.setenv("TESTING", "true")

        cfg = load_config()
        assert cfg.opencode_zen_api_key == "env-key-456"
        assert cfg.llm_provider == "google"
        assert cfg.host == "192.168.1.1"
        assert cfg.port == 9000
        assert cfg.testing is True

    @pytest.mark.anyio
    async def test_loads_lan_authentication_from_env(self, monkeypatch):
        monkeypatch.setenv("KAIROS_LAN_SHARED_SECRET", "shared-test-secret")
        monkeypatch.setenv("KAIROS_LAN_ALLOWED_NODE_IDS", "node-b,kairos-ops")
        monkeypatch.setenv("KAIROS_LAN_AUTH_WINDOW_SECONDS", "45")
        monkeypatch.setenv("KAIROS_LAN_AUTH_NONCE_CAPACITY", "2048")
        monkeypatch.setenv("KAIROS_LAN_AUTH_MAX_BODY_BYTES", "1048576")
        monkeypatch.setenv("KAIROS_LAN_AUTH_ALLOW_LOOPBACK", "true")
        monkeypatch.setenv("KAIROS_LAN_SNAPSHOT_MAX_CONCURRENCY", "2")

        cfg = load_config()

        assert cfg.lan_shared_secret == "shared-test-secret"
        assert cfg.lan_allowed_node_ids == "node-b,kairos-ops"
        assert cfg.lan_auth_window_seconds == 45
        assert cfg.lan_auth_nonce_capacity == 2048
        assert cfg.lan_auth_max_body_bytes == 1048576
        assert cfg.lan_auth_allow_loopback is True
        assert cfg.lan_snapshot_max_concurrency == 2

    @pytest.mark.anyio
    async def test_env_fallback_key(self, monkeypatch):
        """OPENCODE_ZEN_API_KEY_FALLBACK used when primary key is empty."""
        monkeypatch.setenv("OPENCODE_ZEN_API_KEY", "")
        monkeypatch.setenv("OPENCODE_ZEN_API_KEY_FALLBACK", "fallback-key")

        cfg = load_config()
        assert cfg.opencode_zen_api_key == "fallback-key"

    @pytest.mark.anyio
    async def test_memory_db_default(self, monkeypatch):
        """MEMORY_DB_PATH defaults to project-root/memory/kairos_memory.db."""
        monkeypatch.delenv("MEMORY_DB_PATH", raising=False)

        cfg = load_config()
        assert cfg.memory_db_path.endswith("kairos_curated_memory.db")
        assert "memory" in cfg.memory_db_path

    @pytest.mark.anyio
    async def test_port_default(self, monkeypatch):
        """PORT defaults to 8000 when env var is missing."""
        monkeypatch.delenv("PORT", raising=False)

        cfg = load_config()
        assert cfg.port == 8000

    @pytest.mark.anyio
    async def test_testing_default_false(self, monkeypatch):
        """TESTING defaults to False."""
        monkeypatch.delenv("TESTING", raising=False)

        cfg = load_config()
        assert cfg.testing is False


class TestDefaultConfig:
    @pytest.mark.anyio
    async def test_default_config_is_instance(self):
        """load_config() returns a Config instance."""
        assert isinstance(load_config(), Config)
