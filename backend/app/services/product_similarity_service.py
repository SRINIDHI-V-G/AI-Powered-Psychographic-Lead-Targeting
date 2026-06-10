"""
Similar product discovery service.

Calls the LLM once with the product's context and OCEAN profile, receives a list
of candidate similar products (each with its own OCEAN profile), filters them by
cosine similarity to the source product's OCEAN vector, and persists the top N.

The persisted discovery_keywords from each SimilarProduct row are later picked up
by discovery_service to expand the keyword search during user discovery.

Pipeline position:
  Triggered automatically by product_ocean_service after product_ocean_ready.
  On success, advances product status to similar_products_found.
  Discovery is user-triggered after this step (POST /products/{id}/discovery/start).

Fallback behaviour (matches motivation_service pattern):
  USE_MOCK_LLM=True             → skip Ollama, use category-based fallback products.
  Ollama fails + FALLBACK_TO_MOCK_ON_ERROR=True → use fallback products.
  Ollama fails + FALLBACK_TO_MOCK_ON_ERROR=False → mark product as failed.
"""
from __future__ import annotations

import logging
import traceback
from uuid import UUID

from app.config import settings
from app.crud.product_ocean import get_product_ocean
from app.crud.similar_products import replace_similar_products
from app.database import AsyncSessionLocal
from app.ml.llm_client import get_llm_client
from app.ml.similarity.product_similarity import (
    SIMILAR_PRODUCTS_SYSTEM_PROMPT,
    build_similar_products_prompt,
    cosine_ocean_similarity,
    parse_similar_products_response,
)
from app.models.product import Product, ProductStatus

logger = logging.getLogger(__name__)

# 8 candidates × ~130 tokens each + JSON overhead ≈ 1040; 1100 gives safe headroom
_NUM_PREDICT = 1100
_NUM_CTX = 1024


# ── Fallback similar products (category-keyed) ────────────────────────────────
# Used when USE_MOCK_LLM=True or Ollama fails + FALLBACK_TO_MOCK_ON_ERROR=True.
# Each entry is a dict ready to be passed to replace_similar_products().
# similarity_score is set to a conservative 0.72 — clearly mock, not computed.

