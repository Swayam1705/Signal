"""SIGNAL FastAPI application entrypoint."""
from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api.routes import router
from backend.core.config import get_settings
from backend.core.container import Container

logging.basicConfig(level=logging.INFO, format="%(message)s")
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.container = Container(settings)
    app.state.rate_windows = defaultdict(deque)
    yield
    await app.state.container.aclose()


app = FastAPI(
    title="SIGNAL API", version="1.0.0",
    description="Voice → retrieval → grounded answer with end-to-end observability",
    lifespan=lifespan,
    docs_url="/api/docs", openapi_url="/api/openapi.json",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=r"https://.*\.e2b\.app" if settings.app_env == "development" else None,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Accept"],
)


@app.middleware("http")
async def security_and_rate_limit(request: Request, call_next):
    if request.method == "POST" and request.url.path.startswith("/api/"):
        host = request.client.host if request.client else "unknown"
        now = time.monotonic()
        window = request.app.state.rate_windows[host]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= settings.rate_limit_per_minute:
            return JSONResponse(
                status_code=429, content={"detail": "RATE_LIMIT_EXCEEDED"},
                headers={
                    "Retry-After": "60", "X-RateLimit-Limit": str(settings.rate_limit_per_minute),
                    "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY",
                    "Referrer-Policy": "no-referrer", "Cache-Control": "no-store",
                    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
                },
            )
        window.append(now)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    is_data_api = request.url.path.startswith("/api/") and request.url.path not in {"/api/docs", "/api/openapi.json"}
    response.headers["X-Frame-Options"] = "DENY" if is_data_api else "SAMEORIGIN"
    if is_data_api:
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), geolocation=(), payment=()"
    response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api/") else "public, max-age=3600"
    return response


app.include_router(router, prefix=settings.api_prefix)


@app.get("/")
async def root():
    return {"product": "SIGNAL", "tagline": "SPEAK. RETRIEVE. VERIFY.", "api_docs": "/api/docs"}
