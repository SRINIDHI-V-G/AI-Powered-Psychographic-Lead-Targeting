"""
Celery tasks: motivation generation pipeline.

Each task is a thin synchronous wrapper that:
  1. Runs the existing async service function via asyncio.run()
  2. Handles retries with exponential back-off
  3. Preserves all error/status behaviour already in the service

The service functions are the source of truth — tasks never contain business logic.
"""
from __future__ import annotations

import asyncio
import logging

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="app.workers.tasks.product_tasks.generate_motivations_task",
    queue="pipeline",
    max_retries=3,
    default_retry_delay=60,     # 60-second back-off on Ollama timeout
    acks_late=True,
)
def generate_motivations_task(self, product_id: str, force: bool = False) -> dict:
    """
    Generate motivation categories for a product using Llama 3.1.

    Parameters
    ----------
    product_id : str UUID of the product
    force      : bypass the pending-status guard (used by restart)
    """
    from app.services.motivation_service import generate_motivations_background

    try:
        asyncio.run(generate_motivations_background(product_id, force))
        return {"status": "ok", "product_id": product_id}
    except Exception as exc:
        logger.error("generate_motivations_task failed for %s: %s", product_id[:8], exc)
        raise self.retry(exc=exc)