_FALLBACK_SIMILAR_PRODUCTS: dict[str, list[dict]] = {
    "electronics": [
        {
            "similar_product_name": "Laptop",
            "similar_product_category": "electronics",
            "similar_product_description": "Buyers share a high-information-seeking mindset and premium quality expectations.",
            "openness": 80.0, "conscientiousness": 72.0, "extraversion": 52.0,
            "agreeableness": 55.0, "neuroticism": 28.0,
            "discovery_keywords": ["best laptop review", "laptop buying guide", "ultrabook 2024"],
        },
        {
            "similar_product_name": "Smartwatch",
            "similar_product_category": "wearables",
            "similar_product_description": "Buyers value productivity and seamless connectivity with premium devices.",
            "openness": 75.0, "conscientiousness": 78.0, "extraversion": 58.0,
            "agreeableness": 58.0, "neuroticism": 25.0,
            "discovery_keywords": ["best smartwatch", "smartwatch comparison", "wearable tech review"],
        },
        {
            "similar_product_name": "Wireless Earbuds",
            "similar_product_category": "audio",
            "similar_product_description": "Buyers prioritise immersive experiences and modern tech aesthetics.",
            "openness": 78.0, "conscientiousness": 65.0, "extraversion": 60.0,
            "agreeableness": 60.0, "neuroticism": 30.0,
            "discovery_keywords": ["best wireless earbuds", "earbuds review", "true wireless audio"],
        },
    ],
    "fitness": [
        {
            "similar_product_name": "Fitness Tracker",
            "similar_product_category": "wearables",
            "similar_product_description": "Buyers are disciplined and goal-oriented, tracking performance data obsessively.",
            "openness": 65.0, "conscientiousness": 85.0, "extraversion": 62.0,
            "agreeableness": 60.0, "neuroticism": 22.0,
            "discovery_keywords": ["fitness tracker review", "best fitness band", "activity tracker 2024"],
        },
        {
            "similar_product_name": "Protein Supplement",
            "similar_product_category": "nutrition",
            "similar_product_description": "Buyers share the same high-conscientiousness, health-optimisation mindset.",
            "openness": 60.0, "conscientiousness": 88.0, "extraversion": 60.0,
            "agreeableness": 58.0, "neuroticism": 20.0,
            "discovery_keywords": ["best protein powder", "whey protein review", "gym nutrition guide"],
        },
        {
            "similar_product_name": "Yoga Mat",
            "similar_product_category": "fitness accessories",
            "similar_product_description": "Buyers value mindful physical practice and wellness-oriented lifestyles.",
            "openness": 72.0, "conscientiousness": 75.0, "extraversion": 50.0,
            "agreeableness": 70.0, "neuroticism": 30.0,
            "discovery_keywords": ["best yoga mat", "yoga accessories review", "home workout equipment"],
        },
    ],
    "fashion": [
        {
            "similar_product_name": "Premium Watch",
            "similar_product_category": "accessories",
            "similar_product_description": "Buyers signal status and craftsmanship appreciation through luxury accessories.",
            "openness": 72.0, "conscientiousness": 68.0, "extraversion": 72.0,
            "agreeableness": 50.0, "neuroticism": 28.0,
            "discovery_keywords": ["luxury watch review", "premium watch brands", "watch buying guide"],
        },
        {
            "similar_product_name": "Designer Sunglasses",
            "similar_product_category": "accessories",
            "similar_product_description": "Buyers care deeply about personal brand and curated aesthetic presentation.",
            "openness": 78.0, "conscientiousness": 60.0, "extraversion": 75.0,
            "agreeableness": 52.0, "neuroticism": 30.0,
            "discovery_keywords": ["designer sunglasses review", "luxury eyewear", "fashion accessories"],
        },
        {
            "similar_product_name": "Leather Wallet",
            "similar_product_category": "accessories",
            "similar_product_description": "Buyers appreciate quality craftsmanship and understated premium signals.",
            "openness": 65.0, "conscientiousness": 74.0, "extraversion": 58.0,
            "agreeableness": 60.0, "neuroticism": 25.0,
            "discovery_keywords": ["best leather wallet", "premium wallet review", "minimalist wallet"],
        },
    ],
    "food": [
        {
            "similar_product_name": "Specialty Coffee",
            "similar_product_category": "beverages",
            "similar_product_description": "Buyers are curious explorers who appreciate craft and quality in everyday experiences.",
            "openness": 85.0, "conscientiousness": 68.0, "extraversion": 60.0,
            "agreeableness": 65.0, "neuroticism": 28.0,
            "discovery_keywords": ["specialty coffee review", "best coffee beans", "pour over coffee"],
        },
        {
            "similar_product_name": "Organic Snacks",
            "similar_product_category": "health food",
            "similar_product_description": "Buyers are health-conscious and value ingredient transparency.",
            "openness": 72.0, "conscientiousness": 80.0, "extraversion": 52.0,
            "agreeableness": 68.0, "neuroticism": 25.0,
            "discovery_keywords": ["organic snacks review", "healthy snack alternatives", "clean eating"],
        },
        {
            "similar_product_name": "Cooking Kit",
            "similar_product_category": "kitchen",
            "similar_product_description": "Buyers find satisfaction in mastery and enjoy the creative act of cooking.",
            "openness": 80.0, "conscientiousness": 74.0, "extraversion": 55.0,
            "agreeableness": 68.0, "neuroticism": 26.0,
            "discovery_keywords": ["cooking kit review", "home chef tools", "meal prep equipment"],
        },
    ],
}

_FALLBACK_DEFAULT: list[dict] = [
    {
        "similar_product_name": "Premium Alternative A",
        "similar_product_category": "general",
        "similar_product_description": "Buyers share quality-focused purchasing behaviour and research-driven decision making.",
        "openness": 72.0, "conscientiousness": 74.0, "extraversion": 55.0,
        "agreeableness": 60.0, "neuroticism": 28.0,
        "discovery_keywords": ["product review", "best alternatives", "buying guide"],
    },
    {
        "similar_product_name": "Premium Alternative B",
        "similar_product_category": "general",
        "similar_product_description": "Buyers value brand reputation and long-term ownership satisfaction.",
        "openness": 68.0, "conscientiousness": 78.0, "extraversion": 50.0,
        "agreeableness": 62.0, "neuroticism": 26.0,
        "discovery_keywords": ["product comparison", "worth buying", "honest review"],
    },
    {
        "similar_product_name": "Premium Alternative C",
        "similar_product_category": "general",
        "similar_product_description": "Buyers are early adopters who enjoy sharing discoveries with their social circle.",
        "openness": 82.0, "conscientiousness": 62.0, "extraversion": 68.0,
        "agreeableness": 58.0, "neuroticism": 30.0,
        "discovery_keywords": ["new product launch", "trending products", "must have products"],
    },
]


def _get_fallback_products(category: str) -> list[dict]:
    """Return category-matched fallback similar products with mock similarity scores."""
    cat_lower = (category or "").lower()

    # Find matching category key
    for key in _FALLBACK_SIMILAR_PRODUCTS:
        if key in cat_lower or cat_lower in key:
            items = _FALLBACK_SIMILAR_PRODUCTS[key]
            break
    else:
        items = _FALLBACK_DEFAULT

    # Attach a mock similarity score so CRUD layer has a valid value
    return [
        {**item, "similarity_score": 0.72}
        for item in items[: settings.SIMILAR_PRODUCTS_MAX]
    ]


