"""
Product OCEAN profile API router.

Endpoints:
  GET  /products/{id}/ocean         — retrieve the product's aggregated OCEAN vector
  POST /products/{id}/ocean/trigger — manually re-generate the product OCEAN profile
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.product import get_product_by_id
from app.database import get_db
from app.dependencies import get_current_company
from app.models.company import Company
from app.schemas.product_ocean import ProductOceanResponse, ProductOceanTriggerResponse
from app.services.product_ocean_service import (
    generate_product_ocean_background,
    get_product_ocean_for_product,
)

router = APIRouter(tags=["Product OCEAN"])


@router.get(
    "/products/{product_id}/ocean",
    response_model=ProductOceanResponse,
    summary="Get the product-level aggregated OCEAN personality profile",
    description=(
        "Returns the single OCEAN vector derived by averaging all motivation/persona "
        "OCEAN profiles for this product. "
        "Available after the pipeline reaches 'product_ocean_ready' status. "
        "This vector is used as a secondary signal in lead matching and as the source "
        "for similar product discovery."
    ),
)
async def get_product_ocean(
    product_id: UUID,
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
) -> ProductOceanResponse:
    product = await get_product_by_id(db, product_id, company.id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")

    profile = await get_product_ocean_for_product(db, product_id)
    if not profile:
        raise HTTPException(
            status_code=404,
            detail=(
                "Product OCEAN profile not yet generated. "
                f"Current pipeline status: {product.status.value}. "
                "Wait for status 'product_ocean_ready' or trigger manually via POST /ocean/trigger."
            ),
        )
    return profile


@router.post(
    "/products/{product_id}/ocean/trigger",
    response_model=ProductOceanTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Manually re-generate the product OCEAN profile",
    description=(
        "Re-runs the product OCEAN aggregation from existing motivation profiles. "
        "Use this after re-running motivation generation or if the automatic trigger failed. "
        "Requires at least one motivation category with an OCEAN profile to exist."
    ),
)
async def trigger_product_ocean(
    product_id: UUID,
    background_tasks: BackgroundTasks,
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
) -> ProductOceanTriggerResponse:
    product = await get_product_by_id(db, product_id, company.id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")

    allowed = {
        "motivations_generated",
        "product_ocean_ready",
        "similar_products_found",
        "failed",
    }
    if product.status.value not in allowed:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Product OCEAN generation requires motivations to be generated first. "
                f"Current status: {product.status.value}."
            ),
        )

    background_tasks.add_task(generate_product_ocean_background, str(product_id))
    return ProductOceanTriggerResponse(
        status="triggered",
        message=(
            f"Product OCEAN aggregation queued for product {product_id}. "
            "Poll GET /products/{id}/status until status is 'product_ocean_ready'."
        ),
    )
