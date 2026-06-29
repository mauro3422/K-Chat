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
from src.api.exceptions import ServiceException
from src.api.llm_client import get_verified_models, ensure_registry_refreshed
from src.api.repos import get_repos
from src.api.skills import SkillRegistry
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



def reset_web_runtime_state() -> None:
    """Reset web-layer process-local state owned by the composition root."""
    try:
        from web.services.file_logger import reset_log_dirs
        reset_log_dirs()
    except Exception:
        logger.warning("Failed to reset web log dirs", exc_info=True)

    try:
        from web.services.model_catalog import reset_model_cache
        reset_model_cache()
    except Exception:
        logger.warning("Failed to reset model cache", exc_info=True)

    try:
        from web.services.event_bus import reset_event_bus
        reset_event_bus()
    except Exception:
        logger.warning("Failed to reset event bus", exc_info=True)

    try:
        from src.coordination.node_state import reset_node_coordinator
        reset_node_coordinator()
    except Exception:
        logger.warning("Failed to reset node coordinator", exc_info=True)

    try:
        from src.coordination.memory_write_queue import reset_memory_write_queue
        reset_memory_write_queue()
    except Exception:
        logger.warning("Failed to reset memory write queue", exc_info=True)

    try:
        from src.coordination.memory_lease import reset_memory_lease_manager
        reset_memory_lease_manager()
    except Exception:
        logger.warning("Failed to reset memory lease manager", exc_info=True)

    try:
        from src.coordination.leader_lease import reset_leader_lease_manager
        reset_leader_lease_manager()
    except Exception:
        logger.warning("Failed to reset leader lease manager", exc_info=True)



def _wire_llm_runtime_state(llm_container, app_state=None) -> None:
    """Align app-state LLM services with the process-local helper caches."""
    from src.llm.circuit_breaker import configure_breaker
    from src.llm.rate_limit_state import configure_rate_limit_store

    breaker = llm_container.get_circuit_breaker()
    rate_limit_store = llm_container.get_rate_limit_store()

    configure_breaker(breaker)
    configure_rate_limit_store(rate_limit_store)

    if app_state is not None:
        app_state.circuit_breaker = breaker
        app_state.rate_limit_store = rate_limit_store
        app_state.model_registry = llm_container.get_model_registry()


def _ensure_llm_runtime_state(app: FastAPI, cfg=None):
    """Create the LLM container once and expose its shared runtime state."""
    from src.llm.container import LLMContainer

    llm_container = getattr(app.state, "llm_container", None)
    if llm_container is None:
        llm_container = LLMContainer(config=cfg or getattr(app.state, "config", None))
        app.state.llm_container = llm_container
    _wire_llm_runtime_state(llm_container, app.state)
    return llm_container


def _ensure_core_services(app: FastAPI, cfg=None, repos=None, logbus=None) -> None:
    """Expose core services required by routes that may run before lifespan."""
    from src.core.services.telemetry_service import TelemetryService
    from src.core.services.history_service import HistoryService
    from src.core.services.llm_service import LLMService
    from src.core.services.tool_execution_service import ToolExecutionService
    from src.core.services.retrieval_service import RetrievalService

    cfg = cfg or getattr(app.state, "config", None)
    repos = repos or getattr(app.state, "repos", None) or get_repos()
    logbus = logbus if logbus is not None else getattr(app.state, "logbus", None)
    llm_container = _ensure_llm_runtime_state(app, cfg)

    app.state.repos = repos
    if not hasattr(app.state, "telemetry_service"):
        app.state.telemetry_service = TelemetryService(logbus=logbus)
    if not hasattr(app.state, "history_service"):
        app.state.history_service = HistoryService(repos=repos)
    if not hasattr(app.state, "tool_service"):
        app.state.tool_service = ToolExecutionService()
    if not hasattr(app.state, "retrieval_service"):
        app.state.retrieval_service = RetrievalService(config=cfg)
    if not hasattr(app.state, "llm_service"):
        app.state.llm_service = LLMService(
            telemetry_service=app.state.telemetry_service,
            model_registry=llm_container.get_model_registry(),
        )


