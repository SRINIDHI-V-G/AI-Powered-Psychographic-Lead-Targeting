"""
Discovery service — business logic layer for discovery pipeline.

Coordinates between the HTTP layer (router) and the ML layer (orchestrator).
All DB sessions are opened here; the orchestrator receives an open session.
"""
from __future__ import annotations

import logging
from uuid import UUID

from app.config import settings
from app.crud.discovery import create_discovery_job
from app.database import AsyncSessionLocal
from app.ml.discovery.orchestrator import DiscoveryOrchestrator
from app.models.product import ProductStatus

logger = logging.getLogger(__name__)


async def start_discovery_background(
    product_id: str,
    job_id: str,
) -> None:
    """
    Background task entry point.
    Opens its own DB session (pattern: same as generate_motivations_background).
    """
    _log = f"[DISCOVERY svc job={job_id[:8]}]"
    logger.info("%s background task started", _log)

    async with AsyncSessionLocal() as db:
        orchestrator = DiscoveryOrchestrator()
        await orchestrator.run(UUID(job_id), db)

    logger.info("%s background task complete", _log)
