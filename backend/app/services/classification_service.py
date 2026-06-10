"""
Classification service — runs account-type classification on all users
discovered in a job, before NLP/OCEAN/matching.

Entry point:
  classify_job_users(job_id, db)  — called by the orchestrator after content
                                    collection completes and before the job is
                                    marked "completed".

Behaviour:
  - Loads every DiscoveredUser in the job.
  - Calls classifier.classify_user() for each, supplying username, bio,
    display name, follower count, and collected content text.
  - Writes account_type, account_type_confidence, account_type_signals,
    pipeline_excluded, and exclusion_reason to each user row.
  - Returns a summary dict for logging.

Users with account_type in EXCLUDED_TYPES (business, store, competitor)
have pipeline_excluded=True. NLP, OCEAN, and matching services skip them.
UNKNOWN users pass through but receive a 25% final_score penalty in matching.
"""
from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ml.classification.classifier import classify_user, EXCLUDED_TYPES
from app.models.discovery import DiscoveredUser, UserContent

logger = logging.getLogger(__name__)


async def classify_job_users(job_id: UUID, db: AsyncSession) -> dict:
    """
    Classify all users in a discovery job.

    Loads users + their content from DB, runs classify_user() on each,
    and writes classification fields back. Commits once after all users
    are written.

    Returns:
        {
          total: int,
          buyers: int,
          enthusiasts: int,
          community: int,
          creators: int,
          excluded: int,       # business + store + competitor combined
          businesses: int,
          competitors: int,
          unknown: int,
        }
    """
    _log = f"[CLASSIFY job={str(job_id)[:8]}]"
    logger.info("%s START", _log)

    # Load all users for this job
    user_r = await db.execute(
        select(DiscoveredUser).where(DiscoveredUser.discovery_job_id == job_id)
    )
    users = list(user_r.scalars().all())

    if not users:
        logger.info("%s no users found — nothing to classify", _log)
        return _zero_summary()

    # Bulk-load content for all users in one query (avoids N+1)
    user_ids = [u.id for u in users]
    content_r = await db.execute(
        select(UserContent).where(UserContent.user_id.in_(user_ids))
    )
    all_content = list(content_r.scalars().all())

    # Group content texts by user_id
    content_by_user: dict[UUID, list[str]] = {}
    for item in all_content:
        if item.content_type in ("post", "comment", "bio") and item.content_text:
            content_by_user.setdefault(item.user_id, []).append(item.content_text)

    counts: dict[str, int] = {
        "buyers": 0, "enthusiasts": 0, "community": 0,
        "creators": 0, "businesses": 0, "competitors": 0, "unknown": 0,
    }

    for user in users:
        content_texts = content_by_user.get(user.id, [])

        result = classify_user(
            username=user.username or "",
            display_name=user.display_name,
            bio=user.bio,
            follower_count=user.follower_count or 0,
            content_texts=content_texts,
            check_competitor=True,
        )

        user.account_type = result.label
        user.account_type_confidence = result.confidence
        user.account_type_signals = result.signals
        user.pipeline_excluded = result.excluded
        user.exclusion_reason = result.exclusion_reason

        # Tally
        if result.label == "buyer":
            counts["buyers"] += 1
        elif result.label in ("enthusiast", "community"):
            counts[f"{result.label}s" if result.label == "enthusiast" else result.label] += 1
            # Normalise key
            if result.label == "enthusiast":
                counts["enthusiasts"] += 1
            else:
                counts["community"] += 1
        elif result.label == "creator":
            counts["creators"] += 1
        elif result.label == "business":
            counts["businesses"] += 1
        elif result.label == "competitor":
            counts["competitors"] += 1
        else:
            counts["unknown"] += 1

        if result.excluded:
            logger.info(
                "%s EXCLUDED @%s → %s (%.0f%%) signals=%s",
                _log, user.username, result.label,
                result.confidence * 100, result.signals,
            )
        else:
            logger.debug(
                "%s @%s → %s (%.0f%%)",
                _log, user.username, result.label, result.confidence * 100,
            )

    await db.commit()

    excluded = counts["businesses"] + counts["competitors"]
    summary = {
        "total": len(users),
        "buyers": counts["buyers"],
        "enthusiasts": counts["enthusiasts"],
        "community": counts["community"],
        "creators": counts["creators"],
        "excluded": excluded,
        "businesses": counts["businesses"],
        "competitors": counts["competitors"],
        "unknown": counts["unknown"],
    }

    logger.info(
        "%s DONE — total=%d buyers=%d enthusiasts=%d creators=%d "
        "excluded=%d (businesses=%d competitors=%d) unknown=%d",
        _log,
        summary["total"],
        summary["buyers"],
        summary["enthusiasts"],
        summary["creators"],
        summary["excluded"],
        summary["businesses"],
        summary["competitors"],
        summary["unknown"],
    )
    return summary


def _zero_summary() -> dict:
    return {
        "total": 0, "buyers": 0, "enthusiasts": 0, "community": 0,
        "creators": 0, "excluded": 0, "businesses": 0,
        "competitors": 0, "unknown": 0,
    }
