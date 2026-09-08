"""Atlas API.

FastAPI application. Everything financial is delegated to the engines; this
layer handles transport, validation, authorization and persistence.
"""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from atlas_financial_engine import __version__ as engine_version

from .auth import verify_startup_configuration
from .config import get_settings
from .db import init_db
from .routers import analyses, dashboard, leads, properties, settings as settings_router

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("atlas.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Refuse to start a production API without real authentication rather than
    # silently serving every user's pipeline under a shared development identity.
    verify_startup_configuration(settings)
    init_db()
    if not settings.auth_configured:
        logger.warning(
            "running with DEVELOPMENT authentication — every request is the local "
            "user. Set SUPABASE_JWT_SECRET before exposing this API."
        )
    logger.info("Atlas API ready (engine %s)", engine_version)
    yield


app = FastAPI(
    title="Atlas API",
    description=(
        "Real-estate acquisition and investment intelligence. All financial "
        "calculations are performed by a deterministic engine; AI output is "
        "interpretation only and is labelled as such."
    ),
    version=engine_version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    """Attach a request id and log timing for every call."""
    request_id = str(uuid.uuid4())
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "unhandled error [%s] %s %s", request_id, request.method, request.url.path
        )
        raise
    duration_ms = (time.perf_counter() - started) * 1000
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "%s %s -> %s (%.1fms) [%s]",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
        request_id,
    )
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Never leak an internal error message to a caller."""
    logger.exception("unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal error occurred."},
    )


app.include_router(dashboard.router, prefix="/api")
app.include_router(properties.router, prefix="/api")
app.include_router(analyses.router, prefix="/api")
app.include_router(leads.router, prefix="/api")
app.include_router(settings_router.router, prefix="/api")


@app.get("/")
def root() -> dict:
    return {
        "name": "Atlas API",
        "engine_version": engine_version,
        "docs": "/docs",
    }
