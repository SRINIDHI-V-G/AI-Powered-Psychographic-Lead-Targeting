"""Celery tasks: OCEAN personality scoring."""
from __future__ import annotations

import asyncio
import logging

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="app.workers.tasks.scoring_tasks.run_ocean_scoring_task",
    queue="scoring",
    max_retries=2,
    default_retry_delay=30,
    acks_late=True,
    # Ollama is slow; give each task 30 minutes before hard-killing it.
    soft_time_limit=1800,
    time_limit=1900,
)
def run_ocean_scoring_task(self, product_id: str) -> dict:
    """Score all NLP-processed, unscored users for a product via Llama 3.1."""
    from app.services.ocean_service import start_ocean_background

    try:
        asyncio.run(start_ocean_background(product_id))
        return {"status": "ok", "product_id": product_id}
    except Exception as exc:
        logger.error("run_ocean_scoring_task failed for %s: %s", product_id[:8], exc)
        raise self.retry(exc=exc)
