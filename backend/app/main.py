from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy import text

from app.config import settings, warn_missing_credentials
from app.database import engine
from app.models.base import Base
# Import ALL models so create_all registers every table
from app.models import (  # noqa: F401
    Company, Product, MotivationCategory, MotivationOceanProfile,
    DiscoveryJob, DiscoveredUser, UserContent,
    EnrichmentJob, ProductEnrichmentSignal,
    UserEmbedding, UserNlpFeatures, UserOceanScore, LeadMatch,
)
from app.routers import companies, products, motivations
from app.routers import demo
from app.routers import ollama
from app.routers import discovery
from app.routers import nlp
from app.routers import ocean
from app.routers import matching
from app.routers import validation


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    warn_missing_credentials()
    yield
    await engine.dispose()


app = FastAPI(
    title="Psychographic Lead Intelligence Platform",
    description="AI-powered psychographic lead targeting and ranking.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(companies.router, prefix="/api/v1")
app.include_router(products.router, prefix="/api/v1")
app.include_router(motivations.router, prefix="/api/v1")
app.include_router(demo.router, prefix="/api/v1")
app.include_router(ollama.router, prefix="/api/v1")
app.include_router(discovery.router, prefix="/api/v1")
app.include_router(nlp.router, prefix="/api/v1")
app.include_router(ocean.router, prefix="/api/v1")
app.include_router(validation.router, prefix="/api/v1")
app.include_router(matching.router, prefix="/api/v1")

STATIC_DIR = Path(__file__).parent.parent / "static"


@app.get("/", include_in_schema=False)
async def serve_demo():
    return FileResponse(STATIC_DIR / "demo.html")


@app.get("/demo", include_in_schema=False)
async def serve_demo_alias():
    return FileResponse(STATIC_DIR / "demo.html")


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/health", tags=["Health"])
async def health_check() -> dict:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as exc:
        db_status = f"error: {exc}"

    return {
        "status": "ok" if db_status == "connected" else "degraded",
        "version": "1.0.0",
        "environment": settings.ENVIRONMENT,
        "database": db_status,
    }
