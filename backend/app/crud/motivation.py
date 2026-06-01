from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from uuid import UUID
from app.models.motivation import MotivationCategory, MotivationOceanProfile


async def create_motivation_category(
    db: AsyncSession,
    product_id: UUID,
    name: str,
    description: str,
    sort_order: int,
) -> MotivationCategory:
    mc = MotivationCategory(
        product_id=product_id,
        name=name,
        description=description,
        sort_order=sort_order,
    )
    db.add(mc)
    await db.flush()  # assigns mc.id without committing the transaction
    return mc


async def create_ocean_profile(
    db: AsyncSession,
    motivation_category_id: UUID,
    ocean_data: dict,
) -> MotivationOceanProfile:
    profile = MotivationOceanProfile(
        motivation_category_id=motivation_category_id,
        openness=ocean_data["openness"],
        conscientiousness=ocean_data["conscientiousness"],
        extraversion=ocean_data["extraversion"],
        agreeableness=ocean_data["agreeableness"],
        emotional_stability=ocean_data["emotional_stability"],
        interest_tags=ocean_data.get("interest_tags", []),
        search_keywords=ocean_data.get("search_keywords", []),
        hashtags=ocean_data.get("hashtags", []),
    )
    db.add(profile)
    return profile


async def get_motivations_by_product(
    db: AsyncSession,
    product_id: UUID,
) -> list[MotivationCategory]:
    result = await db.execute(
        select(MotivationCategory)
        .where(
            MotivationCategory.product_id == product_id,
            MotivationCategory.is_active == True,  # noqa: E712
        )
        .options(selectinload(MotivationCategory.ocean_profile))
        .order_by(MotivationCategory.sort_order)
    )
    return list(result.scalars().all())


async def delete_motivations_by_product(
    db: AsyncSession,
    product_id: UUID,
) -> None:
    result = await db.execute(
        select(MotivationCategory).where(
            MotivationCategory.product_id == product_id
        )
    )
    for mc in result.scalars().all():
        await db.delete(mc)
    await db.flush()
