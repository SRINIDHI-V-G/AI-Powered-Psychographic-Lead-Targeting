"""
Motivation generation service.

Execution model
---------------
Called as a FastAPI BackgroundTask (fire-and-forget, async).
No Celery required for Phase A — the background task runs inside the
Uvicorn event loop on the same process.

Paths
-----
1. USE_MOCK_LLM=True        → skip Ollama, store fallback categories instantly.
2. USE_MOCK_LLM=False       → call Ollama, parse JSON, persist real categories.
3. Ollama fails             → if FALLBACK_TO_MOCK_ON_ERROR=True, fall back to (1).
                              Otherwise mark product as "failed" with traceback.
"""
from __future__ import annotations

import logging
import traceback
from uuid import UUID

from app.config import settings
from app.crud.motivation import (
    create_motivation_category,
    create_ocean_profile,
    delete_motivations_by_product,
)
from app.database import AsyncSessionLocal
from app.ml.llm_client import OllamaClient
from app.ml.motivation_prompter import (
    SYSTEM_PROMPT,
    build_motivation_prompt,
    parse_motivation_response,
)
from app.models.product import Product, ProductStatus

logger = logging.getLogger(__name__)

# ── Fallback category templates ───────────────────────────────────────────────
# Used when USE_MOCK_LLM=True OR when Ollama fails and FALLBACK_TO_MOCK_ON_ERROR=True.
# Each dict is a jinja-light template — {product_name} and {category} are filled
# in at runtime so the categories feel product-specific, not generic.

_FALLBACK_TEMPLATES: list[dict] = [
    {
        "name": "Aesthetic & Design Appeal",
        "description": (
            "These buyers choose {product_name} primarily for its visual design and how it "
            "elevates their space or style. They treat this {category} as a statement piece."
        ),
        "ocean": {"openness": 8.5, "conscientiousness": 6.0, "extraversion": 6.5,
                  "agreeableness": 6.0, "emotional_stability": 6.5},
        "interest_tags": ["design", "aesthetics", "lifestyle", "interior", "style"],
        "search_keywords": ["design inspiration", "aesthetic", "style guide", "premium look"],
        "hashtags": ["#design", "#aesthetic", "#lifestyle", "#style"],
    },
    {
        "name": "Luxury & Status Signaling",
        "description": (
            "Motivated by prestige, these buyers see {product_name} as a way to signal "
            "success and refined taste. Brand perception and exclusivity matter most."
        ),
        "ocean": {"openness": 7.5, "conscientiousness": 5.5, "extraversion": 8.0,
                  "agreeableness": 4.5, "emotional_stability": 7.0},
        "interest_tags": ["luxury", "premium brands", "status", "high-end living", "fashion"],
        "search_keywords": ["luxury {category}", "premium quality", "top brand", "exclusive"],
        "hashtags": ["#luxury", "#premium", "#highend", "#exclusive"],
    },
    {
        "name": "Practical Value & Functionality",
        "description": (
            "These buyers prioritise utility and return on investment. They research "
            "{product_name} thoroughly, comparing specs and reviews before committing."
        ),
        "ocean": {"openness": 5.5, "conscientiousness": 8.5, "extraversion": 4.0,
                  "agreeableness": 6.5, "emotional_stability": 7.5},
        "interest_tags": ["reviews", "value for money", "practical", "comparison", "quality"],
        "search_keywords": ["best {category} review", "value", "comparison", "worth buying"],
        "hashtags": ["#bestvalue", "#review", "#practical", "#qualityfirst"],
    },
    {
        "name": "Long-Term Investment Mindset",
        "description": (
            "Research-driven purchasers who view {product_name} as a long-term investment. "
            "They scrutinise materials, warranty, and craftsmanship above all else."
        ),
        "ocean": {"openness": 6.5, "conscientiousness": 9.0, "extraversion": 4.0,
                  "agreeableness": 6.5, "emotional_stability": 8.0},
        "interest_tags": ["craftsmanship", "durability", "investment", "quality", "warranty"],
        "search_keywords": ["durable {category}", "long lasting", "best quality", "warranty"],
        "hashtags": ["#quality", "#craftsmanship", "#investment", "#durable"],
    },
    {
        "name": "Trend & Community Driven",
        "description": (
            "Early adopters and community members who buy {product_name} to stay current "
            "and share their experience. Social proof and peer recommendations drive them."
        ),
        "ocean": {"openness": 8.0, "conscientiousness": 5.5, "extraversion": 8.5,
                  "agreeableness": 7.5, "emotional_stability": 6.0},
        "interest_tags": ["trends", "community", "social media", "reviews", "sharing"],
        "search_keywords": ["trending {category}", "popular", "community favourite", "unboxing"],
        "hashtags": ["#trending", "#community", "#new", "#musthave"],
    },
]


