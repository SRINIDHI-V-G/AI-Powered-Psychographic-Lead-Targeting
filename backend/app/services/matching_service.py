"""
Matching service — computes psychographic match scores and ranks leads.

Pipeline:
  1. Load all active motivation categories + OCEAN profiles for the product.
  2. Pre-compute sentence-transformer embeddings for motivation descriptions
     (one per category, cached in-memory for the run duration).
  3. For each OCEAN-scored user:
       a. Load UserOceanScore, UserNlpFeatures, UserEmbedding.
       b. Compute OCEAN similarity, embedding similarity, interest overlap.
       c. Persist LeadMatch rows (one per user × motivation category).
       d. Mark user.matched = True.
  4. After all users processed, run ranking pass:
       - Mark best motivation per user (is_best_match=True).
       - Assign rank 1…N by descending best match score.

Re-run behaviour (upsert):
  Existing matches for the product are deleted before recomputing.
  This ensures ranking is always fresh and consistent.

Auto-trigger:
  Called by start_ocean_background() when OCEAN scoring completes.
"""
from __future__ import annotations

import logging
import traceback
from uuid import UUID

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.crud.product_ocean import get_product_ocean
from app.ml.matching.scorer import (
    normalize_motivation_ocean,
    compute_ocean_similarity,
    compute_embedding_similarity,
    compute_interest_score,
    compute_composite_score,
    compute_match_confidence,
    build_reasoning,
)
from app.ml.nlp.embeddings import EmbeddingModel
from app.models.discovery import DiscoveredUser
from app.models.matching import LeadMatch
from app.models.motivation import MotivationCategory, MotivationOceanProfile
from app.models.nlp import UserEmbedding, UserNlpFeatures
from app.models.ocean import UserOceanScore
from app.models.product import Product, ProductStatus

logger = logging.getLogger(__name__)

_BATCH_SIZE = 20


# ── Motivation embedding cache ────────────────────────────────────────────────

def _embed_motivations(
    categories: list[MotivationCategory],
) -> dict[UUID, list[float]]:
    """
    Encode motivation descriptions once per run.
    Returns {category_id: embedding_vector}.
    Uses the same all-MiniLM-L6-v2 model as the NLP pipeline.
    """
    model = EmbeddingModel()
    embeddings: dict[UUID, list[float]] = {}
    for cat in categories:
        text = f"{cat.name}: {cat.description}"
        embeddings[cat.id] = model.encode(text)
    return embeddings


# ── Per-user matching ─────────────────────────────────────────────────────────

async def _compute_user_matches(
    db: AsyncSession,
    user: DiscoveredUser,
    categories: list[MotivationCategory],
    motiv_embeddings: dict[UUID, list[float]],
    product_ocean_100: dict[str, float] | None = None,
) -> list[LeadMatch]:
    """
    Compute LeadMatch rows for one user across all motivation categories.
    Returns a list (one entry per category). Empty list if user has no OCEAN score.
    """
    # Load OCEAN score
    ocean_r = await db.execute(
        select(UserOceanScore).where(UserOceanScore.user_id == user.id)
    )
    ocean: UserOceanScore | None = ocean_r.scalar_one_or_none()
    if not ocean:
        logger.debug("[MATCH] user %s has no OCEAN score — skipping", user.username)
        return []

    # Load NLP features (for interest tags and keyword frequency)
    nlp_r = await db.execute(
        select(UserNlpFeatures).where(UserNlpFeatures.user_id == user.id)
    )
    nlp: UserNlpFeatures | None = nlp_r.scalar_one_or_none()
    user_tags = list(nlp.interest_tags or []) if nlp else []
    user_keywords = dict(nlp.keyword_frequency or {}) if nlp else {}

    # Load embedding — prefer native VECTOR column, fall back to JSONB
    emb_r = await db.execute(
        select(UserEmbedding).where(
            UserEmbedding.user_id == user.id,
            UserEmbedding.embedding_type == "combined",
        )
    )
    emb_row: UserEmbedding | None = emb_r.scalar_one_or_none()
    if emb_row:
        # embedding_vector is the pgvector VECTOR(384) column (may be None on old rows)
        vec_source = getattr(emb_row, "embedding_vector", None) or emb_row.embedding
        user_vec: list[float] | None = list(vec_source) if vec_source else None
    else:
        user_vec = None

    matches: list[LeadMatch] = []
    for cat in categories:
        if not cat.ocean_profile:
            logger.warning(
                "[MATCH] motivation category %s has no OCEAN profile — skipping",
                cat.name,
            )
            continue

        motiv_ocean_100 = normalize_motivation_ocean(cat.ocean_profile)
        motiv_vec = motiv_embeddings.get(cat.id)
        motiv_tags = list(cat.ocean_profile.interest_tags or [])
        motiv_kw = list(cat.ocean_profile.search_keywords or [])

        ocean_s = compute_ocean_similarity(ocean, motiv_ocean_100)
        embed_s = compute_embedding_similarity(user_vec, motiv_vec)
        interest_s = compute_interest_score(user_tags, user_keywords, motiv_tags, motiv_kw)
        final_s = compute_composite_score(ocean_s, embed_s, interest_s)
        conf = compute_match_confidence(
            ocean.confidence,
            has_embedding=user_vec is not None,
            interest_tag_count=len(user_tags),
        )
        reasons = build_reasoning(ocean_s, embed_s, interest_s, user_tags, motiv_tags, cat.name)

        # Supplementary product-level alignment score (does not affect final_score)
        product_ocean_s: float | None = None
        if product_ocean_100 is not None:
            product_ocean_s = compute_ocean_similarity(ocean, product_ocean_100)

        matches.append(LeadMatch(
            product_id=user.product_id,
            user_id=user.id,
            motivation_category_id=cat.id,
            ocean_score=ocean_s,
            embedding_score=embed_s,
            interest_score=interest_s,
            product_ocean_score=product_ocean_s,
            final_score=final_s,
            confidence=conf,
            reasoning=reasons,
            is_best_match=False,
            rank=None,
        ))

    return matches


