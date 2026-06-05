"""
CRUD helpers for SimilarProduct.

Used by:
  - product_similarity_service : replace after LLM generation
  - discovery_service          : read active similar products to expand keywords
  - routers/similar_products   : read for GET, toggle for PATCH
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.similar_products import SimilarProduct


async def get_similar_products(
    db: AsyncSession,
    product_id: UUID,
    active_only: bool = True,
) -> list[SimilarProduct]:
    """
    Return similar products for a product, ordered by sort_order (most similar first).
    Pass active_only=False to include products the company has toggled off.
    """
    query = select(SimilarProduct).where(
        SimilarProduct.product_id == product_id
    )
    if active_only:
        query = query.where(SimilarProduct.is_active == True)  # noqa: E712
    query = query.order_by(SimilarProduct.sort_order)
    result = await db.execute(query)
    return list(result.scalars().all())


async def replace_similar_products(
    db: AsyncSession,
    product_id: UUID,
    items: list[dict],
) -> list[SimilarProduct]:
    """
    Delete all existing similar products for this product and insert a fresh set.

    Each dict in items must have:
      similar_product_name, similar_product_category, similar_product_description,
      openness, conscientiousness, extraversion, agreeableness, neuroticism,
      similarity_score, discovery_keywords

    sort_order is assigned automatically (index in the list = rank by similarity).
    """
    await db.execute(
        delete(SimilarProduct).where(SimilarProduct.product_id == product_id)
    )
    await db.flush()

    created: list[SimilarProduct] = []
    for i, item in enumerate(items):
        sp = SimilarProduct(
            product_id=product_id,
            similar_product_name=item["similar_product_name"],
            similar_product_category=item.get("similar_product_category"),
            similar_product_description=item.get("similar_product_description"),
            openness=item.get("openness"),
            conscientiousness=item.get("conscientiousness"),
            extraversion=item.get("extraversion"),
            agreeableness=item.get("agreeableness"),
            neuroticism=item.get("neuroticism"),
            similarity_score=item.get("similarity_score"),
            discovery_keywords=item.get("discovery_keywords", []),
            is_active=True,
            sort_order=i,
        )
        db.add(sp)
        created.append(sp)

    await db.flush()
    return created


async def set_similar_product_active(
    db: AsyncSession,
    similar_product_id: UUID,
    is_active: bool,
) -> SimilarProduct | None:
    """
    Toggle is_active for a single similar product.
    Returns the updated row, or None if the ID doesn't exist.
    """
    await db.execute(
        update(SimilarProduct)
        .where(SimilarProduct.id == similar_product_id)
        .values(is_active=is_active)
    )
    await db.flush()

    result = await db.execute(
        select(SimilarProduct).where(SimilarProduct.id == similar_product_id)
    )
    return result.scalar_one_or_none()


async def get_similar_product_by_id(
    db: AsyncSession,
    similar_product_id: UUID,
) -> SimilarProduct | None:
    """Fetch a single similar product by its primary key."""
    result = await db.execute(
        select(SimilarProduct).where(SimilarProduct.id == similar_product_id)
    )
    return result.scalar_one_or_none()
