"""CRUD operations for the discovery layer."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discovery import DiscoveredUser, DiscoveryJob, UserContent


# ── Discovery Jobs ────────────────────────────────────────────────────────────

async def create_discovery_job(
    db: AsyncSession,
    product_id: UUID,
    max_users: int,
    search_config: dict,
) -> DiscoveryJob:
    job = DiscoveryJob(
        product_id=product_id,
        provider_name="pending",
        sources=[],
        max_users=max_users,
        search_config=search_config,
        status="queued",
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


async def get_discovery_jobs_for_product(
    db: AsyncSession,
    product_id: UUID,
) -> list[DiscoveryJob]:
    result = await db.execute(
        select(DiscoveryJob)
        .where(DiscoveryJob.product_id == product_id)
        .order_by(DiscoveryJob.created_at.desc())
    )
    return list(result.scalars().all())


async def get_discovery_job(
    db: AsyncSession,
    job_id: UUID,
    product_id: UUID,
) -> DiscoveryJob | None:
    result = await db.execute(
        select(DiscoveryJob).where(
            DiscoveryJob.id == job_id,
            DiscoveryJob.product_id == product_id,
        )
    )
    return result.scalar_one_or_none()


# ── Discovered Users ──────────────────────────────────────────────────────────

async def get_discovered_user(
    db: AsyncSession,
    user_id: UUID,
    product_id: UUID,
) -> DiscoveredUser | None:
    """Return a single discovered user, or None if it does not exist or belongs to a different product."""
    result = await db.execute(
        select(DiscoveredUser).where(
            DiscoveredUser.id == user_id,
            DiscoveredUser.product_id == product_id,
        )
    )
    return result.scalar_one_or_none()


async def get_discovered_users(
    db: AsyncSession,
    product_id: UUID,
    job_id: UUID | None = None,
    page: int = 1,
    limit: int = 50,
) -> list[DiscoveredUser]:
    stmt = select(DiscoveredUser).where(
        DiscoveredUser.product_id == product_id
    )
    if job_id:
        stmt = stmt.where(DiscoveredUser.discovery_job_id == job_id)
    stmt = stmt.order_by(DiscoveredUser.follower_count.desc())
    stmt = stmt.offset((page - 1) * limit).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def count_discovered_users(
    db: AsyncSession,
    product_id: UUID,
    job_id: UUID | None = None,
) -> int:
    stmt = select(func.count()).select_from(DiscoveredUser).where(
        DiscoveredUser.product_id == product_id
    )
    if job_id:
        stmt = stmt.where(DiscoveredUser.discovery_job_id == job_id)
    result = await db.execute(stmt)
    return result.scalar_one()


async def get_user_content(
    db: AsyncSession,
    user_id: UUID,
    limit: int = 25,
) -> list[UserContent]:
    result = await db.execute(
        select(UserContent)
        .where(UserContent.user_id == user_id)
        .order_by(UserContent.engagement.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
