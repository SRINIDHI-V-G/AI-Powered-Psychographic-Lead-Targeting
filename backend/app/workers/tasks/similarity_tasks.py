"""
Celery task: similar product discovery.

Thin wrapper around generate_similar_products_background().
All business logic lives in the service — this module only handles
Celery registration, retry policy, and asyncio.run() bridging.
"""
from __future__ import annotations

import asyncio
import logging

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="app.workers.tasks.similarity_tasks.run_similarity_task",
    queue="pipeline",
    max_retries=3,
    default_retry_delay=45,   # longer back-off: LLM call is heavier than aggregation
    acks_late=True,
)
def run_similarity_task(self, product_id: str) -> dict:
    """
    Generate, score, and persist similar products for a product using OCEAN similarity.

    Parameters
    ----------
    product_id : str  UUID of the product
    """
    from app.services.product_similarity_service import generate_similar_products_background

    try:
        asyncio.run(generate_similar_products_background(product_id))
        return {"status": "ok", "product_id": product_id}
    except Exception as exc:
        logger.error("run_similarity_task failed for %s: %s", product_id[:8], exc)
        raise self.retry(exc=exc)
