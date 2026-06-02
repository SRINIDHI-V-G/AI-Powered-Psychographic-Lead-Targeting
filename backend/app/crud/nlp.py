"""CRUD helpers for the NLP layer."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discovery import DiscoveredUser
from app.models.nlp import UserEmbedding, UserNlpFeatures


async def get_nlp_status(db: AsyncSession, product_id: UUID) -> dict:
    """Return NLP processing counts for a product."""
    total_r = await db.execute(
        select(func.count())
        .select_from(DiscoveredUser)
        .where(
            DiscoveredUser.product_id == product_id,
            DiscoveredUser.content_collected == True,  # noqa: E712
        )
    )
    total = total_r.scalar_one()

    done_r = await db.execute(
        select(func.count())
        .select_from(DiscoveredUser)
        .where(
            DiscoveredUser.product_id == product_id,
            DiscoveredUser.nlp_processed == True,  # noqa: E712
        )
    )
    done = done_r.scalar_one()
    pending = total - done

    return {
        "total_users": total,
        "nlp_processed": done,
        "nlp_pending": pending,
        "nlp_failed": 0,  # not separately tracked; failed users stay nlp_processed=True
        "progress_pct": round(done / total * 100, 1) if total > 0 else 0.0,
    }


async def get_user_nlp_features(
    db: AsyncSession,
    user_id: UUID,
) -> UserNlpFeatures | None:
    result = await db.execute(
        select(UserNlpFeatures).where(UserNlpFeatures.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def get_user_embedding(
    db: AsyncSession,
    user_id: UUID,
    embedding_type: str = "combined",
) -> UserEmbedding | None:
    result = await db.execute(
        select(UserEmbedding).where(
            UserEmbedding.user_id == user_id,
            UserEmbedding.embedding_type == embedding_type,
        )
    )
    return result.scalar_one_or_none()
