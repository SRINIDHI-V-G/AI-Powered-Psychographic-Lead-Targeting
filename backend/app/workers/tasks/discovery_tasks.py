"""Celery tasks: user discovery + content collection."""
from __future__ import annotations

import asyncio
import logging

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="app.workers.tasks.discovery_tasks.run_discovery_task",
    queue="discovery",
    max_retries=2,
    default_retry_delay=60,
    acks_late=True,
    soft_time_limit=3600,
    time_limit=3700,
)
def run_discovery_task(self, product_id: str, job_id: str) -> dict:
    """Run the full discovery pipeline for a product and job."""
    from app.services.discovery_service import start_discovery_background

    try:
        asyncio.run(start_discovery_background(product_id, job_id))
        return {"status": "ok", "product_id": product_id, "job_id": job_id}
    except Exception as exc:
        logger.error("run_discovery_task failed for %s: %s", product_id[:8], exc)
        raise self.retry(exc=exc)
