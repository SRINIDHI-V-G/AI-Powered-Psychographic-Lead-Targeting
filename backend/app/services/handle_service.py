"""
Handle discovery service.

Pipeline (per user):
  1. Load discovered user with bio, username, display_name.
  2. Run bio extraction → confirmed/extracted handles (tier set immediately).
  3. Load NLP features → interest tags for generator and ranker.
  4. Load OCEAN scores → ocean dict for ranker plausibility component.
  5. Generate candidate pool (five generators).
  6. Rank candidates → composite handle_score per candidate.
  7. Compute confidence and classify tier for each ranked candidate.
  8. Persist top handles via bulk_create_handles().
  9. Mark user.matched = True (pipeline flag already set by matching step).

Product-level entry point:
  run_handle_discovery_for_product() iterates all matched users for a product.

Background task entry point:
  generate_handles_background() opens its own DB session (matches all
  prior background service patterns).
"""
from __future__ import annotations

import logging
import traceback
import uuid
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.crud.handles import bulk_create_handles, delete_user_handles
from app.ml.handles.bio_extractor import extract_from_bio
from app.ml.handles.confidence_engine import classify_tier, compute_confidence
from app.ml.handles.handle_generator import generate_candidate_pool
from app.ml.handles.handle_ranker import rank_candidates
from app.models.discovery import DiscoveredUser
from app.models.lead_handle import LeadHandle
from app.models.nlp import UserNlpFeatures
from app.models.ocean import UserOceanScore
from app.models.product import Product, ProductStatus

logger = logging.getLogger(__name__)

# How many top-ranked handles to persist per user
_TOP_K_HANDLES = 10

# Minimum handle_score to persist (discard very weak candidates)
_MIN_HANDLE_SCORE = 20.0

# Target platforms to generate candidates for
_TARGET_PLATFORMS = ["twitter", "instagram", "linkedin", "tiktok", "github"]


async def _generate_handles_for_user(
    db: AsyncSession,
    user: DiscoveredUser,
) -> list[LeadHandle]:
    """
    Run the full handle discovery pipeline for a single user.
    Returns a list of LeadHandle objects (not yet persisted).
    """
    _log = f"[HANDLES user={str(user.id)[:8]} @{user.username}]"

    # ── 1. Bio extraction ──────────────────────────────────────────────────
    extracted = extract_from_bio(
        bio=user.bio or "",
        profile_url=user.profile_url,
        known_username=user.username,
    )
    confirmed_handles = [
        h.handle for h in extracted
        if h.tier in ("confirmed", "extracted")
    ]
    logger.debug("%s bio extraction → %d handles", _log, len(extracted))

    # ── 2. Load NLP features (interest tags) ──────────────────────────────
    nlp_r = await db.execute(
        select(UserNlpFeatures).where(UserNlpFeatures.user_id == user.id)
    )
    nlp = nlp_r.scalar_one_or_none()
    interest_tags = list(nlp.interest_tags or []) if nlp else []

    # ── 3. Load OCEAN scores ───────────────────────────────────────────────
    ocean_r = await db.execute(
        select(UserOceanScore).where(UserOceanScore.user_id == user.id)
    )
    ocean_row = ocean_r.scalar_one_or_none()
    ocean_dict: dict[str, float] | None = None
    if ocean_row:
        ocean_dict = {
            "openness":          ocean_row.openness,
            "conscientiousness": ocean_row.conscientiousness,
            "extraversion":      ocean_row.extraversion,
            "agreeableness":     ocean_row.agreeableness,
            "neuroticism":       ocean_row.neuroticism,
        }

    # ── 4. Generate candidate pool ─────────────────────────────────────────
    candidates = await generate_candidate_pool(
        username=user.username,
        display_name=user.display_name,
        bio=user.bio,
        interest_tags=interest_tags,
        platforms=_TARGET_PLATFORMS,
    )

    # ── 5. Rank candidates ─────────────────────────────────────────────────
    ranked = rank_candidates(
        candidates=candidates,
        username=user.username,
        interest_tags=interest_tags,
        ocean=ocean_dict,
        confirmed_handles=confirmed_handles,
    )

    # ── 6. Build LeadHandle objects ────────────────────────────────────────
    handles: list[LeadHandle] = []

    # First: bio-extracted handles (always included, highest priority)
    for ext in extracted:
        tier = ext.tier
        # Recompute confidence using engine for consistency
        conf = compute_confidence(
            handle_score=ext.confidence,
            tier=tier,
            source="bio_extractor",
            fingerprint_consistency=100.0,
            username_similarity=60.0,
            ocean_plausibility=50.0,
        )
        handles.append(LeadHandle(
            id=uuid.uuid4(),
            discovered_user_id=user.id,
            platform=ext.platform,
            handle=ext.handle,
            handle_score=ext.confidence,
            confidence=conf,
            tier=tier,
            evidence_json=ext.evidence,
            verification_json={},
        ))

    # Second: top-K ranked generated candidates (excluding already-bio-extracted)
    bio_handle_set = {h.handle for h in handles}
    added = 0
    for rh in ranked:
        if added >= _TOP_K_HANDLES:
            break
        if rh.handle_score < _MIN_HANDLE_SCORE:
            break
        if rh.handle in bio_handle_set:
            continue
        bio_extracted = False
        tier = classify_tier(rh.handle_score, rh.source, bio_extracted)
        conf = compute_confidence(
            handle_score=rh.handle_score,
            tier=tier,
            source=rh.source,
            fingerprint_consistency=rh.fingerprint_consistency,
            username_similarity=rh.username_similarity,
            ocean_plausibility=rh.ocean_plausibility,
        )
        handles.append(LeadHandle(
            id=uuid.uuid4(),
            discovered_user_id=user.id,
            platform=rh.platform,
            handle=rh.handle,
            handle_score=rh.handle_score,
            confidence=conf,
            tier=tier,
            evidence_json={
                **rh.evidence,
                "username_similarity": rh.username_similarity,
                "interest_alignment": rh.interest_alignment,
                "ocean_plausibility": rh.ocean_plausibility,
                "fingerprint_consistency": rh.fingerprint_consistency,
            },
            verification_json={},
        ))
        bio_handle_set.add(rh.handle)
        added += 1

    logger.debug("%s generated %d handles", _log, len(handles))
    return handles


