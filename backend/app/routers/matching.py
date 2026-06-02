"""
Matching and Lead Ranking API router.

Endpoints:
  POST /products/{id}/match/trigger          — start matching (background)
  GET  /products/{id}/match/status           — matching progress poll
  GET  /products/{id}/leads                  — paginated ranked lead list
  GET  /products/{id}/leads/{user_id}        — single lead detail
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.matching import get_match_status, get_ranked_leads, get_lead_detail
from app.crud.product import get_product_by_id
from app.database import get_db
from app.dependencies import get_current_company
from app.models.company import Company
from app.schemas.matching import (
    MatchStatusResponse,
    LeadListResponse,
    LeadDetailResponse,
)
from app.services.matching_service import start_matching_background

router = APIRouter(tags=["Matching & Lead Ranking"])

# Product statuses that permit triggering matching
_ALLOWED_STATUSES = {
    "ocean_scoring", "matching", "ranked", "completed",
}


@router.post(
    "/products/{product_id}/match/trigger",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger psychographic matching and lead ranking for a product",
)
async def trigger_matching(
    product_id: UUID,
    background_tasks: BackgroundTasks,
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
) -> dict:
    product = await get_product_by_id(db, product_id, company.id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")
    if product.status.value not in _ALLOWED_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Matching requires OCEAN scoring to be complete. "
                f"Current status: {product.status.value}."
            ),
        )
    background_tasks.add_task(start_matching_background, str(product_id))
    return {"status": "queued", "product_id": str(product_id)}


@router.get(
    "/products/{product_id}/match/status",
    response_model=MatchStatusResponse,
    summary="Matching progress for a product",
)
async def match_status(
    product_id: UUID,
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
) -> MatchStatusResponse:
    product = await get_product_by_id(db, product_id, company.id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")
    counts = await get_match_status(db, product_id)
    return MatchStatusResponse(product_id=product_id, **counts)


@router.get(
    "/products/{product_id}/leads",
    response_model=LeadListResponse,
    summary="Ranked lead list for a product",
    description=(
        "Returns users ranked by their psychographic match score. "
        "Each user appears once with their best-matching motivation category. "
        "Use page/page_size for pagination, min_score to filter by quality."
    ),
)
async def list_leads(
    product_id: UUID,
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(20, ge=1, le=100, description="Results per page"),
    min_score: float = Query(0.0, ge=0.0, le=100.0, description="Minimum final score"),
    min_confidence: float = Query(
        0.0, ge=0.0, le=100.0,
        description="Minimum match confidence (set to 40 to exclude low-content users)",
    ),
    sort: str = Query(
        "top", pattern="^(top|bottom)$",
        description="Sort direction: 'top' for best leads first, 'bottom' for worst leads first",
    ),
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
) -> LeadListResponse:
    product = await get_product_by_id(db, product_id, company.id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")
    result = await get_ranked_leads(
        db, product_id,
        page=page, page_size=page_size,
        min_score=min_score, min_confidence=min_confidence, sort=sort,
    )
    return LeadListResponse(**result)


@router.get(
    "/products/{product_id}/leads/{user_id}",
    response_model=LeadDetailResponse,
    summary="Full psychographic profile and match breakdown for one lead",
    description=(
        "Returns all motivation category scores for the user, "
        "plus their best match and rank."
    ),
)
async def get_lead(
    product_id: UUID,
    user_id: UUID,
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
) -> LeadDetailResponse:
    product = await get_product_by_id(db, product_id, company.id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")
    detail = await get_lead_detail(db, product_id, user_id)
    if not detail:
        raise HTTPException(
            status_code=404,
            detail="Lead not found or matching not yet computed for this user.",
        )
    return LeadDetailResponse(**detail)
