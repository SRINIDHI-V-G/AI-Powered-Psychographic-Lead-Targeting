"""Celery tasks: handle discovery pipeline."""
from __future__ import annotations

import asyncio
import logging

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="app.workers.tasks.handle_tasks.run_handle_task",
    queue="handles",
    max_retries=2,
    default_retry_delay=30,
    acks_late=True,
)
def run_handle_task(self, product_id: str) -> dict:
    """Run handle discovery for all matched users of a product."""
    from app.services.handle_service import generate_handles_background

    try:
        asyncio.run(generate_handles_background(product_id))
        return {"status": "ok", "product_id": product_id}
    except Exception as exc:
        logger.error("run_handle_task failed for %s: %s", product_id[:8], exc)
        raise self.retry(exc=exc)
