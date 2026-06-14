import asyncio
import logging
from typing import Any

import src.llm.model_state as models
from src.llm.providers import _get_provider
import src.llm.verifier as verifier

logger: logging.Logger = logging.getLogger(__name__)


def _is_go_mode(config=None) -> bool:
    from src.config_loader import DEFAULT_CONFIG
    cfg = config or DEFAULT_CONFIG
    return cfg.llm_mode == "go"


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
    if cached is not None and not force_refresh:
        return cached

    if _is_go_mode(config=config):
        try:
            all_models = await get_models(force_refresh=force_refresh, config=config)
            all_ids = [m if isinstance(m, str) else getattr(m, "id", "") for m in all_models]
            all_ids = [mid for mid in all_ids if mid]
            # In Go mode, also fetch FREE models (cost=0, -free suffix) from Zen API
            try:
                from src.config_loader import DEFAULT_CONFIG, Config
                zen_cfg = config or DEFAULT_CONFIG
                import copy
                fresh = copy.copy(zen_cfg)
                fresh.llm_mode = "zen"
                # Create a fresh Zen provider (bypass global singleton)
                from src.llm.providers import _PROVIDER_REGISTRY
                provider_cls = _PROVIDER_REGISTRY.get(fresh.llm_provider)
                if provider_cls:
                    zen_provider = provider_cls(api_key=fresh.opencode_zen_api_key, base_url=fresh.opencode_zen_base_url)
                    zen_models = await zen_provider.list_models()
                else:
                    zen_models = []
                for m in zen_models:
                    mid = m if isinstance(m, str) else getattr(m, "id", "")
                    if mid and mid.endswith("-free") and mid not in all_ids:
                        all_ids.append(mid)
                logger.info("Go mode: added free models from Zen API")
            except Exception as ze:
                logger.warning("Could not fetch free models from Zen: %s", ze)
            models.set_verified_models(all_ids)
            logger.info("Go mode: all %d models trusted as verified", len(all_ids))
        except Exception as e:
            logger.error("Error fetching Go models: %s", e)
            models.set_verified_models([models.FALLBACK_MODEL])
    else:
        try:
            free_models = await get_free_models(force_refresh=force_refresh, config=config)
            verified: list[str] = []

            model_ids = [m if isinstance(m, str) else getattr(m, "id", "") for m in free_models]
            model_ids = [mid for mid in model_ids if mid]

            async def check(model_id: str) -> str | None:
                if await verifier.verify_model(model_id):
                    return model_id
                return None

            tasks = [check(mid) for mid in model_ids]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for res in results:
                if isinstance(res, str):
                    verified.append(res)
            models.set_verified_models(verified)
            logger.info("Zen mode: verified %d/%d free models", len(verified), len(model_ids))
        except Exception as e:
            logger.error("Error verifying Zen models: %s", e)
            cached = models.get_verified_models_safe()
            if cached is not None:
                return cached
            models.set_verified_models([models.FALLBACK_MODEL])

    # Single-ping availability check for free models
    free_ids = [m for m in (models.get_verified_models_safe() or []) if m.endswith("-free")]
    if free_ids:
        try:
            await _ping_free_model_availability(free_ids, config=config)
        except Exception:
            pass

    # Single-ping availability check for free models
    free_ids = [m for m in (models.get_verified_models_safe() or []) if m.endswith("-free")]
    if free_ids:
        try:
            await _ping_free_model_availability(free_ids, config=config)
        except Exception:
            pass

    return models.get_verified_models_safe() or []


async def _ping_free_model_availability(free_ids: list[str], config=None) -> None:
    """Make ONE lightweight ping to a free model to check rate-limit status.

    If 429 → all free models are rate-limited (cooldown tracked).
    If success → all free models are available (clear any stale limits).
    """
    if not free_ids:
        return

    from src.llm.rate_limit_state import get_rate_limit_store
    store = get_rate_limit_store()

    # Try the first free model
    ping_model = free_ids[0]
    try:
        if _is_go_mode(config=config):
            from src.config_loader import DEFAULT_CONFIG
            ping_cfg = config or DEFAULT_CONFIG
            import copy
            fresh = copy.copy(ping_cfg)
            fresh.llm_mode = "zen"
            from src.llm.providers import _PROVIDER_REGISTRY
            pcls = _PROVIDER_REGISTRY.get(fresh.llm_provider)
            if not pcls:
                return
            provider = pcls(api_key=fresh.opencode_zen_api_key, base_url=fresh.opencode_zen_base_url)
        else:
            from src.llm.providers import _get_provider
            provider = _get_provider(config=config)

        # Minimal ping: 1 token, 1 word
        from src.llm.api_call import _api_call
        await _api_call(
            model=ping_model,
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=1,
            stream=False,
        )
        # Success → clear any stale rate limits on all free models
        for mid in free_ids:
            store.clear_rate_limit(mid)
        logger.info("Free model ping OK: %s — all free models available", ping_model)
    except Exception as e:
        from src.llm.retry import is_rate_limit_error
        if is_rate_limit_error(e):
            # 429 → all free models are rate-limited
            for mid in free_ids:
                store.mark_rate_limited(mid, retry_after=60, detail=str(e)[:200])
            logger.warning("Free model ping 429: %s — all free models rate-limited", ping_model)
        else:
            # Other error → model-specific issue, don't mark all
            logger.info("Free model ping error (non-rate-limit): %s — %s", ping_model, e)
