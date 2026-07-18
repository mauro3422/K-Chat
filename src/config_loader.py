import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

def _ensure_dotenv_loaded() -> None:
    if not _ensure_dotenv_loaded._loaded:
        load_dotenv()
        _ensure_dotenv_loaded._loaded = True
_ensure_dotenv_loaded._loaded = False


def reset_dotenv_state() -> None:
    """Allow dotenv loading to run again on the next config access."""
    _ensure_dotenv_loaded._loaded = False

# ── Model name constants ────────────────────────────────────────────────
DEFAULT_MODEL: str = "deepseek-v4-flash"
# Priority list for failover — only include models known to exist.
# When DEFAULT_MODEL fails, _switch_model tries each candidate in order.
# Remove big-pickle (ghost model that caused permanent 401 fallback loop).
PRIORITY_MODELS: list[str] = [
    "deepseek-v4-flash",       # Go API (primary)
    "deepseek-v4-flash-free",  # Zen API (fallback)
]


@dataclass
class Config:
    opencode_zen_api_key: str = ""
    opencode_zen_base_url: str = "https://opencode.ai/zen/v1"
    opencode_go_base_url: str = "https://opencode.ai/zen/go/v1"
    web_base_url: str = ""
    llm_provider: str = "openai"
    llm_mode: str = "go"
    sessions_db_path: str = ""
    memory_db_path: str = ""
    searxng_url: str = "http://127.0.0.1:8080"
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"
    http_rate_limit: int = 60
    kairos_log_dir: str = "logs"
    llm_max_retries: int = 3
    llm_retry_delay: float = 5.0
    tool_heartbeat_interval: float = 10.0
    max_tool_turns: int = 100
    testing: bool = False
    environment: str = "production"
    user_name: str = "user"
    auto_retrieval_enabled: bool = True
    # ── Telegram Bot ────────────────────────────────────────────────
    telegram_bot_token: str = ""
    telegram_allowed_users: str = ""
    # ── Watchdog ────────────────────────────────────────────────────
    watchdog_interval: int = 5
    watchdog_url: str = "http://127.0.0.1:8000/live"
    # ── Session retention ──────────────────────────────────────────
    session_max_age_days: int = 90
    # ── LAN coordination ─────────────────────────────────────────────
    node_id: str = ""
    node_role: str = "secondary"
    node_platform: str = ""
    cluster_name: str = "kairos"
    peer_urls: str = ""
    node_base_url: str = ""
    node_heartbeat_ttl: float = 15.0
    lan_discovery_enabled: bool = True
    lan_discovery_group: str = "239.255.42.99"
    lan_discovery_port: int = 42429
    lan_discovery_interval: float = 5.0
    lan_discovery_ttl: float = 20.0
    lan_shared_secret: str = ""
    lan_allowed_node_ids: str = ""
    lan_auth_window_seconds: int = 30
    lan_auth_nonce_capacity: int = 4096
    lan_auth_max_body_bytes: int = 3 * 1024 * 1024
    lan_auth_allow_loopback: bool = False


