"""FastAPI application entry point — The Architect API."""

import sentry_sdk
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.database import init_pool, close_pool
from app.core.logging import setup_logging
from app.api.routes import router

# Initialize logging
setup_logging()

# Initialize Sentry (production only)
settings = get_settings()
if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        traces_sample_rate=0.1,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle: startup and shutdown."""
    import structlog
    logger = structlog.get_logger()

    # Startup: initialize database pool (non-fatal — healthcheck must work)
    try:
        await init_pool()
        print(f"[STARTUP] Database pool initialized OK")
        logger.info(
            "architect_api_started",
            environment=settings.environment,
            version=settings.app_version,
        )
    except Exception as e:
        import traceback
        err_msg = f"{type(e).__name__}: {e}"
        print(f"[STARTUP] DATABASE POOL FAILED: {err_msg}")
        traceback.print_exc()
        app.state.db_error = err_msg
        # App starts anyway — healthcheck will respond, DB endpoints will fail gracefully
    yield
    # Shutdown: close database pool
    await close_pool()
    logger.info("architect_api_stopped")


# Create app
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="ModellenWerk Workforce Specialist Agent — RAG-powered workforce intelligence API",
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
    lifespan=lifespan,
)

# CORS — allow portal frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",           # Next.js dev
        "https://*.vercel.app",            # Vercel deployments
        "https://modellenwerk.nl",         # Production domain
        "https://www.modellenwerk.nl",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API routes
app.include_router(router)
