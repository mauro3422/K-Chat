"""Channel adapters for K-Chat.

Each channel is a self-contained module that wraps ``src.core.orchestrator``
to deliver AI responses over a different communication surface (Telegram,
Discord, CLI, etc.).

A channel module exports:
    - ``run()`` — main entry point (blocking loop or asyncio task)
    - ``DEFINITION`` — metadata dict (name, description, version)
    - ``stop()`` — graceful shutdown signal (optional)

Channel modules are discovered automatically from ``channels/`` sub-packages
in the same way tools are discovered from ``src/tools/``.
"""

import importlib
import logging
import os
import pkgutil
from typing import Any, Callable

logger = logging.getLogger(__name__)

_CHANNEL_REGISTRY: dict[str, dict[str, Any]] = {}


def discover() -> dict[str, dict[str, Any]]:
    """Discover all channel modules in the channels package."""
    if _CHANNEL_REGISTRY:
        return _CHANNEL_REGISTRY

    pkg_path = os.path.dirname(__file__)
    for finder, name, is_pkg in pkgutil.iter_modules([pkg_path]):
        if not is_pkg:
            continue
        try:
            mod = importlib.import_module(f"channels.{name}")
            if hasattr(mod, "DEFINITION") and hasattr(mod, "run"):
                _CHANNEL_REGISTRY[name] = {
                    "definition": mod.DEFINITION,
                    "run": mod.run,
                    "stop": getattr(mod, "stop", None),
                    "module": mod,
                }
                logger.info("Channel discovered: %s", name)
        except Exception as e:
            logger.warning("Channel %s: error loading (%s), skipped", name, e)

    return _CHANNEL_REGISTRY


def get_channel(name: str) -> Callable[..., None] | None:
    """Get a channel's run function by name."""
    registry = discover()
    channel = registry.get(name)
    if channel:
        return channel["run"]
    return None


def list_channels() -> list[dict[str, Any]]:
    """List all discovered channels with their definitions."""
    registry = discover()
    return [
        {"name": name, **data["definition"]}
        for name, data in sorted(registry.items())
    ]
