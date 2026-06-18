"""FastAPI app factory and bootstrap helpers."""

from __future__ import annotations

import asyncio
import importlib
import logging
import os
import sys
import time
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from dependencies import manage as deps
from src.api import get_repos
from src.api.exceptions import ServiceException
from src.api.repos import init_db, init_memory_db
from src.config_loader import load_config

logger = logging.getLogger(__name__)


class RateLimitStore:
    """Per-IP rate limit store with automatic eviction."""
    def __init__(self, window: float = 60.0, max_ips: int = 1000):
        self._window = window
        self._max_ips = max_ips
        self._store: dict[str, list[float]] = {}

    def check_and_record(self, ip: str, max_requests: int) -> bool:
        now = time.time()
        if len(self._store) > self._max_ips:
            self._evict()
        bucket = self._store.get(ip, [])
        bucket[:] = [t for t in bucket if now - t < self._window]
        if len(bucket) >= max_requests:
            return False
        bucket.append(now)
        self._store[ip] = bucket
        return True

    def _evict(self):
        now = time.time()
        self._store = {k: v for k, v in self._store.items()
                      if v and now - v[-1] < self._window * 2}


_config = None  # Intentional cache: lazily loaded via _get_config()


def _get_config():
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reset_config_cache() -> None:
    """Clear the cached web config so the next access reloads it."""
    global _config
    _config = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    cfg = _get_config()
    app.state.config = cfg
    searxng_started = False
    logbus = None
    # ── Precalentar modelo de embeddings ────────────────────────────
    if not cfg.testing:
        try:
            generate_embedding = importlib.import_module("src.memory.embeddings.service").generate_embedding
            asyncio.create_task(asyncio.to_thread(generate_embedding, "warmup"))
            logger.info("Embedding model preload initiated")
        except Exception:
            pass
    if cfg.testing or os.environ.get("SEARXNG_AUTO_START", "false").lower() in ("1", "true"):
        err = deps.searxng_start()
        if err:
            logger.warning("SearXNG auto-start: %s", err)
        else:
            searxng_started = True
    await init_db()
    await init_memory_db()
    importlib.import_module("src.memory.deleted_sessions_db").init_deleted_sessions_db()
    # ── Composition Root: Repositories ─────────────────────────
    repos = get_repos()
    app.state.repos = repos
    # ── Composition Root: Connection Pool ─────────────────────
    from src.memory.connection_pool import ConnectionPool, configure_connection_pool
    pool = ConnectionPool(max_connections=5)
    configure_connection_pool(pool)
    app.state.connection_pool = pool
    logger.info("Composition root: Connection pool created and injected")
    logger.info("Composition root: Repositories created and injected")
    # ── Composition Root: LogBus ─────────────────────────────────
    logbus = None
    try:
        from src.logbus import get_logbus
        from src.logbus.writers import JsonlWriter, ConsoleWriter, SqliteWriter
        logbus = get_logbus()
        app.state.logbus = logbus
        logbus.add_writer(JsonlWriter())
        logbus.add_writer(SqliteWriter())
        if os.environ.get("LOG_LEVEL", "").upper() == "DEBUG":
            logbus.add_writer(ConsoleWriter())
        await logbus.start()
    except Exception:
        pass

    # ── Composition Root: Core Services ──────────────────────────
    from src.core.services.telemetry_service import TelemetryService
    from src.core.services.history_service import HistoryService
    from src.core.services.llm_service import LLMService
    from src.core.services.tool_execution_service import ToolExecutionService
    from src.core.services.retrieval_service import RetrievalService

    telemetry_service = TelemetryService(logbus=logbus)
    app.state.telemetry_service = telemetry_service
    app.state.history_service = HistoryService(repos=repos)
    app.state.llm_service = LLMService(telemetry_service=telemetry_service)
    app.state.tool_service = ToolExecutionService()
    app.state.retrieval_service = RetrievalService(config=cfg)
    logger.info("Composition root: Core services created and injected")
    # ── Composition Root: LLM Container ──────────────────────────
    from src.llm.container import LLMContainer, configure_container
    llm_container = LLMContainer(config=cfg)
    app.state.llm_container = llm_container
    configure_container(llm_container)
    logger.info("Composition root: LLM Container created and injected")

    # Wire LLM sub-services into app.state for easy access
    app.state.circuit_breaker = llm_container.get_circuit_breaker()
    app.state.rate_limit_store = llm_container.get_rate_limit_store()
    app.state.model_registry = llm_container.get_model_registry()
    try:
        from src.api import SkillRegistry
        SkillRegistry().generate_index_md()
    except Exception as e:
        logger.warning("Failed to generate skills INDEX.md: %s", e)
    if not cfg.testing:
        from src.api import get_verified_models
        try:
            await asyncio.wait_for(get_verified_models(), timeout=10)
        except asyncio.TimeoutError:
            logger.warning("Model discovery timed out (10s) — will lazy-load on first request")
        except Exception as e:
            logger.warning("Failed to schedule model discovery: %s", e)
        # Auto-refresh the dynamic model registry
        try:
            from src.api import ensure_registry_refreshed
            await asyncio.wait_for(ensure_registry_refreshed(), timeout=10)
        except Exception:
            pass  # registry will lazy-refresh on first request
        # Preload embedding model so first chat request doesn't wait 6+ seconds
        try:
            get_model = importlib.import_module("src.memory.embeddings.service").get_model
            model = await asyncio.to_thread(get_model)
            if model is not None:
                logger.info("Embedding model preloaded successfully")
            else:
                logger.warning("Embedding model not available at startup (will lazy-load)")
        except Exception as e:
            logger.warning("Embedding model preload failed (non-fatal): %s", e)
    yield
    if searxng_started:
        deps.searxng_stop()
    # Unload ML models to free memory on shutdown
    try:
        unload_embeddings = importlib.import_module("src.memory.embeddings.service").unload_model
        unload_embeddings()
    except Exception:
        pass
    try:
        unload_reranker = importlib.import_module("src.memory.retrieval.reranker").unload_model
        unload_reranker()
    except Exception:
        pass
    try:
        if logbus is not None:
            await logbus.stop()
    except Exception:
        pass
    try:
        from src.api.lifecycle import reset_runtime_state
        reset_runtime_state()
    except Exception:
        pass
    try:
        reset_config_cache()
    except Exception:
        pass
    try:
        from web.services.event_bus import reset_event_bus
        reset_event_bus()
    except Exception:
        pass
    logger.info("ML models unloaded on shutdown")

