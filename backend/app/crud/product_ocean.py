"""
CRUD helpers for ProductOceanProfile.

Used by:
  - product_ocean_service  : upsert after computing the aggregate vector
  - matching_service       : read the vector before computing product_ocean_score
  - routers/product_ocean  : read for the GET endpoint
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product_ocean import ProductOceanProfile


async def get_product_ocean(
    db: AsyncSession,
    product_id: UUID,
) -> ProductOceanProfile | None:
    """Return the product's OCEAN profile, or None if it hasn't been generated yet."""
    result = await db.execute(
        select(ProductOceanProfile).where(
            ProductOceanProfile.product_id == product_id
        )
    )
    return result.scalar_one_or_none()


async def upsert_product_ocean(
    db: AsyncSession,
    product_id: UUID,
    openness: float,
    conscientiousness: float,
    extraversion: float,
    agreeableness: float,
    neuroticism: float,
    confidence: float,
    component_count: int,
    derivation_method: str = "motivation_average",
) -> ProductOceanProfile:
    """
    Delete any existing profile for this product and insert a fresh one.

    We delete-then-insert rather than UPDATE so the updated_at trigger fires
    correctly and the row is always in a clean state after re-generation.
    """
    await db.execute(
        delete(ProductOceanProfile).where(
            ProductOceanProfile.product_id == product_id
        )
    )
    await db.flush()

    profile = ProductOceanProfile(
        product_id=product_id,
        openness=openness,
        conscientiousness=conscientiousness,
        extraversion=extraversion,
        agreeableness=agreeableness,
        neuroticism=neuroticism,
        confidence=confidence,
        component_count=component_count,
        derivation_method=derivation_method,
    )
    db.add(profile)
    await db.flush()
    return profile


async def delete_product_ocean(
    db: AsyncSession,
    product_id: UUID,
) -> None:
    """Remove the product OCEAN profile. Called before regeneration."""
    await db.execute(
        delete(ProductOceanProfile).where(
            ProductOceanProfile.product_id == product_id
        )
    )
    await db.flush()