def _build_fallback_categories(product_name: str, category: str) -> list[dict]:
    """Return 5 product-aware fallback motivation categories."""
    result = []
    for tmpl in _FALLBACK_TEMPLATES:
        result.append({
            "name": tmpl["name"],
            "description": tmpl["description"].format(
                product_name=product_name, category=category
            ),
            "ocean": tmpl["ocean"].copy(),
            "interest_tags": [
                t.format(product_name=product_name, category=category)
                for t in tmpl["interest_tags"]
            ],
            "search_keywords": [
                k.format(product_name=product_name, category=category)
                for k in tmpl["search_keywords"]
            ],
            "hashtags": tmpl["hashtags"][:],
        })
    return result


# ── DB persistence helper ─────────────────────────────────────────────────────

async def _persist_categories(db, product_id: UUID, categories: list[dict]) -> None:
    """Delete existing motivations and write a fresh set to the DB."""
    await delete_motivations_by_product(db, product_id)
    for i, cat in enumerate(categories):
        logger.info("[MOTIVATION] persisting [%d] %r", i, cat["name"])
        mc = await create_motivation_category(
            db,
            product_id=product_id,
            name=cat["name"],
            description=cat["description"],
            sort_order=i,
        )
        await create_ocean_profile(
            db,
            motivation_category_id=mc.id,
            ocean_data={
                **cat["ocean"],
                "interest_tags":   cat["interest_tags"],
                "search_keywords": cat["search_keywords"],
                "hashtags":        cat["hashtags"],
            },
        )
    await db.commit()


def _ensure_five(
    categories: list[dict],
    product_name: str,
    category: str,
) -> list[dict]:
    """
    Guarantee exactly 5 categories.
    If the LLM returned fewer (common), pad with product-aware fallbacks,
    skipping any whose name already appears in the LLM results.
    If the LLM returned more than 5, keep only the first 5.
    """
    if len(categories) == 5:
        return categories
    if len(categories) > 5:
        return categories[:5]
    existing_names = {c["name"].lower() for c in categories}
    fallbacks = _build_fallback_categories(product_name, category)
    for fb in fallbacks:
        if len(categories) >= 5:
            break
        if fb["name"].lower() not in existing_names:
            categories.append(fb)
            existing_names.add(fb["name"].lower())
    return categories


# ── Public entry point ────────────────────────────────────────────────────────

