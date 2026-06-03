"""Celery tasks: matching engine + lead ranking."""
from __future__ import annotations

import asyncio
import logging

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="app.workers.tasks.matching_tasks.run_matching_task",
    queue="matching",
    max_retries=2,
    default_retry_delay=30,
    acks_late=True,
)
def run_matching_task(self, product_id: str) -> dict:
    """Run matching engine and lead ranking for all OCEAN-scored users."""
    from app.services.matching_service import start_matching_background

    try:
        asyncio.run(start_matching_background(product_id))
        return {"status": "ok", "product_id": product_id}
    except Exception as exc:
        logger.error("run_matching_task failed for %s: %s", product_id[:8], exc)
        raise self.retry(exc=exc)
