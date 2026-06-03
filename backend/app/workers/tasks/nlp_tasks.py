"""Celery tasks: NLP batch processing."""
from __future__ import annotations

import asyncio
import logging

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="app.workers.tasks.nlp_tasks.run_nlp_task",
    queue="nlp",
    max_retries=2,
    default_retry_delay=30,
    acks_late=True,
)
def run_nlp_task(self, product_id: str) -> dict:
    """Run the full NLP pipeline for all unprocessed users of a product."""
    from app.services.nlp_service import start_nlp_background

    try:
        asyncio.run(start_nlp_background(product_id))
        return {"status": "ok", "product_id": product_id}
    except Exception as exc:
        logger.error("run_nlp_task failed for %s: %s", product_id[:8], exc)
        raise self.retry(exc=exc)