def register_middlewares(app: FastAPI) -> None:
    from src.logbus.middleware import LogBusMiddleware
    app.add_middleware(LogBusMiddleware)
    if not hasattr(app.state, "http_rate_limit_store"):
        app.state.http_rate_limit_store = RateLimitStore()

    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        if request.method not in ("POST", "PUT", "DELETE", "PATCH"):
            return await call_next(request)
        client_ip = request.client.host if request.client else "unknown"
        rate_limit_store = getattr(request.app.state, "http_rate_limit_store", None) or RateLimitStore()
        if not rate_limit_store.check_and_record(client_ip, _get_config().http_rate_limit):
            return JSONResponse({"detail": "Rate limit exceeded. Try again later."}, status_code=429)
        return await call_next(request)

    @app.middleware("http")
    async def csp_middleware(request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob: https:; "
            "frame-src 'self' 'unsafe-inline' https:; "
            "connect-src 'self'"
        )
        return response

    @app.middleware("http")
    async def add_no_cache_headers(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        response = await call_next(request)
        if request.url.path.startswith("/static"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ServiceException)
    def service_exception(request: Request, exc: ServiceException) -> JSONResponse:
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

    @app.exception_handler(404)
    def not_found(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse({"detail": "Not found"}, status_code=404)

    @app.exception_handler(RequestValidationError)
    def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=422)

    @app.exception_handler(Exception)
    def server_error(request: Request, exc: Exception) -> JSONResponse:
        logger.error("Internal error in %s: %s", request.url.path, exc)
        return JSONResponse({"detail": "Internal server error"}, status_code=500)


def register_routers(app: FastAPI) -> None:
    routers_dir = Path(__file__).parent / "routers"
    for f in sorted(routers_dir.iterdir()):
        if not f.is_file() or not f.name.endswith(".py") or f.name.startswith("_"):
            continue
        mod_name = f.stem
        try:
            mod = importlib.import_module(f"web.routers.{mod_name}")
            if hasattr(mod, "router"):
                app.include_router(mod.router)
                logger.debug("Router loaded: %s", mod_name)
        except Exception as e:
            logger.warning("Router %s: error loading (%s), skipped", mod_name, e)

def setup_logging() -> None:
    """Configure root logger for the web server process.

    Called once at app creation — ensures all ``logger.info(...)`` calls
    from web services (chat_stream, routers, etc.) actually go somewhere.
    Also installs the structured JSONL handler for persistent searchable logs.
    """
    cfg = _get_config()
    log_level = getattr(logging, cfg.log_level.upper(), logging.INFO)

    # Only configure if root logger has no handlers yet (idempotent)
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(
            level=log_level,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
            stream=sys.stderr,
        )

    # Install JSONL handler for the whole "web" tree
    try:
        from web.services.file_logger import install_jsonl_handler
        install_jsonl_handler("web")
    except Exception:
        pass  # non-fatal




def create_app() -> FastAPI:
    setup_logging()
    app = FastAPI(lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

    # ── Composition Root: create & inject all Lego blocks ────────────
    from web.services.event_bus import EventBus, set_event_bus
    from src.api import SkillRegistry
    event_bus = EventBus()
    set_event_bus(event_bus)
    app.state.event_bus = event_bus
    app.state.skill_registry = SkillRegistry()
    logger.info("Composition root: EventBus created and injected")

    register_middlewares(app)
    register_exception_handlers(app)
    register_routers(app)
    return app