# ── LLM call with retry ───────────────────────────────────────────────────────

async def _call_llm(prompt: str, _log: str) -> list[dict] | None:
    """
    Call Ollama with the similar products prompt. Retries once at higher
    temperature if the first attempt returns unparseable output.
    Returns a validated list of candidate dicts, or None on complete failure.
    """
    client = get_llm_client()
    # Use the dedicated timeout for this pipeline step
    client.timeout = settings.SIMILAR_PRODUCTS_LLM_TIMEOUT

    logger.info(
        "%s calling Ollama at %s model=%s timeout=%.0fs",
        _log, settings.OLLAMA_BASE_URL, settings.OLLAMA_MODEL,
        settings.SIMILAR_PRODUCTS_LLM_TIMEOUT,
    )

    # ── First attempt ─────────────────────────────────────────────────────────
    raw: str | None = None
    try:
        raw = await client.generate(
            prompt=prompt,
            system=SIMILAR_PRODUCTS_SYSTEM_PROMPT,
            temperature=0.3,
            num_predict=_NUM_PREDICT,
            num_ctx=_NUM_CTX,
        )
        logger.info("%s Ollama responded (%d chars)", _log, len(raw))
        logger.debug("%s RAW (first 600):\n%s", _log, raw[:600])

        candidates = parse_similar_products_response(raw)
        if candidates:
            return candidates
        logger.warning("%s parse returned empty list — retrying", _log)

    except (ConnectionError, TimeoutError, RuntimeError) as exc:
        logger.warning("%s Ollama error on attempt 1: %s", _log, exc)

    # ── Second attempt (higher temperature) ───────────────────────────────────
    try:
        if raw is None:
            raise RuntimeError("Skipping retry — Ollama was unreachable on first attempt")
        raw2 = await client.generate(
            prompt=prompt,
            system=SIMILAR_PRODUCTS_SYSTEM_PROMPT,
            temperature=0.6,
            num_predict=_NUM_PREDICT,
            num_ctx=_NUM_CTX,
        )
        logger.info("%s retry responded (%d chars)", _log, len(raw2))
        candidates = parse_similar_products_response(raw2)
        if candidates:
            return candidates
        logger.warning("%s retry parse also returned empty list", _log)

    except (ConnectionError, TimeoutError, RuntimeError) as exc:
        logger.warning("%s Ollama error on attempt 2: %s", _log, exc)

    return None


# ── Scoring, filtering, and sorting ──────────────────────────────────────────

def _score_and_filter(
    candidates: list[dict],
    product_ocean: dict[str, float],
    _log: str,
) -> list[dict]:
    """
    Attach similarity_score to each candidate, filter below threshold,
    sort descending, and return the top SIMILAR_PRODUCTS_MAX items.
    """
    threshold = settings.SIMILAR_PRODUCT_SIMILARITY_THRESHOLD

    scored: list[tuple[float, dict]] = []
    for item in candidates:
        candidate_ocean = {
            "openness":          item.get("openness", 50.0),
            "conscientiousness": item.get("conscientiousness", 50.0),
            "extraversion":      item.get("extraversion", 50.0),
            "agreeableness":     item.get("agreeableness", 50.0),
            "neuroticism":       item.get("neuroticism", 50.0),
        }
        score = cosine_ocean_similarity(product_ocean, candidate_ocean)
        if score >= threshold:
            scored.append((score, {**item, "similarity_score": round(score, 4)}))

    scored.sort(key=lambda t: t[0], reverse=True)
    top = [item for _, item in scored[: settings.SIMILAR_PRODUCTS_MAX]]

    logger.info(
        "%s %d/%d candidates passed threshold=%.2f — keeping top %d",
        _log, len(scored), len(candidates), threshold, len(top),
    )
    return top


# ── Background task entry point ───────────────────────────────────────────────

