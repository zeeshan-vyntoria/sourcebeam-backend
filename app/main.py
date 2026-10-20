from contextlib import asynccontextmanager
import logging
import time
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import DbSession
from app.api.router import api_router
from app.core.config import settings
from app.core.logging import configure_logging
from app.db.session import engine


configure_logging(settings.environment)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Schema changes are deliberately handled by Alembic, never at startup.
    yield
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    description=(
        "A private, citation-first RAG workspace for asking questions about PDFs. "
        "Built with FastAPI, PostgreSQL, pgvector, and Gemini."
    ),
    version="2.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-Request-ID"],
)


@app.middleware("http")
async def security_and_request_logging(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid4()))[:128]
    origin = request.headers.get("Origin")
    if request.method not in {"GET", "HEAD", "OPTIONS"} and origin:
        if origin not in settings.allowed_origins:
            return JSONResponse(status_code=403, content={"detail": "Origin not allowed"})

    started = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    logger.info(
        "request method=%s path=%s status=%s duration_ms=%s request_id=%s",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
        request_id,
    )
    return response


@app.exception_handler(Exception)
async def unhandled_exception(request: Request, exc: Exception):
    request_id = request.headers.get("X-Request-ID", "unavailable")[:128]
    logger.exception("Unhandled request error request_id=%s", request_id, exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "request_id": request_id},
    )


@app.get("/")
async def root():
    return {"message": "Welcome to the Sourcebeam AI API"}


@app.get("/health")
async def health():
    """Backwards-compatible liveness endpoint for existing deployments."""
    return {"status": "ok"}


@app.get("/health/live", tags=["health"])
async def liveness():
    """Report whether the API process can serve requests."""
    return {"status": "ok", "service": settings.app_name, "version": app.version}


@app.get("/health/ready", tags=["health"])
async def readiness(db: DbSession):
    """Report whether required infrastructure is available."""
    try:
        await db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        logger.warning("Database readiness check failed", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        ) from exc
    return {"status": "ready", "database": "available"}


app.include_router(api_router)
