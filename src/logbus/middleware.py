"""FastAPI middleware for HTTP request logging via LogBus."""

from __future__ import annotations

import time
import uuid
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from src.logbus import LogEvent, get_logbus


class LogBusMiddleware(BaseHTTPMiddleware):
    """Log all HTTP requests to LogBus."""

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        request_id = str(uuid.uuid4())[:12]
        request.state.request_id = request_id
        start = time.time()

        response = await call_next(request)

        duration_ms = (time.time() - start) * 1000
        bus = get_logbus()
        bus.emit(LogEvent(
            level="INFO" if response.status_code < 500 else "ERROR",
            module="web.http",
            msg=f"{request.method} {request.url.path} → {response.status_code}",
            request_id=request_id,
            duration_ms=duration_ms,
            data={
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
            },
        ))

        return response
