import hashlib
import secrets

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.company import Company
from app.schemas.company import CompanyCreate


def _hash_key(raw_key: str) -> str:
    """SHA-256 hex digest of a raw API key. Always 64 hex characters."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


async def create_company(db: AsyncSession, data: CompanyCreate) -> tuple[str, Company]:
    """
    Create a company. Returns (raw_api_key, company).
    The raw key is the only time plaintext is available — store it immediately.
    The DB only ever holds the SHA-256 hash.
    """
    raw_key = secrets.token_hex(32)   # 64-char hex string, 256 bits of entropy
    hashed_key = _hash_key(raw_key)
    company = Company(**data.model_dump(), api_key=hashed_key)
    db.add(company)
    await db.commit()
    await db.refresh(company)
    return raw_key, company


async def get_company_by_email(db: AsyncSession, email: str) -> Company | None:
    result = await db.execute(
        select(Company).where(Company.email == email)
    )
    return result.scalar_one_or_none()


async def get_company_by_api_key(db: AsyncSession, api_key: str) -> Company | None:
    """Hashes the incoming key before comparing — never compares plaintext to DB."""
    hashed = _hash_key(api_key)
    result = await db.execute(
        select(Company).where(
            Company.api_key == hashed,
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
