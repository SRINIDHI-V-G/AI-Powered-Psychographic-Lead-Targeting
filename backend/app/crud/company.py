from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.company import Company
from app.schemas.company import CompanyCreate


async def create_company(db: AsyncSession, data: CompanyCreate) -> Company:
    company = Company(**data.model_dump())
    db.add(company)
    await db.commit()
    await db.refresh(company)
    return company


async def get_company_by_email(db: AsyncSession, email: str) -> Company | None:
    result = await db.execute(
        select(Company).where(Company.email == email)
    )
    return result.scalar_one_or_none()


async def get_company_by_api_key(db: AsyncSession, api_key: str) -> Company | None:
    result = await db.execute(
        select(Company).where(
            Company.api_key == api_key,
            Company.is_active == True,  # noqa: E712
        )
    )
    return result.scalar_one_or_none()


async def get_all_companies(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 20,
) -> list[Company]:
    result = await db.execute(
        select(Company)
        .where(Company.is_active == True)  # noqa: E712
        .order_by(Company.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all())
