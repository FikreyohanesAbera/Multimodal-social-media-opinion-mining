# app/main.py
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.db.pool import close_pool, fetchrow, init_pool
from app.models.schemas import HealthResponse
from app.routes.social_accounts import router as social_router

logging.basicConfig(
    level=logging.DEBUG if not settings.is_production else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ── Lifespan (startup / shutdown) ─────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("🚀 Starting up — initialising database pool...")
    await init_pool()
    logger.info("✓ Database pool ready")
    yield
    logger.info("Shutting down — closing database pool...")
    await close_pool()
    logger.info("✓ Database pool closed")


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="YouTube OAuth2 Social Account Service",
    description="Verify YouTube account ownership via Google OAuth2 and gather sentiment.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── Middleware ────────────────────────────────────────────────────────────────
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret_key,
    session_cookie="session",
    max_age=7 * 24 * 60 * 60,   # 7 days
    https_only=settings.is_production,
    same_site="lax",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

# ── Routes ────────────────────────────────────────────────────────────────────
app.include_router(social_router)


@app.get("/health", response_model=HealthResponse, tags=["Meta"])
async def health_check() -> HealthResponse:
    try:
        await fetchrow("SELECT 1")
        db_status = "connected"
    except Exception:
        db_status = "disconnected"

    return HealthResponse(
        status="ok" if db_status == "connected" else "degraded",
        db=db_status,
        timestamp=datetime.now(tz=timezone.utc),
    )
