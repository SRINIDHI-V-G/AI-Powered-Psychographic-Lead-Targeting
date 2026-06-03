"""
OCEAN personality scoring service.

Pipeline per user:
  1. Load UserNlpFeatures — exit if not found or already scored.
  2. Check token count — use insufficient_content scoring if below threshold.
  3. Load top-N UserContent items by engagement for content samples.
  4. Build compact LLM prompt from NLP features + content samples.
  5. Call Ollama; parse response.
     → On failure or USE_MOCK_LLM: fall back to heuristic scorer.
  6. Persist UserOceanScore (upsert — delete stale row if exists).
  7. Mark discovered_users.ocean_scored = True.

Batch:
  run_ocean_for_product() processes all NLP-processed, ocean-unscored users
  in configurable batches and advances product.pipeline_step = 6.

Auto-trigger:
  NLP service calls start_ocean_background() when batch NLP completes.
"""
from __future__ import annotations

import logging
import traceback
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.ml.llm_client import OllamaClient
from app.ml.ocean.heuristic_scorer import (
    compute_heuristic_scores,
    compute_insufficient_content_scores,
)
from app.ml.ocean.ocean_prompter import (
    MIN_TOKENS_FOR_LLM,
    MAX_CONTENT_SAMPLES,
    build_ocean_prompt,
    parse_ocean_response,
)
from app.models.discovery import DiscoveredUser, UserContent
from app.models.nlp import UserNlpFeatures
from app.models.ocean import UserOceanScore
from app.models.product import Product, ProductStatus

logger = logging.getLogger(__name__)

_BATCH_SIZE = 20
# OCEAN LLM output needs ~1200 tokens (5 dims × score + reasoning)
_OCEAN_NUM_PREDICT = 1200
# Minimum tokens to attempt LLM scoring
_MIN_TOKENS = MIN_TOKENS_FOR_LLM


# ── Per-user OCEAN processing ─────────────────────────────────────────────────

async def process_user_ocean(db: AsyncSession, user_id: UUID) -> bool:
    """
    Score one discovered user's OCEAN personality.

    Returns True if a score was produced, False if skipped.
    Raises on hard DB errors only (LLM errors are caught internally).
    """
    user: DiscoveredUser | None = await db.get(DiscoveredUser, user_id)
    if not user:
        logger.warning("[OCEAN] user %s not found", user_id)
        return False
    if user.ocean_scored:
        logger.debug("[OCEAN] user %s already scored — skipping", user.username)
        return False

    # Load NLP features
    nlp_result = await db.execute(
        select(UserNlpFeatures).where(UserNlpFeatures.user_id == user_id)
    )
    nlp: UserNlpFeatures | None = nlp_result.scalar_one_or_none()

    if not nlp:
        logger.info(
            "[OCEAN] user %s has no NLP features — scoring with insufficient_content",
            user.username,
        )
        scores = compute_insufficient_content_scores()
    elif nlp.total_tokens < _MIN_TOKENS:
        logger.info(
            "[OCEAN] user %s has only %d tokens — using insufficient_content scoring",
            user.username, nlp.total_tokens,
        )
        scores = compute_insufficient_content_scores()
    else:
        scores = await _score_user(db, user, nlp)

    # ── Upsert: delete stale record if present ────────────────────────────────
    existing = await db.execute(
        select(UserOceanScore).where(UserOceanScore.user_id == user_id)
    )
    stale = existing.scalar_one_or_none()
    if stale:
        await db.delete(stale)
        await db.flush()

    # ── Persist ───────────────────────────────────────────────────────────────
    db.add(UserOceanScore(
        user_id=user_id,
        openness=scores["openness"],
        conscientiousness=scores["conscientiousness"],
        extraversion=scores["extraversion"],
        agreeableness=scores["agreeableness"],
        neuroticism=scores["neuroticism"],
        confidence=scores["confidence"],
        scoring_method=scores["scoring_method"],
        reasoning=scores["reasoning"],
        raw_llm_response=scores.get("raw_llm_response"),
    ))
    user.ocean_scored = True
    return True


