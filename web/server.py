import logging
import os
import time
import importlib
from collections import defaultdict
from collections.abc import AsyncGenerator, Callable, Awaitable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError

from src.api import init_db
from dependencies import manage as deps

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    if os.environ.get("SEARXNG_AUTO_START", "true").lower() in ("1", "true"):
        err = deps.searxng_start()
        if err:
            logger.warning("SearXNG auto-start: %s", err)
    init_db()
    yield
    deps.searxng_stop()


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

_rate_limit_store: dict[str, list[float]] = defaultdict(list)
_RATE_LIMIT = int(os.environ.get("HTTP_RATE_LIMIT", "60"))
_RATE_WINDOW = 60.0


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    if request.url.path.startswith("/static"):
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
        "script-src 'self' https://unpkg.com 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "frame-src 'self'; "
        "connect-src 'self'"
    )
    return response


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


@app.middleware("http")
async def add_no_cache_headers(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    response = await call_next(request)
    if request.url.path.startswith("/static"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


# Auto-discover routers from web/routers/*.py
_routers_dir = Path(__file__).parent / "routers"
for f in sorted(_routers_dir.iterdir()):
    if not f.is_file() or not f.name.endswith('.py') or f.name.startswith('_'):
        continue
    mod_name = f.stem
    try:
        mod = importlib.import_module(f'web.routers.{mod_name}')
        if hasattr(mod, 'router'):
            app.include_router(mod.router)
            logger.debug("Router loaded: %s", mod_name)
    except Exception as e:
        logger.warning("Router %s: error loading (%s), skipped", mod_name, e)


if __name__ == "__main__":
    import uvicorn
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("web.server:app", host=host, port=port, reload=True, reload_dirs=["web", "src"])
