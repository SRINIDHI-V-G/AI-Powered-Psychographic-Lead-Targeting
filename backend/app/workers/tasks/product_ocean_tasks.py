"""
Celery task: product OCEAN aggregation.

Thin wrapper around generate_product_ocean_background().
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
    name="app.workers.tasks.product_ocean_tasks.run_product_ocean_task",
    queue="pipeline",
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
)
def run_product_ocean_task(self, product_id: str) -> dict:
    """
    Derive and persist the product-level OCEAN vector from motivation profiles.

    Parameters
    ----------
    product_id : str  UUID of the product
    """
    from app.services.product_ocean_service import generate_product_ocean_background

    try:
        asyncio.run(generate_product_ocean_background(product_id))
        return {"status": "ok", "product_id": product_id}
    except Exception as exc:
        logger.error("run_product_ocean_task failed for %s: %s", product_id[:8], exc)
        raise self.retry(exc=exc)
