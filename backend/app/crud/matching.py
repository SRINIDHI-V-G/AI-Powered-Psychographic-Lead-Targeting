"""CRUD helpers for the matching / lead ranking layer."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discovery import DiscoveredUser
from app.models.matching import LeadMatch
from app.models.motivation import MotivationCategory


async def get_match_status(db: AsyncSession, product_id: UUID) -> dict:
    """Return matching progress counts for a product."""
    total_r = await db.execute(
        select(func.count())
        .select_from(DiscoveredUser)
        .where(
            DiscoveredUser.product_id == product_id,
            DiscoveredUser.ocean_scored == True,  # noqa: E712
        )
    )
    total = total_r.scalar_one()

    matched_r = await db.execute(
        select(func.count())
        .select_from(DiscoveredUser)
        .where(
            DiscoveredUser.product_id == product_id,
            DiscoveredUser.matched == True,  # noqa: E712
        )
    )
    matched = matched_r.scalar_one()

    ranked_r = await db.execute(
        select(func.count())
        .select_from(LeadMatch)
        .where(
            LeadMatch.product_id == product_id,
            LeadMatch.is_best_match == True,  # noqa: E712
        )
    )
    ranked = ranked_r.scalar_one()

    return {
        "total_users": total,
        "matched": matched,
        "ranked": ranked,
        "pending": total - matched,
        "progress_pct": round(matched / total * 100, 1) if total > 0 else 0.0,
    }


async def get_ranked_leads(
    db: AsyncSession,
    product_id: UUID,
    page: int = 1,
    page_size: int = 20,
    min_score: float = 0.0,
    min_confidence: float = 0.0,
    sort: str = "top",
) -> dict:
    """
    Return paginated ranked lead list for a product.
    Only includes best-match rows (is_best_match=True).

    sort="top"    — ordered by rank ascending (best leads first)
    sort="bottom" — ordered by rank descending (worst leads first, useful for validation)
    """
    page = max(1, page)
    page_size = max(1, min(100, page_size))
    offset = (page - 1) * page_size

    filters = [
        LeadMatch.product_id == product_id,
        LeadMatch.is_best_match == True,  # noqa: E712
        LeadMatch.final_score >= min_score,
        LeadMatch.confidence >= min_confidence,
    ]

    # Count total ranked leads meeting filters
    count_r = await db.execute(
        select(func.count())
        .select_from(LeadMatch)
        .where(*filters)
    )
    total = count_r.scalar_one()

    order_clause = (
        LeadMatch.rank.asc().nullslast()
        if sort == "top"
        else LeadMatch.rank.desc().nullsfirst()
    )

    # Fetch page of leads with user + motivation info
    result = await db.execute(
        select(LeadMatch, DiscoveredUser, MotivationCategory)
        .join(DiscoveredUser, LeadMatch.user_id == DiscoveredUser.id)
        .join(MotivationCategory, LeadMatch.motivation_category_id == MotivationCategory.id)
        .where(*filters)
        .order_by(order_clause)
        .offset(offset)
        .limit(page_size)
    )
    rows = result.all()

    leads = []
    for lead_match, user, category in rows:
        leads.append({
            "rank": lead_match.rank,
            "user_id": str(user.id),
            "username": user.username,
            "display_name": user.display_name,
            "platform": user.platform,
            "profile_url": user.profile_url,
            "location": user.location,
            "follower_count": user.follower_count,
            "best_motivation_category": category.name,
            "motivation_category_id": str(category.id),
            "final_score": lead_match.final_score,
            "ocean_score": lead_match.ocean_score,
            "embedding_score": lead_match.embedding_score,
            "interest_score": lead_match.interest_score,
            "confidence": lead_match.confidence,
            "reasoning": lead_match.reasoning,
        })

    return {
        "total_leads": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size),
        "leads": leads,
    }


async def get_lead_detail(
    db: AsyncSession,
    product_id: UUID,
    user_id: UUID,
) -> dict | None:
    """
    Return full lead detail for one user: best match + all category scores.
    Returns None if this user has no matches for this product.
    """
    user_r = await db.execute(
        select(DiscoveredUser).where(DiscoveredUser.id == user_id)
    )
    user: DiscoveredUser | None = user_r.scalar_one_or_none()
    if not user:
        return None

    # All matches for this user under this product
    all_r = await db.execute(
        select(LeadMatch, MotivationCategory)
        .join(MotivationCategory, LeadMatch.motivation_category_id == MotivationCategory.id)
        .where(
            LeadMatch.product_id == product_id,
            LeadMatch.user_id == user_id,
        )
        .order_by(LeadMatch.final_score.desc())
    )
    all_rows = all_r.all()

    if not all_rows:
        return None

    best_match_row = None
    all_category_scores = []
    for match, category in all_rows:
        entry = {
            "motivation_category_id": str(category.id),
            "motivation_category": category.name,
            "final_score": match.final_score,
            "ocean_score": match.ocean_score,
            "embedding_score": match.embedding_score,
            "interest_score": match.interest_score,
            "confidence": match.confidence,
            "reasoning": match.reasoning,
        }
        all_category_scores.append(entry)
        if match.is_best_match:
            best_match_row = {"rank": match.rank, **entry}

    return {
        "user_id": str(user.id),
        "username": user.username,
        "display_name": user.display_name,
        "platform": user.platform,
        "profile_url": user.profile_url,
        "location": user.location,
        "location_confidence": user.location_confidence,
        "follower_count": user.follower_count,
        "best_match": best_match_row,
        "all_category_scores": all_category_scores,
    }
