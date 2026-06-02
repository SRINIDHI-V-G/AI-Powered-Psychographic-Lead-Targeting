"""
Discovery API router.

Endpoints:
  POST /products/{id}/discovery/start       — start a discovery job
  GET  /products/{id}/discovery/jobs        — list all jobs for a product
  GET  /products/{id}/discovery/jobs/{jid}  — get one job (for status polling)
  GET  /products/{id}/discovery/users       — list discovered users (paginated)
  GET  /products/{id}/discovery/users/{uid}/content — user content items
  GET  /discovery/provider/status           — provider health check (unauthenticated)
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.crud.discovery import (
    count_discovered_users,
    create_discovery_job,
    get_discovered_users,
    get_discovery_job,
    get_discovery_jobs_for_product,
    get_user_content,
)
from app.crud.product import get_product_by_id
from app.database import get_db
from app.dependencies import get_current_company
from app.models.company import Company
from app.schemas.discovery import (
    DiscoveredUserListResponse,
    DiscoveredUserResponse,
    DiscoveryJobResponse,
    DiscoveryStartRequest,
    ProviderHealthResponse,
    UserContentResponse,
)
from app.services.discovery_service import start_discovery_background

router = APIRouter(tags=["Discovery"])


# ── Provider health (unauthenticated) ─────────────────────────────────────────

@router.get(
    "/discovery/provider/status",
    response_model=ProviderHealthResponse,
    summary="Check discovery provider health",
    description=(
        "Returns provider readiness without requiring an API key. "
        "Use this to verify Reddit credentials are configured before "
        "running a discovery job."
    ),
)
async def discovery_provider_status() -> ProviderHealthResponse:
    mock_mode = settings.use_mock_discovery()
    creds_ok = settings.reddit_credentials_configured()

    if mock_mode:
        from app.ml.discovery.mock_provider import MockDiscoveryProvider
        provider = MockDiscoveryProvider(delay_ms=0)
    else:
        from app.ml.discovery.reddit_provider import RedditProvider
        try:
            provider = RedditProvider()
        except RuntimeError as exc:
            return ProviderHealthResponse(
                ok=False,
                provider="reddit",
                detail=str(exc),
                mock_mode=True,
                credentials_configured=False,
            )

    health = await provider.health_check()
    return ProviderHealthResponse(
        ok=health["ok"],
        provider=health["provider"],
        detail=health["detail"],
        mock_mode=mock_mode,
        credentials_configured=creds_ok,
    )


# ── Start discovery ───────────────────────────────────────────────────────────

@router.post(
    "/products/{product_id}/discovery/start",
    response_model=DiscoveryJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start a discovery job for a product",
    description=(
        "Creates a discovery job and immediately fires it as a background task. "
        "Returns the job immediately (202 Accepted). "
        "Poll GET /products/{id}/discovery/jobs/{job_id} for status updates. "
        "Requires product status to be 'motivations_generated' or later."
    ),
)
async def start_discovery(
    product_id: UUID,
    body: DiscoveryStartRequest,
    background_tasks: BackgroundTasks,
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
) -> DiscoveryJobResponse:
    product = await get_product_by_id(db, product_id, company.id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product {product_id} not found.",
        )

    allowed_statuses = {
        "motivations_generated", "discovering", "nlp_processing",
        "ocean_scoring", "matching", "ranked", "completed",
    }
    if product.status.value not in allowed_statuses:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Discovery requires product status to be 'motivations_generated' "
                f"or later. Current status: {product.status.value}."
            ),
        )

    job = await create_discovery_job(
        db,
        product_id=product.id,
        max_users=body.max_users,
        search_config=body.search_config,
    )

    background_tasks.add_task(
        start_discovery_background,
        str(product.id),
        str(job.id),
    )
    return job


# ── Job status ────────────────────────────────────────────────────────────────

@router.get(
    "/products/{product_id}/discovery/jobs",
    response_model=list[DiscoveryJobResponse],
    summary="List all discovery jobs for a product",
)
async def list_discovery_jobs(
    product_id: UUID,
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
) -> list[DiscoveryJobResponse]:
    product = await get_product_by_id(db, product_id, company.id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")
    return await get_discovery_jobs_for_product(db, product_id)


@router.get(
    "/products/{product_id}/discovery/jobs/{job_id}",
    response_model=DiscoveryJobResponse,
    summary="Get a specific discovery job (for status polling)",
)
async def get_job(
    product_id: UUID,
    job_id: UUID,
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
) -> DiscoveryJobResponse:
    product = await get_product_by_id(db, product_id, company.id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")
    job = await get_discovery_job(db, job_id, product_id)
    if not job:
        raise HTTPException(status_code=404, detail="Discovery job not found.")
    return job


# ── Discovered users ──────────────────────────────────────────────────────────

@router.get(
    "/products/{product_id}/discovery/users",
    response_model=DiscoveredUserListResponse,
    summary="List discovered users for a product (paginated)",
)
async def list_discovered_users(
    product_id: UUID,
    job_id: UUID | None = Query(default=None, description="Filter by specific job"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
) -> DiscoveredUserListResponse:
    product = await get_product_by_id(db, product_id, company.id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")

    # If no job_id specified, use the most recent completed job
    actual_job_id = job_id
    if not actual_job_id:
        jobs = await get_discovery_jobs_for_product(db, product_id)
        completed = [j for j in jobs if j.status == "completed"]
        if completed:
            actual_job_id = completed[0].id

    users = await get_discovered_users(
        db, product_id, actual_job_id, page=page, limit=limit
    )
    total = await count_discovered_users(db, product_id, actual_job_id)

    return DiscoveredUserListResponse(
        product_id=product_id,
        job_id=actual_job_id or product_id,  # fallback for response schema
        total=total,
        page=page,
        limit=limit,
        users=users,
    )


@router.get(
    "/products/{product_id}/discovery/users/{user_id}/content",
    response_model=list[UserContentResponse],
    summary="Get content items collected for a specific user",
)
async def get_user_content_items(
    product_id: UUID,
    user_id: UUID,
    limit: int = Query(default=25, ge=1, le=100),
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
) -> list[UserContentResponse]:
    product = await get_product_by_id(db, product_id, company.id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")
    return await get_user_content(db, user_id, limit=limit)
