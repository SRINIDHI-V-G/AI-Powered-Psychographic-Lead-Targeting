"""
Discovery service — business logic layer for discovery pipeline.

Coordinates between the HTTP layer (router) and the ML layer (orchestrator).
All DB sessions are opened here; the orchestrator receives an open session.

Similar product keyword injection:
  Before handing off to the orchestrator, this service loads any active
  SimilarProduct rows for the product and writes their discovery_keywords
  into job.search_config["similar_products"]. The orchestrator reads that
  config key and merges the keywords into its unified search set.

Auto-trigger:
  auto_start_discovery(product_id) is called by the pipeline auto-chain
  (from product_similarity_service after step 4 completes). It creates
  the job and fires start_discovery_background without requiring an HTTP
  request or user intervention.

Concurrency queue:
  At most DISCOVERY_MAX_CONCURRENT_JOBS may run simultaneously. Excess
  auto-triggered jobs are created with status="pending". When a running
  job finishes, _dequeue_next_pending_job() picks up the next one.

Orphan recovery:
  recover_stale_jobs() is called at server startup. It marks any job that
  has been status="running" or "collecting" for longer than
  DISCOVERY_STALE_JOB_TIMEOUT_MINUTES as "failed", resets the associated
  product back to similar_products_found (step 4), and re-queues a new
  pending job so the pipeline can resume automatically.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from app.config import settings
from app.crud.similar_products import get_similar_products
from app.database import AsyncSessionLocal
from app.ml.discovery.orchestrator import DiscoveryOrchestrator

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _count_active_jobs(db) -> int:
    """Return number of jobs currently in running or collecting state."""
    from sqlalchemy import func, select
    from app.models.discovery import DiscoveryJob
    r = await db.execute(
        select(func.count()).select_from(DiscoveryJob).where(
            DiscoveryJob.status.in_(["running", "collecting"])
        )
    )
    return r.scalar_one()


async def _dequeue_next_pending_job() -> None:
    """
    Start the next queued (status="pending") discovery job if a concurrency
    slot is available. Called after any job completes or fails.
    """
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        from app.models.discovery import DiscoveryJob

        active = await _count_active_jobs(db)
        if active >= settings.DISCOVERY_MAX_CONCURRENT_JOBS:
            return

        # Oldest pending job first (FIFO)
        r = await db.execute(
            select(DiscoveryJob)
            .where(DiscoveryJob.status == "pending")
            .order_by(DiscoveryJob.created_at.asc())
            .limit(1)
        )
        job = r.scalar_one_or_none()
        if not job:
            return

        product_id = str(job.product_id)
        job_id = str(job.id)
        await db.commit()

    logger.info("[DISCOVERY dequeue] starting queued job=%s product=%s", job_id[:8], product_id[:8])
    await start_discovery_background(product_id, job_id)


# ── Core background task ──────────────────────────────────────────────────────

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

    After the orchestrator finishes (success or failure), calls
    _dequeue_next_pending_job() to start the next queued job if capacity allows.
    """
    _log = f"[DISCOVERY svc job={job_id[:8]}]"
    logger.info("%s background task started", _log)

    async with AsyncSessionLocal() as db:
        from app.models.discovery import DiscoveryJob

        job: DiscoveryJob | None = await db.get(DiscoveryJob, UUID(job_id))
        if not job:
            logger.error("%s job not found in DB — aborting", _log)
            await _dequeue_next_pending_job()
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

    # Open a slot for the next pending job.
    await _dequeue_next_pending_job()


# ── Auto-trigger (pipeline chain) ────────────────────────────────────────────

async def auto_start_discovery(product_id: str) -> None:
    """
    Pipeline auto-chain entry point — called automatically after step 4
    (similar_products_found) with no HTTP request or user action required.

    Creates a discovery job. If fewer than DISCOVERY_MAX_CONCURRENT_JOBS are
    running, starts it immediately (await). Otherwise, creates it as
    status="pending" and returns — _dequeue_next_pending_job() will start it
    when a slot opens.

    Idempotent: skips silently when an active/pending job already exists.
    """
    _log = f"[DISCOVERY auto product={product_id[:8]}]"
    logger.info("%s auto-trigger from pipeline", _log)

    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        from app.crud.discovery import create_discovery_job
        from app.models.discovery import DiscoveryJob

        # Guard: skip if a job is already active or queued for this product
        active_r = await db.execute(
            select(DiscoveryJob)
            .where(
                DiscoveryJob.product_id == UUID(product_id),
                DiscoveryJob.status.in_(["pending", "running", "collecting"]),
            )
            .limit(1)
        )
        if active_r.scalar_one_or_none():
            logger.info("%s active/pending job already exists — skipping auto-trigger", _log)
            return

        # Check global concurrency limit
        active_count = await _count_active_jobs(db)
        if active_count >= settings.DISCOVERY_MAX_CONCURRENT_JOBS:
            # Queue the job — _dequeue_next_pending_job() will start it later
            job = await create_discovery_job(
                db,
                product_id=UUID(product_id),
                max_users=settings.DISCOVERY_MAX_USERS,
                search_config={"queued": True},
            )
            # Mark as pending so it isn't started yet
            job.status = "pending"
            job_id = str(job.id)
            await db.commit()
            logger.info(
                "%s concurrency limit reached (%d/%d) — queued job=%s as pending",
                _log, active_count, settings.DISCOVERY_MAX_CONCURRENT_JOBS, job_id[:8],
            )
            return  # Will be started by _dequeue_next_pending_job()

        job = await create_discovery_job(
            db,
            product_id=UUID(product_id),
            max_users=settings.DISCOVERY_MAX_USERS,
            search_config={},
        )
        job_id = str(job.id)
        await db.commit()
        logger.info(
            "%s created job=%s max_users=%d (slot %d/%d)",
            _log, job_id[:8], settings.DISCOVERY_MAX_USERS,
            active_count + 1, settings.DISCOVERY_MAX_CONCURRENT_JOBS,
        )

    # Await directly — avoids unreliable nested asyncio.create_task().
    # The session above is already closed; start_discovery_background opens its own.
    await start_discovery_background(product_id, job_id)


