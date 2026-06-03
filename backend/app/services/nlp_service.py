"""
NLP service — processes a discovered user's content through the NLP pipeline.

Pipeline per user:
  1. Load user + content from DB.
  2. Clean + combine all text.
  3. Generate 384-dim sentence-transformer embedding.
  4. Compute Empath emotional/topic scores → extract interest tags.
  5. Compute basic text metrics (vocab richness, entities, keyword freq).
  6. Optionally run BERTopic (skipped if unavailable or < 2 posts).
  7. Persist UserEmbedding + UserNlpFeatures.
  8. Mark discovered_users.nlp_processed = True.

Batch orchestration:
  run_nlp_for_product() processes all unprocessed users for a product in
  configurable batches, then advances product.pipeline_step = 5.

Auto-trigger:
  The discovery orchestrator calls start_nlp_background() when content
  collection is complete.
"""
from __future__ import annotations

import logging
import traceback
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.ml.nlp.bertopic_modeler import TopicModeler
from app.ml.nlp.empath_analyzer import EmpathAnalyzer
from app.ml.nlp.embeddings import EmbeddingModel
from app.ml.nlp.text_cleaner import clean_text, combine_user_content
from app.ml.nlp.text_processor import extract_features
from app.models.discovery import DiscoveredUser, UserContent
from app.models.nlp import UserEmbedding, UserNlpFeatures
from app.models.product import Product, ProductStatus

logger = logging.getLogger(__name__)

# Batch size: number of users processed per DB transaction
_BATCH_SIZE = 20


# ── Per-user NLP processing ───────────────────────────────────────────────────

async def process_user_nlp(db: AsyncSession, user_id: UUID) -> bool:
    """
    Run the full NLP pipeline for one discovered user.
    Returns True on success, False if skipped (no content / already processed).
    Raises on hard errors.
    """
    # Load user
    user: DiscoveredUser | None = await db.get(DiscoveredUser, user_id)
    if not user:
        logger.warning("[NLP] user %s not found", user_id)
        return False
    if user.nlp_processed:
        logger.debug("[NLP] user %s already processed", user.username)
        return False

    # Load content
    result = await db.execute(
        select(UserContent).where(UserContent.user_id == user_id)
    )
    content_items = list(result.scalars().all())

    post_texts = [
        item.content_text for item in content_items
        if item.content_type in ("post", "comment") and item.content_text
    ]
    combined = combine_user_content(user.bio, post_texts)

    if not combined.strip():
        logger.info("[NLP] user %s has no usable text — skipping", user.username)
        user.nlp_processed = True  # mark so we don't retry empty users
        return False

    # ── 1. Embedding ──────────────────────────────────────────────────────────
    embedder = EmbeddingModel()
    # Run in executor to avoid blocking the event loop during model inference
    import asyncio
    loop = asyncio.get_running_loop()
    embedding_vec = await loop.run_in_executor(None, embedder.encode, combined)

    # ── 2. Empath ─────────────────────────────────────────────────────────────
    empath = EmpathAnalyzer()
    empath_scores = await loop.run_in_executor(None, empath.analyze, combined)
    interest_tags = empath.get_top_categories(empath_scores, n=10)

    # ── 3. Text metrics ───────────────────────────────────────────────────────
    text_features = extract_features(combined)

    # ── 4. BERTopic (optional) ────────────────────────────────────────────────
    topic_modeler = TopicModeler()
    bertopic_topics: list[dict] = []
    if len(post_texts) >= 2:
        bertopic_topics = await loop.run_in_executor(
            None, topic_modeler.get_topics, post_texts
        )

    # ── 5. Delete stale records before inserting (handles re-runs) ───────────
    existing_emb = await db.execute(
        select(UserEmbedding).where(
            UserEmbedding.user_id == user_id,
            UserEmbedding.embedding_type == "combined",
        )
    )
    stale_emb = existing_emb.scalar_one_or_none()
    if stale_emb:
        await db.delete(stale_emb)

    existing_nlp = await db.execute(
        select(UserNlpFeatures).where(UserNlpFeatures.user_id == user_id)
    )
    stale_nlp = existing_nlp.scalar_one_or_none()
    if stale_nlp:
        await db.delete(stale_nlp)

    await db.flush()

    # ── 6. Persist ────────────────────────────────────────────────────────────
    from app.models.nlp import _HAS_PGVECTOR  # noqa: PLC0415
    db.add(UserEmbedding(
        user_id=user_id,
        embedding_type="combined",
        embedding=embedding_vec,            # JSONB — always populated
        embedding_vector=embedding_vec if _HAS_PGVECTOR else None,  # VECTOR(384) when available
        model_used="all-MiniLM-L6-v2",
        token_count=text_features["total_tokens"],
    ))

    db.add(UserNlpFeatures(
        user_id=user_id,
        empath_scores=empath_scores,
        bertopic_topics=bertopic_topics,
        bertopic_probs=[],
        spacy_entities=text_features["entities"],
        interest_tags=interest_tags,
        keyword_frequency=text_features["keyword_frequency"],
        vocabulary_richness=text_features["vocabulary_richness"],
        avg_sentence_length=text_features["avg_sentence_length"],
        total_tokens=text_features["total_tokens"],
    ))

    user.nlp_processed = True
    return True