async def generate_similar_products_background(product_id: str) -> None:
    """
    Background task: generate and persist similar products for a product.

    Opens its own DB session — matches the pattern used by all pipeline services.

    Triggered by: product_ocean_service.generate_product_ocean_background()
    Next step:    User manually triggers discovery via POST /products/{id}/discovery/start
    """
    _log = f"[SIMILAR_PRODUCTS pid={product_id[:8]}]"
    logger.info("%s START", _log)

    async with AsyncSessionLocal() as db:
        product: Product | None = await db.get(Product, UUID(product_id))
        if not product:
            logger.error("%s product not found in DB", _log)
            return

        # Run from any post-product-ocean status, including failed states.
        allowed_statuses = {
            ProductStatus.product_ocean_ready,
            ProductStatus.similar_products_found,
            ProductStatus.failed,
        }
        if product.status not in allowed_statuses:
            logger.info(
                "%s SKIP — status=%s (expected product_ocean_ready or similar_products_found)",
                _log, product.status,
            )
            return

        try:
            # ── 1. Load product OCEAN profile ─────────────────────────────────
            profile = await get_product_ocean(db, product.id)
            if profile is None:
                logger.error(
                    "%s no product OCEAN profile found — run product_ocean step first", _log
                )
                product.status = ProductStatus.failed
                product.error_message = (
                    "Similar product discovery failed: product OCEAN profile not found. "
                    "Re-run product OCEAN generation first."
                )
                await db.commit()
                return

            product_ocean_dict: dict[str, float] = {
                "openness":          profile.openness,
                "conscientiousness": profile.conscientiousness,
                "extraversion":      profile.extraversion,
                "agreeableness":     profile.agreeableness,
                "neuroticism":       profile.neuroticism,
            }

            # ── 2. Choose path: mock or real LLM ──────────────────────────────
            if settings.USE_MOCK_LLM:
                logger.info(
                    "%s USE_MOCK_LLM=True — using fallback similar products", _log
                )
                final_items = _get_fallback_products(product.category)
                source = "mock (USE_MOCK_LLM)"

            else:
                # ── 3. Build prompt ───────────────────────────────────────────
                prompt = build_similar_products_prompt(
                    product={
                        "name":        product.name,
                        "category":    product.category,
                        "description": product.description,
                        "price_range": product.price_range.value if product.price_range else "",
                        "keywords":    list(product.keywords or []),
                    },
                    product_ocean=product_ocean_dict,
                )

                # ── 4. Call LLM ───────────────────────────────────────────────
                candidates = await _call_llm(prompt, _log)

                if candidates:
                    # ── 5. Score, filter, and sort ────────────────────────────
                    final_items = _score_and_filter(candidates, product_ocean_dict, _log)
                    source = "ollama"

                    if not final_items:
                        # All candidates were below the similarity threshold
                        logger.warning(
                            "%s no candidates passed the similarity threshold (%.2f) "
                            "— using fallback",
                            _log, settings.SIMILAR_PRODUCT_SIMILARITY_THRESHOLD,
                        )
                        if settings.FALLBACK_TO_MOCK_ON_ERROR:
                            final_items = _get_fallback_products(product.category)
                            source = "fallback (all below threshold)"
                        else:
                            product.status = ProductStatus.failed
                            product.error_message = (
                                f"Similar product discovery found no candidates above "
                                f"similarity threshold "
                                f"({settings.SIMILAR_PRODUCT_SIMILARITY_THRESHOLD:.2f})."
                            )
                            await db.commit()
                            logger.error("%s FAILED — no candidates above threshold", _log)
                            return

                else:
                    # LLM failed completely
                    if settings.FALLBACK_TO_MOCK_ON_ERROR:
                        logger.warning(
                            "%s LLM failed after 2 attempts — using fallback similar products",
                            _log,
                        )
                        final_items = _get_fallback_products(product.category)
                        source = "fallback (LLM failed)"
                    else:
                        product.status = ProductStatus.failed
                        product.error_message = (
                            "Similar product discovery failed: Ollama returned unparseable "
                            "output after 2 attempts and FALLBACK_TO_MOCK_ON_ERROR is False."
                        )
                        await db.commit()
                        logger.error("%s FAILED — LLM returned unparseable output", _log)
                        return

            # ── 6. Persist ────────────────────────────────────────────────────
            saved = await replace_similar_products(db, product.id, final_items)
            logger.info(
                "%s persisted %d similar products (source=%s)", _log, len(saved), source
            )

            # ── 7. Advance pipeline ───────────────────────────────────────────
            product.status = ProductStatus.similar_products_found
            product.pipeline_step = 4
            product.error_message = None
            if "fallback" in source:
                product.error_message = (
                    f"[INFO] LLM unavailable — used fallback similar products. "
                    f"Reason: {source}"
                )
            await db.commit()

            logger.info(
                "%s DONE — %d similar products ready, pipeline_step=4", _log, len(saved)
            )

            # ── 8. Auto-trigger discovery ─────────────────────────────────────
            # Await directly (fast: just creates DB job + schedules background task)
            from app.services.discovery_service import auto_start_discovery
            await auto_start_discovery(product_id)
            logger.info("%s auto_start_discovery complete", _log)

        except Exception as exc:
            tb = traceback.format_exc()
            logger.exception("%s FAILED: %s", _log, exc)
            product.status = ProductStatus.failed
            product.error_message = f"{type(exc).__name__}: {exc}\n{tb}"[:1000]
            await db.commit()