# ── Startup orphan recovery ───────────────────────────────────────────────────

async def recover_stale_jobs() -> None:
    """
    Called once at server startup (from main.py lifespan).

    Finds any discovery job that has been status="running" or "collecting"
    for longer than DISCOVERY_STALE_JOB_TIMEOUT_MINUTES. These are orphaned
    — the process that was running them was killed (restart, crash, OOM).

    For each stale job:
      1. Mark the job as "failed".
      2. If the product is currently at step 5 (discovering), reset it to
         step 4 (similar_products_found) so the pipeline can be retried.
      3. Queue a new pending job for the product so it resumes automatically.

    Jobs that have been running for LESS than the timeout are left alone —
    they may still be legitimately in-progress (e.g. server restarted while
    a job that just started is still within its expected runtime).
    """
    stale_cutoff = datetime.now(timezone.utc) - timedelta(
        minutes=settings.DISCOVERY_STALE_JOB_TIMEOUT_MINUTES
    )

    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        from app.models.discovery import DiscoveryJob
        from app.models.product import Product, ProductStatus
        from app.crud.discovery import create_discovery_job

        r = await db.execute(
            select(DiscoveryJob).where(
                DiscoveryJob.status.in_(["running", "collecting"]),
                DiscoveryJob.started_at < stale_cutoff,
            )
        )
        stale_jobs = r.scalars().all()

        if not stale_jobs:
            logger.info("[DISCOVERY startup] no stale jobs found")
            return

        logger.warning(
            "[DISCOVERY startup] found %d stale job(s) — marking failed and re-queuing",
            len(stale_jobs),
        )

        requeue_product_ids: list[UUID] = []

        for job in stale_jobs:
            runtime_min = (
                (datetime.now(timezone.utc) - job.started_at).total_seconds() / 60
                if job.started_at else 0
            )
            logger.warning(
                "[DISCOVERY startup] stale job=%s product=%s status=%s "
                "running_for=%.0fmin — marking failed",
                str(job.id)[:8], str(job.product_id)[:8], job.status, runtime_min,
            )
            job.status = "failed"
            job.error_message = (
                f"Job was interrupted by a server restart after {runtime_min:.0f} minutes. "
                "Re-queued automatically."
            )
            job.completed_at = datetime.now(timezone.utc)

            # Reset product to step 4 if it was advanced to step 5 by this job
            product: Product | None = await db.get(Product, job.product_id)
            if product and product.status == ProductStatus.discovering:
                product.status = ProductStatus.similar_products_found
                product.pipeline_step = 4
                product.error_message = (
                    "Discovery was interrupted by a server restart. "
                    "Automatically re-queued."
                )
                requeue_product_ids.append(job.product_id)
                logger.info(
                    "[DISCOVERY startup] reset product=%s to similar_products_found",
                    str(job.product_id)[:8],
                )

        await db.commit()

        # Re-queue as pending jobs (up to MAX_CONCURRENT will start immediately)
        slots_available = settings.DISCOVERY_MAX_CONCURRENT_JOBS
        for pid in requeue_product_ids:
            # Check no active/pending job already exists for this product
            existing_r = await db.execute(
                select(DiscoveryJob).where(
                    DiscoveryJob.product_id == pid,
                    DiscoveryJob.status.in_(["pending", "running", "collecting"]),
                ).limit(1)
            )
            if existing_r.scalar_one_or_none():
                continue

            new_job = await create_discovery_job(
                db,
                product_id=pid,
                max_users=settings.DISCOVERY_MAX_USERS,
                search_config={"requeued_after_restart": True},
            )
            new_job.status = "pending"
            await db.commit()
            logger.info(
                "[DISCOVERY startup] re-queued job=%s for product=%s",
                str(new_job.id)[:8], str(pid)[:8],
            )

    # Start pending jobs up to the concurrency limit
    for _ in range(min(len(requeue_product_ids), settings.DISCOVERY_MAX_CONCURRENT_JOBS)):
        await _dequeue_next_pending_job()
