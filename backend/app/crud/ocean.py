"""CRUD helpers for the OCEAN scoring layer."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discovery import DiscoveredUser
from app.models.ocean import UserOceanScore


async def get_ocean_status(db: AsyncSession, product_id: UUID) -> dict:
    """Return OCEAN scoring progress counts for a product."""
    total_r = await db.execute(
        select(func.count())
        .select_from(DiscoveredUser)
        .where(
            DiscoveredUser.product_id == product_id,
            DiscoveredUser.nlp_processed == True,  # noqa: E712
        )
    )
    total = total_r.scalar_one()

    done_r = await db.execute(
        select(func.count())
        .select_from(DiscoveredUser)
        .where(
            DiscoveredUser.product_id == product_id,
            DiscoveredUser.ocean_scored == True,  # noqa: E712
        )
    )
    done = done_r.scalar_one()
    pending = total - done

    return {
        "total_users": total,
        "ocean_scored": done,
        "ocean_pending": pending,
        "progress_pct": round(done / total * 100, 1) if total > 0 else 0.0,
    }


async def get_user_ocean_score(
    db: AsyncSession,
    user_id: UUID,
) -> UserOceanScore | None:
    result = await db.execute(
        select(UserOceanScore).where(UserOceanScore.user_id == user_id)
    )
    return result.scalar_one_or_none()
