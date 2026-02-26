"""
FastAPI application entry point.

Run with:
    uv run uvicorn src.main:app --reload --port 8000
"""

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

import sentry_sdk
import structlog

from src.api.analytics import router as analytics_router
from src.api.auth_flow import router as auth_router
from src.api.chat import router as chat_router
from src.api.connections import router as connections_router
from src.api.onboarding import router as onboarding_router
from src.api.reports import router as reports_router
from src.api.sync import router as sync_router
from src.api.users import router as users_router, OAuthCallbackRedirectMiddleware
from src.api.tenants import router as tenants_router
from src.scheduler.scheduler import start_scheduler, stop_scheduler
from src.config import settings
from src.db import engine

# ── Sentry ───────────────────────────────────────

if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        traces_sample_rate=1.0,
    )

# ── Logging ──────────────────────────────────────

import logging.config

# Clear existing loggers
logging.getLogger().handlers.clear()

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.dict_tracebacks,
        structlog.processors.JSONRenderer() if settings.environment == "production" else structlog.dev.ConsoleRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)

# Route standard logging to structlog
class StructlogHandler(logging.Handler):
    def emit(self, record):
        logger_for_record = structlog.get_logger(record.name)
        if record.exc_info:
            logger_for_record.exception(record.getMessage(), exc_info=record.exc_info)
        else:
            # We map standard python log levels to structlog methods
            # Only intercept log levels INFO and above to prevent overly noisy logs
            if record.levelno >= logging.INFO:
                method = getattr(logger_for_record, record.levelname.lower(), logger_for_record.info)
                method(record.getMessage())

root_logger = logging.getLogger()
# Clear existing handlers again to be safe
root_logger.handlers.clear()
root_logger.addHandler(StructlogHandler())
root_logger.setLevel(logging.INFO)

# Suppress noisy library loggers that cause loops or spam
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# ── Lifespan ─────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle for the FastAPI app."""
    logger.info("Starting up...")
    start_scheduler()
    yield
    logger.info("Shutting down...")
    stop_scheduler()


# ── App ──────────────────────────────────────────

limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])

app = FastAPI(
    title="Shopify & Meta Ads Analytics",
    description="Multi-tenant analytics platform with LLM-powered weekly reports",
    version="0.1.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore
app.add_middleware(SlowAPIMiddleware)

from src.config import settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# OAuth callback redirect middleware (must be added before routers)
app.add_middleware(OAuthCallbackRedirectMiddleware)

# Mount routers
app.include_router(tenants_router, prefix="/api")
app.include_router(reports_router, prefix="/api")
app.include_router(sync_router, prefix="/api")
app.include_router(analytics_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(auth_router, prefix="/api/auth")
app.include_router(users_router) # /auth and /users endpoints are self-contained
app.include_router(connections_router, prefix="/api")
app.include_router(onboarding_router)

# Mount static files
app.mount("/static", StaticFiles(directory="src/ui/static"), name="static")


@app.get("/health")
def health_check():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        db_status = "error"
        raise HTTPException(status_code=503, detail="Database connection failed")
        
    return {"status": "ok", "database": db_status}
