import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError

from src.memory import init_db
from web.routers import pages, chat, sessions, widgets, debug

app = FastAPI()
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")


@app.exception_handler(404)
async def not_found(request: Request, exc):
    return HTMLResponse("<h1>404 - No encontrado</h1><a href='/'>Volver</a>", status_code=404)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc):
    return JSONResponse({"error": "Datos inválidos", "detail": str(exc)}, status_code=422)


@app.exception_handler(Exception)
async def server_error(request: Request, exc):
    logger = logging.getLogger(__name__)
    logger.error("Error interno en %s: %s", request.url.path, exc)
    return HTMLResponse("<h1>500 - Error interno</h1><p>Ocurrió un error inesperado.</p>", status_code=500)


@app.middleware("http")
async def add_no_cache_headers(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


app.include_router(pages.router)
app.include_router(chat.router)
app.include_router(sessions.router)
app.include_router(widgets.router)
app.include_router(debug.router)

init_db()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
