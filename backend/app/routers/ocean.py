"""
OCEAN scoring API router.

Endpoints:
  GET  /products/{id}/ocean/status              — progress poll
  POST /products/{id}/ocean/trigger             — manually start OCEAN scoring
  GET  /products/{id}/discovery/users/{uid}/ocean — OCEAN scores for one user
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.ocean import get_ocean_status, get_user_ocean_score
from app.crud.product import get_product_by_id
from app.database import get_db
from app.dependencies import get_current_company
from app.models.company import Company
from app.schemas.ocean import OceanStatusResponse, UserOceanScoreResponse
from app.services.ocean_service import start_ocean_background

router = APIRouter(tags=["OCEAN Scoring"])


@router.get(
    "/products/{product_id}/ocean/status",
    response_model=OceanStatusResponse,
    summary="OCEAN scoring progress for a product",
)
async def ocean_status(
    product_id: UUID,
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
) -> OceanStatusResponse:
    product = await get_product_by_id(db, product_id, company.id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")
    counts = await get_ocean_status(db, product_id)
    return OceanStatusResponse(product_id=product_id, **counts)


@router.post(
    "/products/{product_id}/ocean/trigger",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Manually trigger OCEAN scoring for a product",
)
async def trigger_ocean(
    product_id: UUID,
    background_tasks: BackgroundTasks,
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
) -> dict:
    product = await get_product_by_id(db, product_id, company.id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")

    allowed = {
        "nlp_processing", "ocean_scoring", "matching", "ranked", "completed",
    }
    if product.status.value not in allowed:
        raise HTTPException(
            status_code=422,
            detail=(
                f"OCEAN scoring requires NLP processing to be complete first. "
                f"Current status: {product.status.value}."
            ),
        )

    background_tasks.add_task(start_ocean_background, str(product_id))
    return {"status": "queued", "product_id": str(product_id)}


@router.get(
    "/products/{product_id}/discovery/users/{user_id}/ocean",
    response_model=UserOceanScoreResponse,
    summary="Get OCEAN personality scores for a discovered user",
)
async def get_user_ocean(
    product_id: UUID,
    user_id: UUID,
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
) -> UserOceanScoreResponse:
    product = await get_product_by_id(db, product_id, company.id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")
    score = await get_user_ocean_score(db, user_id)
    if not score:
        raise HTTPException(
            status_code=404,
            detail="OCEAN scores not yet computed for this user.",
        )
    return score