# ── Ranking pass ──────────────────────────────────────────────────────────────

async def _apply_ranking(db: AsyncSession, product_id: UUID) -> None:
    """
    After all matches are computed, identify the best motivation per user
    and assign ordinal ranks ordered by best match score descending.

    Only is_best_match=True rows receive a rank value.
    """
    result = await db.execute(
        select(LeadMatch)
        .where(LeadMatch.product_id == product_id)
        .order_by(LeadMatch.user_id, LeadMatch.final_score.desc())
    )
    all_matches = list(result.scalars().all())

    # Best match per user = first row in score-desc order per user
    best_per_user: dict[UUID, LeadMatch] = {}
    for m in all_matches:
        if m.user_id not in best_per_user:
            best_per_user[m.user_id] = m

    # Sort users by their best match score
    ranked = sorted(best_per_user.values(), key=lambda m: m.final_score, reverse=True)

    for rank_num, match in enumerate(ranked, start=1):
        match.is_best_match = True
        match.rank = rank_num

    await db.flush()
    logger.info("[MATCH] ranking applied — %d leads ranked", len(ranked))


# ── Product-level batch matching ──────────────────────────────────────────────

async def run_matching_for_product(db: AsyncSession, product_id: UUID) -> dict:
    """
    Compute psychographic match scores for all OCEAN-scored users of a product.

    Performs a full re-run (deletes existing matches first) so results are
    always consistent even if motivation categories were updated.

    Returns: {total, processed, failed}
    """
    _log = f"[MATCH product={str(product_id)[:8]}]"
    logger.info("%s START", _log)

    # ── 1. Load motivation categories + OCEAN profiles with explicit JOIN ────
    # Bypass ORM relationship lazy-loading entirely — use two separate awaited
    # queries so no implicit sync I/O can fire inside an asyncio background task.
    cat_r = await db.execute(
        select(MotivationCategory)
        .where(
            MotivationCategory.product_id == product_id,
            MotivationCategory.is_active == True,  # noqa: E712
        )
        .order_by(MotivationCategory.sort_order)
    )
    categories = list(cat_r.scalars().all())

    if not categories:
        logger.warning("%s no active motivation categories found — aborting", _log)
        return {"total": 0, "processed": 0, "failed": 0}

    # Explicitly load each category's OCEAN profile via a separate awaited query.
    # This avoids the MissingGreenlet error caused by accessing a lazy-loaded
    # relationship attribute inside an asyncio create_task background context.
    for cat in categories:
        prof_r = await db.execute(
            select(MotivationOceanProfile).where(
                MotivationOceanProfile.motivation_category_id == cat.id
            )
        )
        cat.ocean_profile = prof_r.scalar_one_or_none()

    # ── 1b. Load product-level OCEAN profile (supplementary signal) ───────────
    product_ocean_profile = await get_product_ocean(db, product_id)
    if product_ocean_profile:
        product_ocean_100: dict[str, float] | None = {
            "openness":          product_ocean_profile.openness,
            "conscientiousness": product_ocean_profile.conscientiousness,
            "extraversion":      product_ocean_profile.extraversion,
            "agreeableness":     product_ocean_profile.agreeableness,
            "neuroticism":       product_ocean_profile.neuroticism,
        }
        logger.info(
            "%s product OCEAN loaded — will compute product_ocean_score per lead",
            _log,
        )
    else:
        product_ocean_100 = None
        logger.info(
            "%s no product OCEAN profile found — product_ocean_score will be NULL",
            _log,
        )

    # ── 2. Pre-compute motivation embeddings (once per run) ───────────────────
    motiv_embeddings = _embed_motivations(categories)
    logger.info(
        "%s pre-computed embeddings for %d motivation categories",
        _log, len(categories),
    )

    # ── 3. Acquire advisory lock + clear stale matches ───────────────────────
    # The advisory lock serialises concurrent matching runs for the same product
    # (e.g. auto-trigger from OCEAN + explicit call from E2E script running in
    # parallel).  It is transaction-scoped: released automatically on COMMIT/ROLLBACK.
    lock_key = int.from_bytes(product_id.bytes[:8], "big") % (2**62)
    await db.execute(text("SELECT pg_advisory_xact_lock(:k)").bindparams(k=lock_key))
    logger.debug("%s advisory lock acquired (key=%d)", _log, lock_key)

    await db.execute(
        delete(LeadMatch).where(LeadMatch.product_id == product_id)
    )
    await db.flush()

    # ── 4. Load all OCEAN-scored users ────────────────────────────────────────
    user_r = await db.execute(
        select(DiscoveredUser).where(
            DiscoveredUser.product_id == product_id,
            DiscoveredUser.ocean_scored == True,   # noqa: E712
        )
    )
    users = list(user_r.scalars().all())
    total = len(users)
    processed = 0
    failed = 0

    logger.info("%s %d users to match against %d categories", _log, total, len(categories))

    # ── 5. Compute matches in batches ─────────────────────────────────────────
    for i in range(0, total, _BATCH_SIZE):
        batch = users[i: i + _BATCH_SIZE]
        for user in batch:
            try:
                matches = await _compute_user_matches(
                    db, user, categories, motiv_embeddings, product_ocean_100
                )
                if matches:
                    for m in matches:
                        db.add(m)
                    user.matched = True
                    processed += 1
                else:
                    failed += 1
            except Exception as exc:
                logger.warning("[MATCH] failed user %s: %s", user.id, exc)
                failed += 1

        await db.commit()
        logger.info(
            "%s matched %d / %d (failed: %d)",
            _log, processed + failed, total, failed,
        )

    # ── 6. Apply ranking pass ─────────────────────────────────────────────────
    if processed > 0:
        await _apply_ranking(db, product_id)
        await db.commit()

    logger.info("%s DONE — processed=%d failed=%d", _log, processed, failed)
    return {"total": total, "processed": processed, "failed": failed}


