"""
Similar products API router.

Endpoints:
  GET   /products/{id}/similar-products                        — list similar products
  POST  /products/{id}/similar-products/trigger                — re-generate
  PATCH /products/{id}/similar-products/{sp_id}/toggle         — enable/disable one
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.product import get_product_by_id
from app.crud.similar_products import (
    get_similar_products,
    get_similar_product_by_id,
    set_similar_product_active,
)
from app.database import get_db
from app.dependencies import get_current_company
from app.models.company import Company
from app.schemas.similar_products import (
    SimilarProductListResponse,
    SimilarProductResponse,
    SimilarProductToggleRequest,
)
from app.services.product_similarity_service import generate_similar_products_background

router = APIRouter(tags=["Similar Products"])


@router.get(
    "/products/{product_id}/similar-products",
    response_model=SimilarProductListResponse,
    summary="List similar products found for this product",
    description=(
        "Returns all similar products discovered via OCEAN personality alignment. "
        "Each entry includes the product's name, category, OCEAN profile, cosine "
        "similarity score, and the discovery keywords used during the expanded search. "
        "Available after pipeline status reaches 'similar_products_found'. "
        "Use the toggle endpoint to exclude noisy similar products from future discovery runs."
    ),
)
async def list_similar_products(
    product_id: UUID,
    include_inactive: bool = False,
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
) -> SimilarProductListResponse:
    product = await get_product_by_id(db, product_id, company.id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")

    items = await get_similar_products(db, product_id, active_only=not include_inactive)
    return SimilarProductListResponse(
        product_id=product_id,
        count=len(items),
        items=items,
    )


@router.post(
    "/products/{product_id}/similar-products/trigger",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Re-generate similar products for this product",
    description=(
        "Re-runs the similar product discovery pipeline using the existing product OCEAN "
        "profile. Overwrites all current similar products. "
        "Requires status to be 'product_ocean_ready', 'similar_products_found', or 'failed'."
    ),
)
async def trigger_similar_products(
    product_id: UUID,
    background_tasks: BackgroundTasks,
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
) -> dict:
    product = await get_product_by_id(db, product_id, company.id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")

    allowed = {
        "product_ocean_ready",
        "similar_products_found",
        "failed",
    }
    if product.status.value not in allowed:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Similar product discovery requires a product OCEAN profile first. "
                f"Current status: {product.status.value}. "
                "Ensure status is 'product_ocean_ready' before triggering."
            ),
        )

    background_tasks.add_task(generate_similar_products_background, str(product_id))
    return {
        "status": "triggered",
        "product_id": str(product_id),
        "message": (
            "Similar product discovery queued. "
            "Poll GET /products/{id}/status until status is 'similar_products_found'."
        ),
    }


@router.patch(
    "/products/{product_id}/similar-products/{similar_product_id}/toggle",
    response_model=SimilarProductResponse,
    summary="Enable or disable a similar product",
    description=(
        "Toggles the is_active flag on a single similar product without deleting it. "
        "Inactive similar products are excluded from future discovery runs. "
        "Use this to remove noisy or irrelevant similar products that the LLM suggested."
    ),
)
async def toggle_similar_product(
    product_id: UUID,
    similar_product_id: UUID,
    body: SimilarProductToggleRequest,
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
) -> SimilarProductResponse:
    product = await get_product_by_id(db, product_id, company.id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")

    sp = await get_similar_product_by_id(db, similar_product_id)
    if not sp or sp.product_id != product_id:
        raise HTTPException(
            status_code=404,
            detail="Similar product not found for this product.",
        )

    updated = await set_similar_product_active(db, similar_product_id, body.is_active)
    await db.commit()
    return updated
