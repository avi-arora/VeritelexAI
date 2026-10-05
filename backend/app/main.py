"""FastAPI application factory.

Roles (``VTX_ROLE``):
* ``all``    — local development: API + in-process agent execution.
* ``api``    — Cloud Run *api* service: public REST API, dispatches to Cloud Tasks.
* ``worker`` — Cloud Run *worker* service: executes agent steps from Cloud Tasks.

Run locally (binds to loopback only)::

    uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import Settings, get_settings
from app.container import build_container
from app.harness.dispatcher import LocalDispatcher
from app.logging_setup import configure_logging, get_logger

log = get_logger(__name__)

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cache-Control": "no-store",
    "Cross-Origin-Resource-Policy": "same-site",
}


class RateLimiter:
    """Small in-memory sliding-window limiter (per client, per minute).

    Per-instance only; Cloud Run's max-instances and the private ingress are the
    outer bounds. Adequate for a POC — use Cloud Armor / API Gateway for production.
    """

    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        t = time.monotonic()
        q = self._hits[key]
        while q and t - q[0] > 60:
            q.popleft()
        if len(q) >= self.per_minute:
            return False
        q.append(t)
        if len(self._hits) > 10_000:  # bound memory
            self._hits = defaultdict(deque, {k: v for k, v in self._hits.items() if v and t - v[-1] < 60})
        return True


def create_app(settings: Settings | None = None) -> FastAPI:
    s = settings or get_settings()
    configure_logging(json_logs=s.env == "prod")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.container = build_container(s)
        resume: asyncio.Task | None = None
        if isinstance(app.state.container.dispatcher, LocalDispatcher):
            # In-memory deliveries are lost on restart: resume active runs from their checkpoints.
            resume = asyncio.create_task(app.state.container.orchestrator.resume_active_runs())
        log.info("VeriteLex backend started (env=%s role=%s dispatcher=%s)", s.env, s.role, s.dispatcher)
        yield
        if resume and not resume.done():
            resume.cancel()
        try:
            await app.state.container.council.aclose()
        except Exception:  # noqa: BLE001 - best effort on shutdown
            log.warning("could not close the council HTTP client", exc_info=True)

    app = FastAPI(
        title="VeriteLex AI backend", version="0.1.0", lifespan=lifespan,
        docs_url="/docs" if s.env == "local" else None, redoc_url=None,
        openapi_url="/openapi.json" if s.env == "local" else None,
    )

    if s.serves_api:
        from app.api.routes import router as api_router

        app.include_router(api_router)
    if s.serves_worker and s.dispatcher == "cloud_tasks":
        from app.internal.tasks import router as tasks_router

        app.include_router(tasks_router)

    app.add_middleware(
        CORSMiddleware, allow_origins=s.cors_origins, allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH"], allow_headers=["Content-Type"], max_age=600,
    )
    limiter = RateLimiter(s.rate_limit_per_minute)

    @app.middleware("http")
    async def guard(request: Request, call_next):  # type: ignore[no-untyped-def]
        path = request.url.path
        if path.startswith("/api/"):
            client = request.client.host if request.client else "unknown"
            if not limiter.allow(client):
                return JSONResponse({"detail": "Too many requests"}, status_code=429, headers=SECURITY_HEADERS)
        response = await call_next(request)
        for k, v in SECURITY_HEADERS.items():
            if k == "Content-Security-Policy" and path in ("/docs", "/openapi.json"):
                continue  # Swagger UI (local only) needs scripts
            response.headers.setdefault(k, v)
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [{"loc": e.get("loc"), "msg": e.get("msg")} for e in exc.errors()]  # no input echo
        return JSONResponse({"detail": "Invalid request", "errors": errors}, status_code=422)

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error", exc_info=exc)
        return JSONResponse({"detail": "Internal error"}, status_code=500)

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