async def _score_user(
    db: AsyncSession,
    user: DiscoveredUser,
    nlp: UserNlpFeatures,
) -> dict:
    """
    Attempt LLM scoring; fall back to heuristic on any error.
    """
    if settings.USE_MOCK_LLM:
        logger.info("[OCEAN] USE_MOCK_LLM=True — using heuristic for %s", user.username)
        return compute_heuristic_scores(
            empath_scores=nlp.empath_scores or {},
            total_tokens=nlp.total_tokens,
            vocabulary_richness=nlp.vocabulary_richness,
            avg_sentence_length=nlp.avg_sentence_length,
        )

    # Load top-N content samples by engagement
    content_result = await db.execute(
        select(UserContent)
        .where(
            UserContent.user_id == user.id,
            UserContent.content_type.in_(["post", "comment"]),
        )
        .order_by(UserContent.engagement.desc())
        .limit(MAX_CONTENT_SAMPLES)
    )
    content_items = list(content_result.scalars().all())
    content_samples = [
        item.content_text for item in content_items
        if item.content_text and item.content_text.strip()
    ]

    prompt = build_ocean_prompt(
        interest_tags=list(nlp.interest_tags or []),
        empath_scores=dict(nlp.empath_scores or {}),
        keyword_frequency=dict(nlp.keyword_frequency or {}),
        vocabulary_richness=float(nlp.vocabulary_richness or 0.5),
        avg_sentence_length=float(nlp.avg_sentence_length or 10.0),
        total_tokens=nlp.total_tokens,
        content_samples=content_samples,
    )

    raw_response: str | None = None
    try:
        client = OllamaClient()
        raw_response = await client.generate(
            prompt=prompt,
            system=_OCEAN_SYSTEM_PROMPT_IMPORT(),
            temperature=0.2,
            num_predict=_OCEAN_NUM_PREDICT,
        )
        scores = parse_ocean_response(raw_response)
        if scores:
            scores["raw_llm_response"] = raw_response[:2000]
            logger.info(
                "[OCEAN] LLM scored %s: O=%.0f C=%.0f E=%.0f A=%.0f N=%.0f conf=%.0f",
                user.username,
                scores["openness"], scores["conscientiousness"],
                scores["extraversion"], scores["agreeableness"],
                scores["neuroticism"], scores["confidence"],
            )
            return scores
        logger.warning("[OCEAN] LLM response unparseable for %s — using heuristic", user.username)

    except (ConnectionError, TimeoutError, RuntimeError) as exc:
        logger.warning("[OCEAN] LLM failed for %s: %s — using heuristic", user.username, exc)

    # ── Heuristic fallback ────────────────────────────────────────────────────
    fallback = compute_heuristic_scores(
        empath_scores=nlp.empath_scores or {},
        total_tokens=nlp.total_tokens,
        vocabulary_richness=nlp.vocabulary_richness,
        avg_sentence_length=nlp.avg_sentence_length,
    )
    fallback["scoring_method"] = "heuristic"
    if raw_response:
        fallback["raw_llm_response"] = raw_response[:2000]
    return fallback


def _OCEAN_SYSTEM_PROMPT_IMPORT() -> str:
    from app.ml.ocean.ocean_prompter import OCEAN_SYSTEM_PROMPT
    return OCEAN_SYSTEM_PROMPT


# ── Product-level batch processing ───────────────────────────────────────────

async def run_ocean_for_product(db: AsyncSession, product_id: UUID) -> dict:
    """
    Process all NLP-processed, ocean-unscored users for a product.
    Returns a summary dict: {total, processed, failed}.
    """
    _log = f"[OCEAN product={str(product_id)[:8]}]"
    logger.info("%s START", _log)

    result = await db.execute(
        select(DiscoveredUser.id).where(
            DiscoveredUser.product_id == product_id,
            DiscoveredUser.nlp_processed == True,   # noqa: E712
            DiscoveredUser.ocean_scored == False,    # noqa: E712
        )
    )
    user_ids = [row[0] for row in result.fetchall()]
    total = len(user_ids)
    processed = 0
    failed = 0

    logger.info("%s %d users to score", _log, total)

    for i in range(0, total, _BATCH_SIZE):
        batch = user_ids[i: i + _BATCH_SIZE]
        for uid in batch:
            try:
                success = await process_user_ocean(db, uid)
                if success:
                    processed += 1
            except Exception as exc:
                logger.warning("%s failed user %s: %s", _log, uid, exc)
                failed += 1
        await db.commit()
        logger.info(
            "%s scored %d / %d (failed: %d)",
            _log, processed + failed, total, failed,
        )

    logger.info("%s DONE — processed=%d failed=%d", _log, processed, failed)
    return {"total": total, "processed": processed, "failed": failed}


# ── Background task entry point ───────────────────────────────────────────────

async def start_ocean_background(product_id: str) -> None:
    """
    Background task: score all users of a product, then advance pipeline step.
    Opens its own DB session (mirrors NLP service pattern).
    """
    _log = f"[OCEAN bg product={product_id[:8]}]"
    logger.info("%s background task started", _log)

    async with AsyncSessionLocal() as db:
        product: Product | None = await db.get(Product, UUID(product_id))
        if not product:
            logger.error("%s product not found", _log)
            return

        product.status = ProductStatus.ocean_scoring
        product.pipeline_step = 6
        await db.commit()

        try:
            summary = await run_ocean_for_product(db, UUID(product_id))

            product.status = ProductStatus.ocean_scoring
            product.pipeline_step = 6
            await db.commit()

            logger.info(
                "%s complete — processed=%d failed=%d",
                _log, summary["processed"], summary["failed"],
            )

            # ── Auto-trigger matching ─────────────────────────────────────────
            if summary["processed"] > 0:
                from app.workers.dispatch import dispatch
                logger.info(
                    "%s auto-triggering matching for %d users",
                    _log, summary["processed"],
                )
                dispatch("matching", product_id)

        except Exception as exc:
            tb = traceback.format_exc()
            logger.exception("%s FAILED: %s", _log, exc)
            product.status = ProductStatus.failed
            product.error_message = f"{type(exc).__name__}: {exc}\n{tb}"[:1000]
            await db.commit()