# ── Background task entry point ───────────────────────────────────────────────

async def start_matching_background(product_id: str) -> None:
    """
    Background task: run matching for all users of a product, then advance pipeline.
    Opens its own DB session (mirrors all prior background service pattern).
    """
    _log = f"[MATCH bg product={product_id[:8]}]"
    logger.info("%s background task started", _log)

    async with AsyncSessionLocal() as db:
        product: Product | None = await db.get(Product, UUID(product_id))
        if not product:
            logger.error("%s product not found", _log)
            return

        product.status = ProductStatus.matching
        product.pipeline_step = 8
        await db.commit()

        try:
            summary = await run_matching_for_product(db, UUID(product_id))

            product.status = ProductStatus.ranked
            product.pipeline_step = 9
            await db.commit()

            logger.info(
                "%s complete — processed=%d failed=%d",
                _log, summary["processed"], summary["failed"],
            )

            # Fire handle discovery as a separate background task — it's post-ranking
            # enrichment and should not block the pipeline or keep the event loop busy.
            # Product is already 'ranked' at this point (user-visible final state).
            import asyncio as _asyncio_handles
            from app.services.handle_service import generate_handles_background
            _asyncio_handles.create_task(generate_handles_background(product_id))

        except Exception as exc:
            tb = traceback.format_exc()
            logger.exception("%s FAILED: %s", _log, exc)
            product.status = ProductStatus.failed
            product.error_message = f"{type(exc).__name__}: {exc}\n{tb}"[:1000]
            await db.commit()
