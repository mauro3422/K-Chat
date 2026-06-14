"""FastAPI app factory and bootstrap helpers."""

from __future__ import annotations

import asyncio
import importlib
import logging
import os
import time
from collections import defaultdict
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from dependencies import manage as deps
from src.api.exceptions import ServiceException
from src.config_loader import DEFAULT_CONFIG
from src.memory.schema import init_db

logger = logging.getLogger(__name__)

_rate_limit_store: dict[str, list[float]] = defaultdict(list)
_RATE_LIMIT = DEFAULT_CONFIG.http_rate_limit
_RATE_WINDOW = 60.0


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    searxng_started = False
    if DEFAULT_CONFIG.testing or os.environ.get("SEARXNG_AUTO_START", "false").lower() in ("1", "true"):
        err = deps.searxng_start()
        if err:
            logger.warning("SearXNG auto-start: %s", err)
        else:
            searxng_started = True
    await init_db()
    try:
        from src.skills import SkillRegistry
        SkillRegistry().generate_index_md()
    except Exception as e:
        logger.warning("Failed to generate skills INDEX.md: %s", e)
    if not DEFAULT_CONFIG.testing:
        from src.llm.discovery import get_verified_models
        try:
            await asyncio.wait_for(get_verified_models(), timeout=10)
        except asyncio.TimeoutError:
            logger.warning("Model discovery timed out (10s) — will lazy-load on first request")
        except Exception as e:
            logger.warning("Failed to schedule model discovery: %s", e)
        # Auto-refresh the dynamic model registry
        try:
            from src.llm.model_registry import ensure_registry_refreshed
            await asyncio.wait_for(ensure_registry_refreshed(), timeout=10)
        except Exception:
            pass  # registry will lazy-refresh on first request
    yield
    if searxng_started:
        deps.searxng_stop()


def register_middlewares(app: FastAPI) -> None:
    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        if request.method not in ("POST", "PUT", "DELETE", "PATCH"):
            return await call_next(request)
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        bucket = _rate_limit_store[client_ip]
        bucket[:] = [t for t in bucket if now - t < _RATE_WINDOW]
        if len(bucket) >= _RATE_LIMIT:
            return JSONResponse({"detail": "Rate limit exceeded. Try again later."}, status_code=429)
        bucket.append(now)
        return await call_next(request)

    @app.middleware("http")
    async def csp_middleware(request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; "
            "frame-src 'self'; "
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


def create_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
    register_middlewares(app)
    register_exception_handlers(app)
    register_routers(app)
    return app
