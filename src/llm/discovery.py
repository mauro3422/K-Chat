import asyncio
import logging
from typing import Any

import src.llm.model_state as models
import src.llm.model_registry as registry
from src.llm.providers import _get_provider
import src.llm.verifier as verifier
from src.utils.async_utils import schedule_background_awaitable

logger: logging.Logger = logging.getLogger(__name__)


def _start_background_ping(free_ids: list[str], config=None) -> None:
    if not free_ids:
        return
    schedule_background_awaitable(
        _ping_free_model_availability(free_ids, config=config),
        label="free model availability ping",
    )


def _resolve_config(config=None):
    if config is None:
        from src._config import resolve_config
        return resolve_config()
    return config


def _is_go_mode(config=None) -> bool:
    return _resolve_config(config).llm_mode == "go"


def _model_id(model: Any) -> str:
    return model if isinstance(model, str) else getattr(model, "id", "")


def _make_zen_provider(config=None):
    cfg = _resolve_config(config)
    import copy
    fresh = copy.copy(cfg)
    fresh.llm_mode = "zen"
    from src.llm.providers import _get_registry
    provider_cls = _get_registry().get(fresh.llm_provider)
    if not provider_cls:
        return None
    return provider_cls(api_key=fresh.opencode_zen_api_key, base_url=fresh.opencode_zen_base_url)


async def get_models(force_refresh: bool = False, config=None) -> list[Any]:
    """Returns all available models from the API (with in-memory cache)."""
    cached = models.get_cached_models_safe()
    if cached is None or force_refresh:
        try:
            provider = _get_provider(config=config)
            result = await provider.list_models()
            models.set_cached_models(result)
        except Exception as e:
            logger.error("Error fetching models from API: %s", e)
            cached = models.get_cached_models_safe()
            if cached is not None:
                return cached
            raise
    return models.get_cached_models_safe() or []


async def get_free_models(force_refresh: bool = False, config=None) -> list[Any]:
    """Returns only free models (IDs ending in -free)."""
    all_models = await get_models(force_refresh=force_refresh, config=config)
    free_models = []
    for model in all_models:
        model_id = model if isinstance(model, str) else getattr(model, "id", None)
        if model_id and model_id.endswith("-free"):
            free_models.append(model)
    return free_models


async def get_verified_models(force_refresh: bool = False, config=None) -> list[str]:
    """Returns the list of models that are active and working.

    In Go mode: all models from the API are pre-verified by OpenCode, skip verification.
    In Zen mode: verify each free model with a test call.
    """
    cached = models.get_verified_models_safe()
    if cached and not force_refresh:
        return cached
    verified_models: list[str] = []

    if _is_go_mode(config=config):
        try:
            all_models = await get_models(force_refresh=force_refresh, config=config)
            all_ids = [mid for mid in (_model_id(m) for m in all_models) if mid]
            # In Go mode, also fetch FREE models (cost=0, -free suffix) from Zen API
            try:
                zen_provider = _make_zen_provider(config=config)
                zen_models = await zen_provider.list_models() if zen_provider else []
                for m in zen_models:
                    mid = _model_id(m)
                    if mid and mid.endswith("-free") and mid not in all_ids:
                        all_ids.append(mid)
                logger.info("Go mode: discovered %d free models from Zen API", len([x for x in all_ids if x.endswith("-free")]))
            except Exception as ze:
                logger.warning("Could not fetch free models from Zen: %s", ze)
            registry.set_verified_models(all_ids)
            logger.info("Go mode: all %d models trusted as verified", len(all_ids))
            verified_models = all_ids
        except Exception as e:
            logger.error("Error fetching Go models: %s", e)
            registry.set_verified_models([models.FALLBACK_MODEL])
            verified_models = [models.FALLBACK_MODEL]
    else:
        try:
            free_models = await get_free_models(force_refresh=force_refresh, config=config)
            verified: list[str] = []

            model_ids = [mid for mid in (_model_id(m) for m in free_models) if mid]

            for mid in model_ids:
                try:
                    if await verifier.verify_model(mid):
                        verified.append(mid)
                except Exception as e:
                    logger.warning("Model verification failed for %s: %s", mid, e)
            registry.set_verified_models(verified)
            logger.info("Zen mode: verified %d/%d free models", len(verified), len(model_ids))
            verified_models = verified
        except Exception as e:
            logger.error("Error verifying Zen models: %s", e)
            cached = models.get_verified_models_safe()
            if cached:
                return cached
            registry.set_verified_models([models.FALLBACK_MODEL])
            verified_models = []

    # Fire-and-forget availability ping for free models.
    # Runs in background so it doesn't block the caller (e.g. lifespan timeout=10s).
    free_ids = [m for m in verified_models if m.endswith("-free")]
    _start_background_ping(free_ids, config=config)

    return verified_models


async def _ping_free_model_availability(free_ids: list[str], config=None) -> None:
    """Ping each free model independently to check availability.

    Each model gets a lightweight 1-token request via the Zen API.
    Results:
      - 200 OK → mark_available
      - 429 → mark_rate_limited
      - other errors (401 promotion ended, etc.) → not available, no mark
    """
    if not free_ids:
        return

    from src.llm.rate_limit_state import get_rate_limit_store
    store = get_rate_limit_store()

    # Build Zen provider once
    zen_provider = _make_zen_provider(config=config)
    if not zen_provider:
        return
    from src.llm.protocol import UnifiedRequest

    sem = asyncio.Semaphore(3)

    async def _ping_one(mid: str) -> None:
        async with sem:
            try:
                await zen_provider.chat(
                    UnifiedRequest(
                        messages=[{"role": "user", "content": "hi"}],
                        model=mid,
                        max_tokens=1,
                        stream=False,
                    )
                )
                store.mark_available(mid)
                logger.info("Free model ping OK: %s", mid)
            except Exception as e:
                from src.llm.retry import is_rate_limit_error
                if is_rate_limit_error(e):
                    store.mark_rate_limited(mid, retry_after=60, detail=str(e)[:200])
                    logger.info("Free model ping 429: %s — rate-limited", mid)
                else:
                    # Promotion ended, model removed, etc.
                    store.mark_unavailable(mid)
                    logger.info("Free model ping unavailable: %s — %s", mid, str(e)[:100])

    await asyncio.gather(*[_ping_one(mid) for mid in free_ids], return_exceptions=True)