async def run_handle_discovery_for_product(
    db: AsyncSession,
    product_id: UUID,
) -> dict:
    """
    Run handle discovery for all matched users of a product.

    Re-run safe: deletes existing handles per user before inserting fresh ones.
    Returns: {total, processed, failed}
    """
    _log = f"[HANDLES product={str(product_id)[:8]}]"
    logger.info("%s START", _log)

    user_r = await db.execute(
        select(DiscoveredUser).where(
            DiscoveredUser.product_id == product_id,
            DiscoveredUser.matched == True,  # noqa: E712
        )
    )
    users = list(user_r.scalars().all())
    total = len(users)
    processed = 0
    failed = 0

    logger.info("%s %d matched users to process", _log, total)

    for user in users:
        try:
            # Clear stale handles before regenerating
            await delete_user_handles(db, user.id)

            handles = await _generate_handles_for_user(db, user)
            if handles:
                await bulk_create_handles(db, handles)
                processed += 1
            else:
                processed += 1

            await db.commit()

        except Exception as exc:
            logger.warning("%s failed user %s: %s", _log, user.id, exc)
            failed += 1
            await db.rollback()

    logger.info("%s DONE — processed=%d failed=%d", _log, processed, failed)
    return {"total": total, "processed": processed, "failed": failed}


async def generate_handles_background(product_id: str) -> None:
    """
    Background task entry point: run handle discovery for a product,
    then advance the product to ProductStatus.completed.

    Opens its own DB session — matches all prior background service patterns.
    """
    _log = f"[HANDLES bg product={product_id[:8]}]"
    logger.info("%s background task started", _log)

    async with AsyncSessionLocal() as db:
        product: Product | None = await db.get(Product, UUID(product_id))
        if not product:
            logger.error("%s product not found", _log)
            return

        try:
            summary = await run_handle_discovery_for_product(db, UUID(product_id))

            product.status = ProductStatus.completed
            # pipeline_step stays at 9 (ranked) — handle generation is transparent to the user
            await db.commit()

            logger.info(
                "%s complete — processed=%d failed=%d",
                _log, summary["processed"], summary["failed"],
            )

        except Exception as exc:
            tb = traceback.format_exc()
            logger.exception("%s FAILED: %s", _log, exc)
            product.status = ProductStatus.failed
            product.error_message = f"{type(exc).__name__}: {exc}\n{tb}"[:1000]
            await db.commit()
