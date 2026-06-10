import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy import text

from app.config import settings, warn_missing_credentials
from app.database import engine
from app.middleware.rate_limit import RateLimitMiddleware

# Model imports are kept so that references elsewhere in the codebase resolve
# correctly at runtime. They do NOT drive schema creation — Alembic migrations
# are the sole source of truth for the database schema.
# Before starting the server, run: alembic upgrade head
from app.models import (  # noqa: F401
    Company, Product, MotivationCategory, MotivationOceanProfile,
    ProductOceanProfile, SimilarProduct,
    DiscoveryJob, DiscoveredUser, UserContent,
    EnrichmentJob, ProductEnrichmentSignal,
    UserEmbedding, UserNlpFeatures, UserOceanScore, LeadMatch, LeadHandle,
)
from app.routers import companies, products, motivations
from app.routers import dashboard
from app.routers import demo
from app.routers import ollama
from app.routers import discovery
from app.routers import nlp
from app.routers import ocean
from app.routers import matching
from app.routers import validation
from app.routers import product_ocean
from app.routers import similar_products

logger = logging.getLogger(__name__)

_EXPECTED_REVISION = "b2c3d4e5f6a7"


async def _discovery_watchdog() -> None:
    """
    Periodic background task: detects and recovers stale discovery jobs.

    Wakes every DISCOVERY_STALE_JOB_TIMEOUT_MINUTES / 2 minutes and calls
    recover_stale_jobs(). This covers jobs that become stale AFTER startup
    (e.g. a job that starts, then the process hangs without a full restart).
    """
    from app.services.discovery_service import recover_stale_jobs
    interval = max(60, settings.DISCOVERY_STALE_JOB_TIMEOUT_MINUTES * 30)  # half-timeout in seconds
    while True:
        await asyncio.sleep(interval)
        try:
            await recover_stale_jobs()
        except Exception as exc:
            logger.warning("[watchdog] stale-job sweep failed: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Verify the database is reachable and migrations are at head.
    # Schema creation is handled exclusively by `alembic upgrade head`.
    # Never call Base.metadata.create_all() here — it silently skips
    # ALTER TABLE operations from migrations and leaves columns missing.
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT version_num FROM alembic_version LIMIT 1")
            )
            row = result.fetchone()
            if row is None:
                logger.error(
                    "alembic_version table is empty. "
                    "Run `alembic upgrade head` before starting the server."
                )
            elif row[0] != _EXPECTED_REVISION:
                logger.warning(
                    "Database is at Alembic revision %s; expected %s. "
                    "Run `alembic upgrade head` to apply pending migrations.",
                    row[0],
                    _EXPECTED_REVISION,
                )
            else:
                logger.info("Database schema verified at revision %s.", row[0])
    except Exception as exc:
        logger.error(
            "Database connectivity check failed: %s. "
            "Ensure PostgreSQL is running and DATABASE_URL is correct.",
            exc,
        )

    warn_missing_credentials()

    # ── Orphan recovery: mark stale jobs failed and re-queue them ─────────────
    try:
        from app.services.discovery_service import recover_stale_jobs
        await recover_stale_jobs()
    except Exception as exc:
        logger.warning("Startup stale-job recovery failed (non-fatal): %s", exc)

    # ── Periodic watchdog: catches jobs that go stale after startup ───────────
    watchdog_task = asyncio.create_task(_discovery_watchdog())

    yield

    watchdog_task.cancel()
    try:
        await watchdog_task
    except asyncio.CancelledError:
        pass
    await engine.dispose()


app = FastAPI(
    title="Psychographic Lead Intelligence Platform",
    description="AI-powered psychographic lead targeting and ranking.",
    version="1.0.0",
    lifespan=lifespan,
    # Disable automatic trailing-slash redirects.
    # With redirect_slashes=True (default), a request to /api/v1/products would
    # get a 307 redirect to http://localhost:8000/api/v1/products/ — an absolute
    # backend URL. Axios follows that redirect directly to the backend, bypassing
    # the Next.js middleware that injects X-API-Key, resulting in a 401 that logs
    # the user out. Setting False makes both /products and /products/ work directly.
    redirect_slashes=False,
)

# ── Middleware (order matters: outermost = first to receive request) ───────────

app.add_middleware(RateLimitMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ────────────────────────────────────────────────────────────────────

app.include_router(companies.router, prefix="/api/v1")
app.include_router(products.router, prefix="/api/v1")
app.include_router(motivations.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")
app.include_router(ollama.router, prefix="/api/v1")
app.include_router(discovery.router, prefix="/api/v1")
app.include_router(nlp.router, prefix="/api/v1")
app.include_router(ocean.router, prefix="/api/v1")
app.include_router(validation.router, prefix="/api/v1")
app.include_router(matching.router, prefix="/api/v1")
app.include_router(product_ocean.router, prefix="/api/v1")
app.include_router(similar_products.router, prefix="/api/v1")

# Demo router is only registered when explicitly enabled.
# It must NEVER be registered in production (enforced by warn_missing_credentials).
if settings.ENABLE_DEMO:
    app.include_router(demo.router, prefix="/api/v1")
    logger.warning("Demo router is ACTIVE. Disable in production: ENABLE_DEMO=false")

# ── Static files ───────────────────────────────────────────────────────────────

STATIC_DIR = Path(__file__).parent.parent / "static"


@app.get("/", include_in_schema=False)
async def serve_demo():
    return FileResponse(STATIC_DIR / "demo.html")


@app.get("/demo", include_in_schema=False)
async def serve_demo_alias():
    return FileResponse(STATIC_DIR / "demo.html")


@app.get("/dashboard", include_in_schema=False)
async def serve_dashboard():
    return FileResponse(STATIC_DIR / "dashboard.html")


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ── Health check ───────────────────────────────────────────────────────────────

@app.get("/health", tags=["Health"])
async def health_check() -> dict:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as exc:
        db_status = f"error: {exc}"

    redis_status = "not_configured"
    if settings.REDIS_URL:
        try:
            import redis.asyncio as aioredis
            r = aioredis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
            await r.ping()
            await r.aclose()
            redis_status = "connected"
        except Exception as exc:
            redis_status = f"error: {exc}"

    all_ok = db_status == "connected" and redis_status in ("connected", "not_configured")

    return {
        "status": "ok" if all_ok else "degraded",
        "version": "1.0.0",
        "environment": settings.ENVIRONMENT,
        "database": db_status,
        "redis": redis_status,
    }
