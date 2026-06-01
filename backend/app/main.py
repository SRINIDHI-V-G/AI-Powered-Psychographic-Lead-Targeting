from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import settings
from app.database import engine
from app.models.base import Base
from app.models import Company, Product, MotivationCategory, MotivationOceanProfile  # noqa: F401
from app.routers import companies, products, motivations


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
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
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(companies.router, prefix="/api/v1")
app.include_router(products.router, prefix="/api/v1")
app.include_router(motivations.router, prefix="/api/v1")


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
