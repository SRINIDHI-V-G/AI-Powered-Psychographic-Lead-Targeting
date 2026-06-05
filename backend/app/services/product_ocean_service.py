"""
Product OCEAN aggregation service.

Derives a single OCEAN vector for a registered product by computing the
arithmetic mean of all its motivation OCEAN profiles.

Scale conversion:
  MotivationOceanProfile stores values on a 0-10 scale with `emotional_stability`
  (the inverse of neuroticism). This service converts to the 0-100 scale used
  by ProductOceanProfile and UserOceanScore so that the matching service can
  compare product vs lead OCEAN directly without any further conversion.

  openness          = motivation.openness          × 10
  conscientiousness = motivation.conscientiousness × 10
  extraversion      = motivation.extraversion      × 10
  agreeableness     = motivation.agreeableness     × 10
  neuroticism       = 100 − (motivation.emotional_stability × 10)

Pipeline position:
  Triggered automatically by motivation_service after motivations_generated.
  On success, dispatches "similar_products" to continue the chain.
"""
from __future__ import annotations

import logging
import traceback
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.motivation import get_motivations_by_product
from app.crud.product_ocean import get_product_ocean, upsert_product_ocean
from app.database import AsyncSessionLocal
from app.models.motivation import MotivationOceanProfile
from app.models.product import Product, ProductStatus

logger = logging.getLogger(__name__)

# Exported so routers and the matching service can call it without importing CRUD directly
__all__ = ["generate_product_ocean_background", "get_product_ocean_for_product"]


# ── Convenience re-export for router use ─────────────────────────────────────

async def get_product_ocean_for_product(db: AsyncSession, product_id: UUID):
    """
    Return the ProductOceanProfile for a product, or None if not yet generated.
    Thin wrapper over the CRUD layer; keeps the router import surface clean.
    """
    return await get_product_ocean(db, product_id)


# ── OCEAN aggregation ─────────────────────────────────────────────────────────

def _to_100_scale(profile: MotivationOceanProfile) -> dict[str, float]:
    """
    Convert one MotivationOceanProfile (0-10) to the 0-100 scale used by
    ProductOceanProfile, applying the emotional_stability → neuroticism inversion.
    Clamps inputs to [0, 10] before scaling — mirrors normalize_motivation_ocean()
    in ml/matching/scorer.py.
    """
    def _c10(v: float) -> float:
        return max(0.0, min(10.0, float(v)))

    return {
        "openness":          _c10(profile.openness)          * 10.0,
        "conscientiousness": _c10(profile.conscientiousness) * 10.0,
        "extraversion":      _c10(profile.extraversion)      * 10.0,
        "agreeableness":     _c10(profile.agreeableness)     * 10.0,
        "neuroticism":       100.0 - _c10(profile.emotional_stability) * 10.0,
    }


async def _compute_product_ocean(
    db: AsyncSession,
    product_id: UUID,
    _log: str,
) -> dict | None:
    """
    Load all active motivation categories + OCEAN profiles for the product,
    convert each to 0-100 scale, and return their arithmetic mean.

    Returns None if no profiles are available (caller should abort gracefully).
    """
    categories = await get_motivations_by_product(db, product_id)

    if not categories:
        logger.warning("%s no motivation categories found — cannot derive product OCEAN", _log)
        return None

    valid_vectors: list[dict[str, float]] = []
    for cat in categories:
        if cat.ocean_profile is None:
            # Load profile explicitly in case selectinload was not used
            prof_r = await db.execute(
                select(MotivationOceanProfile).where(
                    MotivationOceanProfile.motivation_category_id == cat.id
                )
            )
            cat.ocean_profile = prof_r.scalar_one_or_none()

        if cat.ocean_profile is not None:
            valid_vectors.append(_to_100_scale(cat.ocean_profile))

    if not valid_vectors:
        logger.warning(
            "%s all motivation categories lack OCEAN profiles — cannot derive product OCEAN",
            _log,
        )
        return None

    dims = ("openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism")
    n = len(valid_vectors)
    averaged = {d: sum(v[d] for v in valid_vectors) / n for d in dims}

    # Confidence: proportion of motivation categories that had a valid OCEAN profile
    confidence = (n / len(categories)) * 100.0

    logger.info(
        "%s aggregated %d/%d motivation profiles → "
        "O=%.1f C=%.1f E=%.1f A=%.1f N=%.1f (conf=%.0f%%)",
        _log, n, len(categories),
        averaged["openness"], averaged["conscientiousness"],
        averaged["extraversion"], averaged["agreeableness"],
        averaged["neuroticism"], confidence,
    )

    return {**averaged, "confidence": confidence, "component_count": n}


# ── Background task entry point ───────────────────────────────────────────────

async def generate_product_ocean_background(product_id: str) -> None:
    """
    Background task: derive and persist the product-level OCEAN profile,
    then auto-trigger similar product discovery.

    Opens its own DB session — matches the pattern used by all other pipeline
    background tasks (motivation_service, ocean_service, matching_service).

    Triggered by: motivation_service.generate_motivations_background()
    Triggers:     dispatch("similar_products", product_id)
    """
    _log = f"[PRODUCT_OCEAN pid={product_id[:8]}]"
    logger.info("%s START", _log)

    async with AsyncSessionLocal() as db:
        product: Product | None = await db.get(Product, UUID(product_id))
        if not product:
            logger.error("%s product not found in DB", _log)
            return

        # Run from any post-motivation status, including re-runs and failed states.
        allowed_statuses = {
            ProductStatus.motivations_generated,
            ProductStatus.product_ocean_ready,
            ProductStatus.similar_products_found,
            ProductStatus.failed,
        }
        if product.status not in allowed_statuses:
            logger.info(
                "%s SKIP — status=%s is not ready for product OCEAN derivation",
                _log, product.status,
            )
            return

        try:
            ocean_data = await _compute_product_ocean(db, product.id, _log)

            if ocean_data is None:
                # No profiles available — mark failed so the dashboard shows a clear error
                product.status = ProductStatus.failed
                product.error_message = (
                    "Product OCEAN derivation failed: no motivation OCEAN profiles found. "
                    "Re-run motivation generation first."
                )
                await db.commit()
                logger.error("%s FAILED — no motivation OCEAN profiles available", _log)
                return

            await upsert_product_ocean(
                db,
                product_id=product.id,
                openness=ocean_data["openness"],
                conscientiousness=ocean_data["conscientiousness"],
                extraversion=ocean_data["extraversion"],
                agreeableness=ocean_data["agreeableness"],
                neuroticism=ocean_data["neuroticism"],
                confidence=ocean_data["confidence"],
                component_count=ocean_data["component_count"],
            )

            product.status = ProductStatus.product_ocean_ready
            product.pipeline_step = 3
            product.error_message = None
            await db.commit()

            logger.info(
                "%s DONE — product OCEAN ready (pipeline_step=3)", _log
            )

            # ── Auto-trigger similar product discovery ────────────────────────
            from app.workers.dispatch import dispatch
            dispatch("similar_products", product_id)
            logger.info("%s dispatched 'similar_products'", _log)

        except Exception as exc:
            tb = traceback.format_exc()
            logger.exception("%s FAILED: %s", _log, exc)
            product.status = ProductStatus.failed
            product.error_message = f"{type(exc).__name__}: {exc}\n{tb}"[:1000]
            await db.commit()
