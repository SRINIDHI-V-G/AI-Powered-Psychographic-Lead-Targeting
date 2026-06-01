from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from app.models.product import Product
from app.schemas.product import ProductCreate


async def create_product(
    db: AsyncSession,
    data: ProductCreate,
    company_id: UUID,
) -> Product:
    product = Product(**data.model_dump(), company_id=company_id)
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product


async def get_products_by_company(
    db: AsyncSession,
    company_id: UUID,
) -> list[Product]:
    result = await db.execute(
        select(Product)
        .where(Product.company_id == company_id)
        .order_by(Product.created_at.desc())
    )
    return list(result.scalars().all())


async def get_product_by_id(
    db: AsyncSession,
    product_id: UUID,
    company_id: UUID,
) -> Product | None:
    result = await db.execute(
        select(Product).where(
            Product.id == product_id,
            Product.company_id == company_id,
        )
    )
    return result.scalar_one_or_none()
