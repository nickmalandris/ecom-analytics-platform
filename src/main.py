"""
FastAPI application entry point.

Run with:
    uv run uvicorn src.main:app --reload --port 8000
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from src.api.auth_flow import router as auth_router
from src.api.connections import router as connections_router
from src.api.onboarding import router as onboarding_router
from src.api.reports import router as reports_router
from src.api.sync import router as sync_router
from src.api.users import router as users_router
from src.api.tenants import router as tenants_router
from src.scheduler.scheduler import start_scheduler, stop_scheduler

# ── Logging ──────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


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

app = FastAPI(
    title="Shopify & Meta Ads Analytics",
    description="Multi-tenant analytics platform with LLM-powered weekly reports",
    version="0.1.0",
    lifespan=lifespan,
)

# Mount routers
app.include_router(tenants_router, prefix="/api")
app.include_router(reports_router, prefix="/api")
app.include_router(sync_router, prefix="/api")
app.include_router(auth_router, prefix="/api/auth")
app.include_router(users_router) # /auth and /users endpoints are self-contained
app.include_router(connections_router, prefix="/api")
app.include_router(onboarding_router)

# Mount static files
app.mount("/static", StaticFiles(directory="src/ui/static"), name="static")


@app.get("/health")
def health_check():
    return {"status": "ok"}
