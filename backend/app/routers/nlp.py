"""
NLP pipeline API router.

Endpoints:
  GET  /products/{id}/nlp/status     — progress poll
  POST /products/{id}/nlp/trigger    — manually start NLP for a product
  GET  /products/{id}/discovery/users/{uid}/nlp — NLP features for one user
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.nlp import get_nlp_status, get_user_nlp_features, get_user_embedding
from app.crud.product import get_product_by_id
from app.database import get_db
from app.dependencies import get_current_company
from app.models.company import Company
from app.schemas.nlp import NlpStatusResponse, UserNlpFeaturesResponse, UserEmbeddingResponse
from app.services.nlp_service import start_nlp_background

router = APIRouter(tags=["NLP Pipeline"])


@router.get(
    "/products/{product_id}/nlp/status",
    response_model=NlpStatusResponse,
    summary="NLP pipeline progress for a product",
    description="Poll this every 10 seconds while NLP is running.",
)
async def nlp_status(
    product_id: UUID,
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
) -> NlpStatusResponse:
    product = await get_product_by_id(db, product_id, company.id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")
    counts = await get_nlp_status(db, product_id)
    return NlpStatusResponse(product_id=product_id, **counts)


@router.post(
    "/products/{product_id}/nlp/trigger",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Manually trigger NLP processing for a product",
    description=(
        "Fires the NLP background task for all users with collected content "
        "that have not yet been NLP-processed. "
        "Normally triggered automatically by the discovery orchestrator."
    ),
)
async def trigger_nlp(
    product_id: UUID,
    background_tasks: BackgroundTasks,
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
) -> dict:
    product = await get_product_by_id(db, product_id, company.id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")

    allowed = {
        "motivations_generated", "discovering", "nlp_processing",
        "ocean_scoring", "matching", "ranked", "completed",
    }
    if product.status.value not in allowed:
        raise HTTPException(
            status_code=422,
            detail=(
                f"NLP requires discovery to be complete first. "
                f"Current status: {product.status.value}."
            ),
        )

    background_tasks.add_task(start_nlp_background, str(product_id))
    return {"status": "queued", "product_id": str(product_id)}


@router.get(
    "/products/{product_id}/discovery/users/{user_id}/nlp",
    response_model=UserNlpFeaturesResponse,
    summary="Get NLP features for a specific discovered user",
)
async def get_user_nlp(
    product_id: UUID,
    user_id: UUID,
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
) -> UserNlpFeaturesResponse:
    product = await get_product_by_id(db, product_id, company.id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")
    features = await get_user_nlp_features(db, user_id)
    if not features:
        raise HTTPException(
            status_code=404,
            detail="NLP features not yet computed for this user.",
        )
    return features