# ── Product-level batch processing ───────────────────────────────────────────

async def run_nlp_for_product(db: AsyncSession, product_id: UUID) -> dict:
    """
    Process all unprocessed users for a product in batches.
    Returns a summary dict with counts.
    """
    _log = f"[NLP product={str(product_id)[:8]}]"
    logger.info("%s START", _log)

    result = await db.execute(
        select(DiscoveredUser.id).where(
            DiscoveredUser.product_id == product_id,
            DiscoveredUser.content_collected == True,   # noqa: E712
            DiscoveredUser.nlp_processed == False,      # noqa: E712
        )
    )
    user_ids = [row[0] for row in result.fetchall()]
    total = len(user_ids)
    processed = 0
    failed = 0

    logger.info("%s %d users to process", _log, total)

    for i in range(0, total, _BATCH_SIZE):
        batch = user_ids[i: i + _BATCH_SIZE]
        for uid in batch:
            try:
                success = await process_user_nlp(db, uid)
                if success:
                    processed += 1
            except Exception as exc:
                logger.warning("%s failed user %s: %s", _log, uid, exc)
                failed += 1
        await db.commit()
        logger.info(
            "%s processed %d / %d (failed: %d)", _log, processed + failed, total, failed
        )

    logger.info("%s DONE — processed=%d failed=%d", _log, processed, failed)
    return {"total": total, "processed": processed, "failed": failed}


# ── Background task entry point ───────────────────────────────────────────────

async def start_nlp_background(product_id: str) -> None:
    """
    Background task: run NLP for all users of a product, then advance pipeline.
    Opens its own DB session (pattern matching motivation/discovery services).
    """
    _log = f"[NLP bg product={product_id[:8]}]"
    logger.info("%s background task started", _log)

    async with AsyncSessionLocal() as db:
        # Advance product status to nlp_processing
        product: Product | None = await db.get(Product, UUID(product_id))
        if not product:
            logger.error("%s product not found", _log)
            return

        product.status = ProductStatus.nlp_processing
        product.pipeline_step = 5
        await db.commit()

        try:
            summary = await run_nlp_for_product(db, UUID(product_id))

            product.status = ProductStatus.nlp_processing
            product.pipeline_step = 5
            await db.commit()

            logger.info(
                "%s complete — processed=%d failed=%d",
                _log, summary["processed"], summary["failed"],
            )

            # ── Auto-trigger OCEAN scoring ────────────────────────────────────
            if summary["processed"] > 0:
                from app.workers.dispatch import dispatch
                logger.info(
                    "%s auto-triggering OCEAN scoring for %d users",
                    _log, summary["processed"],
                )
                dispatch("ocean", product_id)

        except Exception as exc:
            tb = traceback.format_exc()
            logger.exception("%s FAILED: %s", _log, exc)
            product.status = ProductStatus.failed
            product.error_message = f"{type(exc).__name__}: {exc}\n{tb}"[:1000]
            await db.commit()
