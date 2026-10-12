"""FastAPI application factory (``uvicorn adintel.api.app:create_app --factory``)."""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import generate_latest

from adintel import __version__
from adintel.api.routers import admin, approvals, auth, brands, chat, kb, ops, runs, scim, status, verify
from adintel.config import get_settings
from adintel.observability import context
from adintel.observability.alerts import install_security_hooks
from adintel.observability.logging import configure_logging
from adintel.observability.metrics import HTTP_LATENCY, HTTP_REQUESTS, REGISTRY
from adintel.observability.tracing import configure_tracing
from adintel.storage import get_database

log = logging.getLogger("adintel.api")

API_VERSION = 1
# Request path (e.g. "/v1/brands") → HTTP-date after which it may be removed. Announced ≥ 6 months ahead (docs/17-api/versioning.md).
DEPRECATED: dict[str, str] = {}

SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
}


def create_app(*, start_inline_worker: bool | None = None) -> FastAPI:
    s = get_settings()
    configure_logging(s.log_level, s.log_json)
    configure_tracing("adintel-api", s.otel_endpoint)
    install_security_hooks()
    # Interactive docs are an attack-surface map: on locally, off in staging/production unless asked for.
    docs = s.api_docs if s.api_docs is not None else s.env in ("local", "test")
    app = FastAPI(
        docs_url="/docs" if docs else None,
        redoc_url="/redoc" if docs else None,
        openapi_url="/openapi.json" if docs else None,
        title="AdIntel API",
        version=__version__,
        description="Enterprise-governed multi-agent paid-ad intelligence. AI proposes; humans approve.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type", "Last-Event-ID"],
    )

    @app.middleware("http")
    async def limit_body(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        """Refuse oversized bodies before they are read (memory exhaustion, giant prompts)."""
        declared = request.headers.get("content-length")
        if request.method in ("POST", "PUT", "PATCH"):
            if declared is None and "chunked" in request.headers.get("transfer-encoding", ""):
                return JSONResponse({"detail": "chunked request bodies are not accepted"}, status_code=411)
            if declared is not None and (not declared.isdigit() or int(declared) > s.max_request_bytes):
                return JSONResponse({"detail": f"request body exceeds {s.max_request_bytes} bytes"}, status_code=413)
        return await call_next(request)

    @app.middleware("http")
    async def observe(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        t0 = time.perf_counter()
        with context.bind(request_id=rid):
            response = await call_next(request)
        route = request.scope.get("route")
        path = getattr(route, "path", "unmatched")
        HTTP_REQUESTS.labels(route=path, method=request.method, status=str(response.status_code)).inc()
        HTTP_LATENCY.labels(route=path).observe(time.perf_counter() - t0)
        response.headers["X-Request-ID"] = rid
        for k, v in SECURITY_HEADERS.items():
            if k == "Cache-Control" and response.headers.get("content-type", "").startswith("text/event-stream"):
                continue
            response.headers.setdefault(k, v)
        response.headers["X-AdIntel-API-Version"] = str(API_VERSION)
        sunset = DEPRECATED.get(request.url.path)
        if sunset:  # RFC 8594 / draft-ietf-httpapi-deprecation-header
            response.headers["Deprecation"] = "true"
            response.headers["Sunset"] = sunset
            response.headers["Link"] = '</docs/17-api/versioning.md>; rel="deprecation"'
        if s.env in ("staging", "production"):
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled_error", extra={"path": request.url.path})
        return JSONResponse({"detail": "internal error"}, status_code=500)

    @app.get("/health", tags=["ops"])
    def health() -> dict[str, Any]:
        return {"status": "ok", "version": s.system_version}

    @app.get("/ready", tags=["ops"])
    def ready() -> Response:
        ok = get_database().ping()
        return JSONResponse({"database": ok}, status_code=200 if ok else 503)

    @app.get("/metrics", tags=["ops"], include_in_schema=False)
    def metrics() -> PlainTextResponse:
        from adintel.observability.host import sample

        sample()  # refresh host gauges on every scrape
        return PlainTextResponse(generate_latest(REGISTRY).decode(), media_type="text/plain; version=0.0.4")

    # Versioned integrator contract (/v1/...) for the business API; the unversioned paths are the same routes
    # for the web app. Infrastructure routes (SCIM, webhooks, provenance) have their own stable paths.
    versioned = (auth.router, brands.router, runs.router, approvals.router, chat.router, kb.router, admin.router, status.router)
    for r in versioned:
        app.include_router(r)
        app.include_router(r, prefix=f"/v{API_VERSION}")
    for r in (ops.router, scim.router, verify.router):
        app.include_router(r)

    inline = start_inline_worker if start_inline_worker is not None else s.queue == "memory" and s.env == "local"
    if inline:
        # the in-memory queue is per-process, so local single-process mode runs the worker in-process
        @app.on_event("startup")
        def _start_worker() -> None:
            from adintel.workers.agent_worker import Worker

            threading.Thread(target=Worker().loop, name="inline-agent-worker", daemon=True).start()

    return app
