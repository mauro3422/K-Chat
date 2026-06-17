"""Config resolution helper - single source of truth for Config dependency."""

from __future__ import annotations

from typing import Optional
from src.config_loader import Config, load_config as _load_config


def resolve_config(config: Optional[Config] = None) -> Config:
    """Resolve Config, loading from env if not provided.
    
    Use this instead of repeating 'if config is None: load_config()' everywhere.
    Long-term goal: modules should receive Config via constructor injection.
    """
    if config is not None:
        return config
    return _load_config()