def _resolve_project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def load_config(overrides: dict | None = None) -> Config:
    _ensure_dotenv_loaded()
    root = _resolve_project_root()
    cfg = Config(
        opencode_zen_api_key=os.getenv("OPENCODE_ZEN_API_KEY", "") or os.getenv("OPENCODE_ZEN_API_KEY_FALLBACK", ""),
        opencode_zen_base_url=os.getenv("OPENCODE_ZEN_BASE_URL", "https://opencode.ai/zen/v1"),
        opencode_go_base_url=os.getenv("OPENCODE_GO_BASE_URL", "https://opencode.ai/zen/go/v1"),
        web_base_url=os.getenv("KAIROS_WEB_BASE_URL", "") or os.getenv("WEB_BASE_URL", ""),
        llm_provider=os.getenv("LLM_PROVIDER", "openai"),
        llm_mode=os.getenv("LLM_MODE", "go"),
        sessions_db_path=os.getenv("SESSIONS_DB_PATH", str(root / "memory" / "kairos_memory.db")),
        memory_db_path=os.getenv("MEMORY_DB_PATH", str(root / "memory" / "kairos_curated_memory.db")),
        searxng_url=os.getenv("SEARXNG_URL", "http://127.0.0.1:8080"),
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        http_rate_limit=int(os.getenv("HTTP_RATE_LIMIT", "60")),
        kairos_log_dir=os.getenv("KAIROS_LOG_DIR", "logs"),
        llm_max_retries=int(os.getenv("LLM_MAX_RETRIES", "3")),
        llm_retry_delay=float(os.getenv("LLM_RETRY_DELAY", "5.0")),
        tool_heartbeat_interval=float(os.getenv("TOOL_HEARTBEAT_INTERVAL", "10.0")),
        max_tool_turns=int(os.getenv("MAX_TOOL_TURNS", "100")),
        testing=os.getenv("TESTING", "").lower() in ("1", "true", "yes"),
        environment=os.getenv("ENVIRONMENT", "production"),
        user_name=os.getenv("USER", "") or os.getenv("USERNAME", "user"),
        auto_retrieval_enabled=os.getenv("AUTO_RETRIEVAL_ENABLED", "true").lower() in ("1", "true", "yes"),
        # ── Telegram ────────────────────────────────────────────────
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        telegram_allowed_users=os.getenv("TELEGRAM_ALLOWED_USERS", ""),
        # ── Watchdog ───────────────────────────────────────────────
        watchdog_interval=int(os.getenv("WATCHDOG_INTERVAL", "5")),
        watchdog_url=os.getenv("WATCHDOG_URL", "http://127.0.0.1:8000/live"),
        # ── Session retention ──────────────────────────────────────
        session_max_age_days=int(os.getenv("SESSION_MAX_AGE_DAYS", "90")),
        node_id=os.getenv("KAIROS_NODE_ID", "") or os.getenv("HOSTNAME", "") or os.getenv("COMPUTERNAME", ""),
        node_role=os.getenv("KAIROS_NODE_ROLE", "secondary"),
        node_platform=os.getenv("KAIROS_NODE_PLATFORM", ""),
        cluster_name=os.getenv("KAIROS_CLUSTER_NAME", "kairos"),
        peer_urls=os.getenv("KAIROS_PEER_URLS", ""),
        node_base_url=os.getenv("KAIROS_NODE_BASE_URL", ""),
        node_heartbeat_ttl=float(os.getenv("KAIROS_NODE_HEARTBEAT_TTL", "15.0")),
        lan_discovery_enabled=os.getenv("KAIROS_LAN_DISCOVERY", "true").lower() in ("1", "true", "yes"),
        lan_discovery_group=os.getenv("KAIROS_LAN_DISCOVERY_GROUP", "239.255.42.99"),
        lan_discovery_port=int(os.getenv("KAIROS_LAN_DISCOVERY_PORT", "42429")),
        lan_discovery_interval=float(os.getenv("KAIROS_LAN_DISCOVERY_INTERVAL", "5.0")),
        lan_discovery_ttl=float(os.getenv("KAIROS_LAN_DISCOVERY_TTL", "20.0")),
        lan_shared_secret=os.getenv("KAIROS_LAN_SHARED_SECRET", ""),
        lan_allowed_node_ids=os.getenv("KAIROS_LAN_ALLOWED_NODE_IDS", ""),
        lan_auth_window_seconds=int(os.getenv("KAIROS_LAN_AUTH_WINDOW_SECONDS", "30")),
        lan_auth_nonce_capacity=int(os.getenv("KAIROS_LAN_AUTH_NONCE_CAPACITY", "4096")),
        lan_auth_max_body_bytes=int(os.getenv("KAIROS_LAN_AUTH_MAX_BODY_BYTES", str(3 * 1024 * 1024))),
        lan_auth_allow_loopback=os.getenv("KAIROS_LAN_AUTH_ALLOW_LOOPBACK", "false").lower() in ("1", "true", "yes"),
    )

    if overrides:
        for k, v in overrides.items():
            if hasattr(cfg, k) and v is not None:
                setattr(cfg, k, v)

    return cfg