async def generate_motivations_background(
    product_id: str,
    force: bool = False,
) -> None:
    """
    Background task: generate motivation categories for *product_id*.

    Parameters
    ----------
    product_id : str  UUID of the product.
    force      : bool If True, runs even when product.status != pending.
                      Used by the /motivations/regenerate endpoint.
    """
    _log = f"[MOTIVATION pid={product_id[:8]}]"
    logger.info("%s START (force=%s)", _log, force)

    async with AsyncSessionLocal() as db:
        product = await db.get(Product, UUID(product_id))
        if not product:
            logger.error("%s product not found in DB", _log)
            return

        if not force and product.status != ProductStatus.pending:
            logger.info(
                "%s SKIP — status=%s (not pending)", _log, product.status
            )
            return

        # ── 1. Mark as analyzing ──────────────────────────────────────────────
        product.status = ProductStatus.analyzing
        product.pipeline_step = 1
        product.error_message = None
        await db.commit()
        logger.info("%s → analyzing", _log)

        try:
            # ── 2. Choose path: mock or real LLM ─────────────────────────────
            if settings.USE_MOCK_LLM:
                logger.info(
                    "%s USE_MOCK_LLM=True — using fallback categories", _log
                )
                categories = _build_fallback_categories(
                    product.name, product.category
                )
                source = "mock (USE_MOCK_LLM)"
            else:
                categories, source = await _run_llm(
                    product, _log
                )

            # ── 3. Ensure exactly 5, then persist ────────────────────────────
            categories = _ensure_five(categories, product.name, product.category)
            logger.info(
                "%s persisting %d categories (source=%s)", _log, len(categories), source
            )
            await _persist_categories(db, product.id, categories)

            # ── 4. Mark done ──────────────────────────────────────────────────
            product.status = ProductStatus.motivations_generated
            product.pipeline_step = 2
            # Store a note if we fell back so operators can spot it in /products/{id}
            if "fallback" in source:
                product.error_message = (
                    f"[INFO] LLM unavailable — used fallback categories. "
                    f"Reason: {source}"
                )
            else:
                product.error_message = None
            await db.commit()
            logger.info("%s DONE (%d categories, source=%s)", _log, len(categories), source)

            # ── 5. Auto-trigger product OCEAN derivation ──────────────────────
            from app.workers.dispatch import dispatch
            dispatch("product_ocean", product_id)
            logger.info("%s dispatched 'product_ocean'", _log)

        except Exception as exc:
            full_tb = traceback.format_exc()
            logger.exception("%s FAILED — %s", _log, exc)
            product.status = ProductStatus.failed
            product.error_message = (
                f"{type(exc).__name__}: {exc}\n\nTraceback:\n{full_tb}"
            )[:1000]
            await db.commit()


async def _run_llm(product: Product, _log: str) -> tuple[list[dict], str]:
    """
    Call Ollama, parse the response, and return (categories, source_label).

    Falls back to product-aware template categories when:
      - Ollama is unreachable or times out
      - The JSON response cannot be parsed after two attempts
      - FALLBACK_TO_MOCK_ON_ERROR is False → re-raises so the caller marks product failed
    """
    # ── Build prompt ──────────────────────────────────────────────────────────
    prompt = build_motivation_prompt({
        "name":        product.name,
        "category":    product.category,
        "price_range": product.price_range.value,
        "description": product.description,
    })
    logger.info(
        "%s calling Ollama at %s model=%s",
        _log, settings.OLLAMA_BASE_URL, settings.OLLAMA_MODEL,
    )

    client = OllamaClient()

    # ── First attempt ─────────────────────────────────────────────────────────
    try:
        raw = await client.generate(prompt=prompt, system=SYSTEM_PROMPT)
        logger.info("%s Ollama responded (%d chars)", _log, len(raw))
        logger.debug("%s RAW (first 800):\n%s", _log, raw[:800])

        categories = parse_motivation_response(raw)
        if categories:
            return categories, "ollama"

        logger.warning("%s parse returned None — retrying with higher temperature", _log)

    except (ConnectionError, TimeoutError, RuntimeError) as exc:
        logger.warning("%s Ollama error on attempt 1: %s", _log, exc)
        raw = None

    # ── Second attempt (higher temperature, slightly trimmed prompt) ──────────
    try:
        if raw is None:
            raise RuntimeError("Skipping retry — Ollama was unreachable on first attempt")
        raw2 = await client.generate(
            prompt=prompt, system=SYSTEM_PROMPT, temperature=0.6
        )
        logger.info(
            "%s retry responded (%d chars)", _log, len(raw2)
        )
        categories = parse_motivation_response(raw2)
        if categories:
            return categories, "ollama (retry)"

        logger.warning("%s retry parse also returned None", _log)

    except (ConnectionError, TimeoutError, RuntimeError) as exc:
        logger.warning("%s Ollama error on attempt 2: %s", _log, exc)

    # ── Fallback ──────────────────────────────────────────────────────────────
    if settings.FALLBACK_TO_MOCK_ON_ERROR:
        logger.warning(
            "%s FALLBACK_TO_MOCK_ON_ERROR=True — using template categories", _log
        )
        return (
            _build_fallback_categories(product.name, product.category),
            f"fallback (Ollama failed after 2 attempts)",
        )

    raise RuntimeError(
        "Ollama returned unparseable output after 2 attempts and "
        "FALLBACK_TO_MOCK_ON_ERROR is False."
    )
