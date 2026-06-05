"""
CRUD helpers for LeadHandle.

Used by:
  handle_service : bulk insert after discovery pipeline completes
  validation router: read handles for a lead inspection
  export: include handles in CSV/JSON exports
"""
from __future__ import annotations

import uuid
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lead_handle import LeadHandle


async def create_handle(
    db: AsyncSession,
    discovered_user_id: UUID,
    platform: str,
    handle: str,
    handle_score: float,
    confidence: float,
    tier: str,
    evidence_json: dict,
    verification_json: dict | None = None,
) -> LeadHandle:
    """Insert a single LeadHandle row and return it (not yet committed)."""
    row = LeadHandle(
        id=uuid.uuid4(),
        discovered_user_id=discovered_user_id,
        platform=platform,
        handle=handle,
        handle_score=handle_score,
        confidence=confidence,
        tier=tier,
        evidence_json=evidence_json,
        verification_json=verification_json or {},
    )
    db.add(row)
    await db.flush()
    return row


async def bulk_create_handles(
    db: AsyncSession,
    handles: list[LeadHandle],
) -> list[LeadHandle]:
    """
    Persist a batch of pre-built LeadHandle objects.
    Caller is responsible for setting all fields before passing in.
    Flushes but does NOT commit.
    """
    for h in handles:
        db.add(h)
    await db.flush()
    return handles


async def get_user_handles(
    db: AsyncSession,
    user_id: UUID,
    platform: str | None = None,
) -> list[LeadHandle]:
    """
    Return all handles for a discovered user, ordered by handle_score DESC.
    Optionally filter to a single platform.
    """
    stmt = (
        select(LeadHandle)
        .where(LeadHandle.discovered_user_id == user_id)
        .order_by(LeadHandle.handle_score.desc())
    )
    if platform is not None:
        stmt = stmt.where(LeadHandle.platform == platform)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_top_handles(
    db: AsyncSession,
    user_id: UUID,
    limit: int = 5,
) -> list[LeadHandle]:
    """Return the top-N handles across all platforms for a user."""
    result = await db.execute(
        select(LeadHandle)
        .where(LeadHandle.discovered_user_id == user_id)
        .order_by(LeadHandle.handle_score.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def delete_user_handles(
    db: AsyncSession,
    user_id: UUID,
) -> int:
    """
    Delete all handle rows for a user.
    Returns the number of rows deleted.
    Used before re-running handle discovery to avoid duplicates.
    """
    result = await db.execute(
        delete(LeadHandle)
        .where(LeadHandle.discovered_user_id == user_id)
        .returning(LeadHandle.id)
    )
    deleted = len(result.fetchall())
    await db.flush()
    return deleted
