"""FastAPI application entry point — The Architect API."""

import sentry_sdk
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.database import init_pool, close_pool
from app.core.logging import setup_logging
from app.api.routes import router
from app.api.function_routes import router as function_router
from app.api.organization_routes import router as organization_router

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

        # Auto-migrate and seed function impact data
        try:
            from app.pipeline.seed_functions import run_migration, seed_function_data
            await run_migration()
            await seed_function_data()
        except Exception as e:
            logger.warning("function_seed_failed", error=str(e))

        # Auto-migrate and seed organization data
        try:
            from app.pipeline.seed_organizations import seed_organization_data
            await seed_organization_data()
        except Exception as e:
            logger.warning("organization_seed_failed", error=str(e))

        logger.info(
            "architect_api_started",
            environment=settings.environment,
            version=settings.app_version,
        )
    except Exception as e:
        logger.error("database_pool_failed", error=str(e))
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
        "https://aiwatnow.nl",
        "https://www.aiwatnow.nl",
            "https://aiaiaiwat-3vag3exs.manus.space",  # AIAIAI Wat Nu portal (Manus )

    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API routes
app.include_router(router)
app.include_router(function_router)
app.include_router(organization_router)
