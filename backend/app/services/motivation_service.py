import traceback
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
    print(f"\n[MOTIVATION] ── START ── product_id={product_id}", flush=True)

    async with AsyncSessionLocal() as db:
        product = await db.get(Product, UUID(product_id))
        if not product:
            print(f"[MOTIVATION] ERROR: product {product_id} not found in DB", flush=True)
            return

        if product.status != ProductStatus.pending:
            print(f"[MOTIVATION] SKIP: product {product_id} status={product.status}, not pending", flush=True)
            return

        # ── Step 1: mark as analyzing ─────────────────────────────────────────
        product.status = ProductStatus.analyzing
        product.pipeline_step = 1
        product.error_message = None
        await db.commit()
        print(f"[MOTIVATION] Step 1 OK: status → analyzing", flush=True)

        try:
            # ── Step 2: clear stale motivations ──────────────────────────────
            await delete_motivations_by_product(db, product.id)
            print(f"[MOTIVATION] Step 2 OK: stale motivations cleared", flush=True)

            # ── Step 3: build prompt ──────────────────────────────────────────
            prompt = build_motivation_prompt(
                {
                    "name": product.name,
                    "category": product.category,
                    "price_range": product.price_range.value,
                    "description": product.description,
                }
            )
            print(f"[MOTIVATION] Step 3 OK: prompt built ({len(prompt)} chars)", flush=True)

            # ── Step 4: call Ollama ───────────────────────────────────────────
            print(f"[MOTIVATION] Step 4: calling Ollama at {__import__('app.config', fromlist=['settings']).settings.OLLAMA_BASE_URL} model={__import__('app.config', fromlist=['settings']).settings.OLLAMA_MODEL}", flush=True)
            client = OllamaClient()
            response_text = await client.generate(prompt=prompt, system=SYSTEM_PROMPT)
            print(f"[MOTIVATION] Step 4 OK: Ollama responded ({len(response_text)} chars)", flush=True)
            print(f"[MOTIVATION] RAW RESPONSE (first 800 chars):\n{response_text[:800]}", flush=True)

            # ── Step 5: parse ─────────────────────────────────────────────────
            categories = parse_motivation_response(response_text)
            print(f"[MOTIVATION] Step 5: parsed categories = {len(categories) if categories else 0}", flush=True)

            if not categories:
                raise ValueError(
                    f"parse_motivation_response returned None.\n"
                    f"Full Ollama response ({len(response_text)} chars):\n{response_text}"
                )

            # ── Step 6: persist ───────────────────────────────────────────────
            print(f"[MOTIVATION] Step 6: persisting {len(categories)} categories...", flush=True)
            for i, cat in enumerate(categories):
                print(f"[MOTIVATION]   [{i}] name={cat['name']!r}", flush=True)
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
            print(f"[MOTIVATION] Step 6 OK: all categories persisted", flush=True)

            # ── Step 7: mark done ─────────────────────────────────────────────
            product.status = ProductStatus.motivations_generated
            product.pipeline_step = 2
            await db.commit()
            print(f"[MOTIVATION] ── DONE ── product_id={product_id} ({len(categories)} categories)\n", flush=True)

        except Exception as exc:
            full_tb = traceback.format_exc()
            print(f"[MOTIVATION] ── FAILED ── product_id={product_id}", flush=True)
            print(f"[MOTIVATION] EXCEPTION TYPE : {type(exc).__name__}", flush=True)
            print(f"[MOTIVATION] EXCEPTION MSG  : {exc}", flush=True)
            print(f"[MOTIVATION] FULL TRACEBACK :\n{full_tb}", flush=True)
            logger.exception("generate_motivations failed for product %s", product_id)

            product.status = ProductStatus.failed
            product.error_message = (
                f"{type(exc).__name__}: {exc}\n\nTraceback:\n{full_tb}"
            )[:1000]
            await db.commit()
