"""Compatibility shim — re-exports from src.config_loader.

New code should import from src.config_loader directly.
Kept for backward compatibility with legacy imports.
"""
from src.config_loader import Config, load_config, DEFAULT_CONFIG

OPENCODE_ZEN_API_KEY: str = DEFAULT_CONFIG.opencode_zen_api_key
OPENCODE_ZEN_API_KEY_FALLBACK: str = ""
MEMORY_DB_PATH: str = DEFAULT_CONFIG.memory_db_path