async def _prime_verified_model_cache(app: FastAPI, timeout: float = 10) -> None:
    """Prime the shared model registry used by HTTP requests."""
    from src.llm.model_registry import configure_model_registry

    cfg = app.state.config
    model_registry = app.state.model_registry
    configure_model_registry(model_registry)

    try:
        await asyncio.wait_for(ensure_registry_refreshed(), timeout=timeout)
    except Exception:
        logger.warning("Registry refresh failed, will lazy-refresh on first request", exc_info=True)
        return

    if getattr(cfg, "llm_mode", "go") == "go":
        verified = model_registry.get_all_models()
        model_registry.set_verified_models(verified)
        logger.info("Go mode: primed verified model cache with %d models", len(verified))
        return

    try:
        await asyncio.wait_for(get_verified_models(config=cfg), timeout=timeout)
    except Exception as e:
        logger.warning("Failed to prime verified model cache: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    cfg = getattr(app.state, "config", None) or load_config()
    app.state.config = cfg
    searxng_started = False
    logbus = None
    if cfg.testing or os.environ.get("SEARXNG_AUTO_START", "false").lower() in ("1", "true"):
        err = deps.searxng_start()
        if err:
            logger.warning("SearXNG auto-start: %s", err)
        else:
            searxng_started = True
    await init_db()
    await init_memory_db()
    importlib.import_module("src.memory.deleted_sessions_db").init_deleted_sessions_db()
    # â”€â”€ Composition Root: Repositories â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    repos = get_repos()
    app.state.repos = repos
    # â”€â”€ Composition Root: Connection Pool â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    from src.memory.connection_pool import ConnectionPool, configure_connection_pool
    pool = ConnectionPool(max_connections=5)
    configure_connection_pool(pool)
    app.state.connection_pool = pool
    logger.info("Composition root: Connection pool created and injected")
    logger.info("Composition root: Repositories created and injected")
    # â”€â”€ Composition Root: LogBus â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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
        logger.warning("Failed to start LogBus", exc_info=True)

    # â”€â”€ Composition Root: Core Services â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    _ensure_core_services(app, cfg=cfg, repos=repos, logbus=logbus)
    logger.info("Composition root: Core services created and injected")
    # â”€â”€ Composition Root: LLM Container â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    _ensure_llm_runtime_state(app, cfg)
    logger.info("Composition root: LLM Container created and injected")
    from src.coordination.node_state import get_node_coordinator
    from src.coordination.lan_bridge import NodeLanBridge
    if not hasattr(app.state, "node_coordinator"):
        app.state.node_coordinator = get_node_coordinator(cfg)
    if not hasattr(app.state, "node_bridge"):
        app.state.node_bridge = NodeLanBridge(
            config=cfg,
            coordinator=app.state.node_coordinator,
            on_primary_yield=lambda reason: app.state.failover_state.reset(reason),
        )
    try:
        if await app.state.node_coordinator.is_primary():
            from src.coordination.memory_write_queue import apply_pending_memory_writes

            applied = await apply_pending_memory_writes(
                app.state.memory_write_queue,
                app.state.save_memory_run,
                repos=getattr(app.state, "repos", None),
            )
            if applied:
                await app.state.node_coordinator.mark_memory_sync({"event": "startup_flush", "applied": len(applied)})
    except Exception:
        logger.warning("Failed to auto-flush persisted memory queue on startup", exc_info=True)
    if not cfg.testing:
        async def _generate_skills_index() -> None:
            try:
                await asyncio.to_thread(SkillRegistry().generate_index_md)
            except Exception as e:
                logger.warning("Failed to generate skills INDEX.md: %s", e)

        asyncio.create_task(_generate_skills_index())

        async def _prime_model_registry() -> None:
            await _prime_verified_model_cache(app)

        asyncio.create_task(_prime_model_registry())

        if os.environ.get("KAIROS_WARMUP_EMBEDDINGS", "false").lower() in ("1", "true"):
            try:
                get_model = importlib.import_module("src.memory.embeddings.service").get_model
                model = await asyncio.to_thread(get_model)
                if model is not None:
                    logger.info("Embedding model preloaded successfully")
                else:
                    logger.warning("Embedding model not available at startup (will lazy-load)")
            except Exception as e:
                logger.warning("Embedding model preload failed (non-fatal): %s", e)

    configured_peers = getattr(cfg, "peer_urls", "")
    has_static_peers = isinstance(configured_peers, str) and bool(configured_peers.strip())
    discovery_enabled = bool(getattr(cfg, "lan_discovery_enabled", True)) and not bool(cfg.testing)

    if discovery_enabled:
        from src.coordination.lan_discovery import LanDiscovery

        app.state.lan_discovery = LanDiscovery(
            cfg,
            on_peer=app.state.node_bridge.register_discovered_peer,
        )
        app.state.lan_discovery_task = asyncio.create_task(app.state.lan_discovery.run())

    if has_static_peers or discovery_enabled:
        async def _sync_node_heartbeats() -> None:
            try:
                await app.state.node_bridge.broadcast_once()
                while True:
                    await asyncio.sleep(app.state.node_bridge.interval)
                    await app.state.node_bridge.broadcast_once()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning("Node LAN heartbeat loop stopped: %s", e, exc_info=True)

        app.state.node_bridge_task = asyncio.create_task(_sync_node_heartbeats())

        async def _monitor_node_failover() -> None:
            try:
                while True:
                    ttl = float(getattr(cfg, "node_heartbeat_ttl", 15.0) or 15.0)
                    interval = float(getattr(cfg, "node_failover_check_interval", 0.0) or 0.0)
                    if interval <= 0:
                        interval = max(1.0, ttl / 3.0)
                    await asyncio.sleep(interval)
                    coordinator = app.state.node_coordinator
                    failover_state = app.state.failover_state
                    if await coordinator.is_primary():
                        failover_state.reset("already_primary")
                        continue
                    if await coordinator.has_recent_primary():
                        failover_state.note_check(primary_seen=True, reason="recent_primary")
                        continue
                    failover_state.note_check(primary_seen=False, reason="missing_primary")
                    if failover_state.miss_count < failover_state.required_misses:
                        continue

                    lease_manager = app.state.leader_lease_manager
                    lease = lease_manager.acquire(
                        coordinator.node_id,
                        ttl=ttl,
                        reason="leader_election",
                    )
                    if lease is None:
                        failover_state.last_action = "lease_busy"
                        failover_state.last_reason = "leader_lease_busy"
                        continue

                    snapshot = await coordinator.promote()
                    failover_state.note_promotion(reason="leader_election")
                    try:
                        await app.state.event_bus.publish("leader_changed", {"role": "primary", "state": snapshot})
                    except Exception:
                        logger.warning("Failed to publish leader_changed after failover", exc_info=True)
                    try:
                        await app.state.node_bridge.broadcast_once()
                    except Exception:
                        logger.warning("Node LAN heartbeat broadcast failed after failover", exc_info=True)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning("Node failover monitor stopped: %s", e, exc_info=True)

        app.state.node_failover_task = asyncio.create_task(_monitor_node_failover())
    yield
    if searxng_started:
        deps.searxng_stop()
    # Unload ML models to free memory on shutdown
    try:
        unload_embeddings = importlib.import_module("src.memory.embeddings.service").unload_model
        unload_embeddings()
    except Exception:
        logger.warning("Failed to unload embeddings on shutdown", exc_info=True)
    try:
        unload_reranker = importlib.import_module("src.memory.retrieval.reranker").unload_model
        unload_reranker()
    except Exception:
        logger.warning("Failed to unload reranker on shutdown", exc_info=True)
    try:
        if logbus is not None:
            await logbus.stop()
    except Exception:
        logger.warning("Failed to stop LogBus on shutdown", exc_info=True)
    try:
        discovery = getattr(app.state, "lan_discovery", None)
        discovery_task = getattr(app.state, "lan_discovery_task", None)
        if discovery is not None:
            discovery.stop()
        if discovery_task is not None:
            discovery_task.cancel()
            try:
                await discovery_task
            except asyncio.CancelledError:
                pass
    except Exception:
        logger.warning("Failed to stop LAN discovery task on shutdown", exc_info=True)
    try:
        node_task = getattr(app.state, "node_bridge_task", None)
        if node_task is not None:
            node_task.cancel()
            try:
                await node_task
            except asyncio.CancelledError:
                pass
    except Exception:
        logger.warning("Failed to stop node LAN bridge task on shutdown", exc_info=True)
    try:
        failover_task = getattr(app.state, "node_failover_task", None)
        if failover_task is not None:
            failover_task.cancel()
            try:
                await failover_task
            except asyncio.CancelledError:
                pass
    except Exception:
        logger.warning("Failed to stop node failover task on shutdown", exc_info=True)
    try:
        reset_web_runtime_state()
    except Exception:
        logger.warning("Failed to reset web runtime state on shutdown", exc_info=True)
    try:
        from src.api.lifecycle import reset_runtime_state_async
        await reset_runtime_state_async()
    except Exception:
        logger.warning("Failed to reset runtime state on shutdown", exc_info=True)

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
        if not rate_limit_store.check_and_record(client_ip, app.state.config.http_rate_limit):
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
                app.router.routes.extend(mod.router.routes)
                logger.debug("Router loaded: %s", mod_name)
        except Exception as e:
            logger.warning("Router %s: error loading (%s), skipped", mod_name, e)

def setup_logging(cfg) -> None:
    """Configure root logger for the web server process.

    Called once at app creation — ensures all ``logger.info(...)`` calls
    from web services (chat_stream, routers, etc.) actually go somewhere.
    Also installs the structured JSONL handler for persistent searchable logs.
    """
    log_level = getattr(logging, cfg.log_level.upper(), logging.INFO)

    # Only configure if root logger has no handlers yet (idempotent)
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(
            level=log_level,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
            stream=sys.stderr,
        )

    # httpx logs every successful LAN heartbeat at INFO. Keep transport
    # failures visible while avoiding repetitive request noise.
    logging.getLogger("httpx").setLevel(logging.WARNING)

    # Install JSONL handler for the whole "web" tree
    try:
        from web.services.file_logger import install_jsonl_handler
        install_jsonl_handler("web")
    except Exception:
        logger.warning("Failed to install JSONL handler", exc_info=True)




def create_app() -> FastAPI:
    cfg = load_config()
    setup_logging(cfg)
    app = FastAPI(lifespan=lifespan)
    app.state.config = cfg
    app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

    # â”€â”€ Composition Root: create & inject all Lego blocks â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    from web.services.event_bus import EventBus, set_event_bus
    from web.services.failover_state import FailoverState, configure_failover_state
    from web.services.telegram_reflection import TelegramReflectionState, configure_telegram_reflection_state
    from src.coordination.memory_write_queue import get_memory_write_queue, configure_memory_write_queue
    from src.coordination.memory_lease import get_memory_lease_manager, configure_memory_lease_manager
    from src.coordination.leader_lease import get_leader_lease_manager, configure_leader_lease_manager
    from src.coordination.node_state import get_node_coordinator, configure_node_coordinator
    from src.tools.manage_memory import run as manage_memory_run
    from src.tools.save_memory import run as save_memory_run
    from src.logbus import get_logbus
    event_bus = EventBus()
    set_event_bus(event_bus)
    app.state.event_bus = event_bus
    app.state.telegram_reflection_state = TelegramReflectionState()
    configure_telegram_reflection_state(app.state.telegram_reflection_state)
    app.state.failover_state = FailoverState(required_misses=max(2, int(getattr(cfg, "node_failover_required_misses", 2) or 2)))
    configure_failover_state(app.state.failover_state)
    node_coordinator = get_node_coordinator(cfg)
    configure_node_coordinator(node_coordinator)
    app.state.node_coordinator = node_coordinator
    app.state.memory_write_queue = get_memory_write_queue(cfg)
    configure_memory_write_queue(app.state.memory_write_queue)
    app.state.memory_lease_manager = get_memory_lease_manager(cfg)
    configure_memory_lease_manager(app.state.memory_lease_manager)
    app.state.leader_lease_manager = get_leader_lease_manager(cfg)
    configure_leader_lease_manager(app.state.leader_lease_manager)
    app.state.manage_memory_run = manage_memory_run
    app.state.save_memory_run = save_memory_run
    app.state.skill_registry = SkillRegistry()
    app.state.logbus = get_logbus()
    _ensure_core_services(app, cfg=cfg, logbus=app.state.logbus)
    logger.info("Composition root: EventBus created and injected")

    register_middlewares(app)
    register_exception_handlers(app)
    register_routers(app)
    return app




