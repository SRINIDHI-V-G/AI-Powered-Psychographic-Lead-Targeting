"""
Discovery service — business logic layer for discovery pipeline.

Coordinates between the HTTP layer (router) and the ML layer (orchestrator).
All DB sessions are opened here; the orchestrator receives an open session.

Similar product keyword injection:
  Before handing off to the orchestrator, this service loads any active
  SimilarProduct rows for the product and writes their discovery_keywords
  into job.search_config["similar_products"]. The orchestrator reads that
  config key and merges the keywords into its unified search set.
"""
from __future__ import annotations

import logging
from uuid import UUID

from app.crud.similar_products import get_similar_products
from app.database import AsyncSessionLocal
from app.ml.discovery.orchestrator import DiscoveryOrchestrator

logger = logging.getLogger(__name__)


async def start_discovery_background(
    product_id: str,
    job_id: str,
) -> None:
    """
    Background task entry point.
    Opens its own DB session (pattern: same as generate_motivations_background).

    Injects similar product keywords into the job's search_config before
    the orchestrator runs, so providers search for discussions about both
    the primary product and all active similar products.
    """
    _log = f"[DISCOVERY svc job={job_id[:8]}]"
    logger.info("%s background task started", _log)

    async with AsyncSessionLocal() as db:
        from app.models.discovery import DiscoveryJob

        job: DiscoveryJob | None = await db.get(DiscoveryJob, UUID(job_id))
        if not job:
            logger.error("%s job not found in DB — aborting", _log)
            return

        # ── Inject similar product keywords ───────────────────────────────────
        similar = await get_similar_products(db, UUID(product_id), active_only=True)
        if similar:
            sp_config = [
                {
                    "name":             sp.similar_product_name,
                    "keywords":         list(sp.discovery_keywords or []),
                    "similarity_score": sp.similarity_score,
                }
                for sp in similar
            ]
            # Merge into existing search_config (preserves any prior keys)
            config = dict(job.search_config or {})
            config["similar_products"] = sp_config
            job.search_config = config
            job.similar_products_searched = sp_config
            await db.commit()
            logger.info(
                "%s injected %d similar product keyword sets into job search_config",
                _log, len(sp_config),
            )
        else:
            logger.info("%s no active similar products — running primary keywords only", _log)

        orchestrator = DiscoveryOrchestrator()
        await orchestrator.run(UUID(job_id), db)

    logger.info("%s background task complete", _log)
