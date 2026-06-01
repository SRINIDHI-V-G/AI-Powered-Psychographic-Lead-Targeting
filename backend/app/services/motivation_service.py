import logging
from uuid import UUID

from app.database import AsyncSessionLocal
from app.models.product import Product, ProductStatus
from app.crud.motivation import (
    create_motivation_category,
    create_ocean_profile,
    delete_motivations_by_product,
)
from app.ml.llm_client import OllamaClient
from app.ml.motivation_prompter import (
    SYSTEM_PROMPT,
    build_motivation_prompt,
    parse_motivation_response,
)

logger = logging.getLogger(__name__)


async def generate_motivations_background(product_id: str) -> None:
    """
    FastAPI BackgroundTask — runs after the POST /products response is sent.
    Opens its own DB session because the request session is already closed.
    """
    async with AsyncSessionLocal() as db:
        product = await db.get(Product, UUID(product_id))
        if not product:
            logger.error("generate_motivations: product %s not found", product_id)
            return

        if product.status != ProductStatus.pending:
            logger.info(
                "generate_motivations: product %s is %s, skipping",
                product_id,
                product.status,
            )
            return

        # ── Step 1: mark as analyzing ─────────────────────────────────────────
        product.status = ProductStatus.analyzing
        product.pipeline_step = 1
        product.error_message = None
        await db.commit()

        try:
            # ── Step 2: delete any stale motivations from a prior run ─────────
            await delete_motivations_by_product(db, product.id)

            # ── Step 3: call Ollama ───────────────────────────────────────────
            logger.info("generate_motivations: calling Ollama for product %s", product_id)
            client = OllamaClient()
            prompt = build_motivation_prompt(
                {
                    "name": product.name,
                    "category": product.category,
                    "price_range": product.price_range.value,
                    "description": product.description,
                }
            )
            response_text = await client.generate(prompt=prompt, system=SYSTEM_PROMPT)
            logger.info("generate_motivations: Ollama responded for product %s", product_id)

            # ── Step 4: parse ─────────────────────────────────────────────────
            categories = parse_motivation_response(response_text)
            if not categories:
                raise ValueError(
                    "Could not parse motivation categories from Ollama response. "
                    f"First 300 chars: {response_text[:300]}"
                )

            # ── Step 5: persist categories + OCEAN profiles ───────────────────
            for i, cat in enumerate(categories):
                mc = await create_motivation_category(
                    db,
                    product_id=product.id,
                    name=cat["name"],
                    description=cat["description"],
                    sort_order=i,
                )
                await create_ocean_profile(
                    db,
                    motivation_category_id=mc.id,
                    ocean_data={
                        **cat["ocean"],
                        "interest_tags": cat["interest_tags"],
                        "search_keywords": cat["search_keywords"],
                        "hashtags": cat["hashtags"],
                    },
                )

            # ── Step 6: mark as done ──────────────────────────────────────────
            product.status = ProductStatus.motivations_generated
            product.pipeline_step = 2
            await db.commit()
            logger.info(
                "generate_motivations: done for product %s (%d categories)",
                product_id,
                len(categories),
            )

        except Exception as exc:
            logger.error(
                "generate_motivations: failed for product %s — %s", product_id, exc
            )
            product.status = ProductStatus.failed
            product.error_message = str(exc)[:500]
            await db.commit()
