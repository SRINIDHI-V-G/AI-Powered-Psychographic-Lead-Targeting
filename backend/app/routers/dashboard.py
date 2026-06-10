"""
Dashboard overview router.

Provides company-wide summary statistics and pipeline activity feed.

Endpoints:
  GET /dashboard/overview   â€” aggregate stats + recent activity
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_company
from app.models.company import Company
from app.models.discovery import DiscoveredUser, DiscoveryJob
from app.models.matching import LeadMatch
from app.models.product import Product, ProductStatus

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


# â”€â”€ Response schemas â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class ProductPipelineSummary(BaseModel):
    product_id: str
    product_name: str
    status: str
    pipeline_step: int
    discovered_users: int
    ranked_leads: int
    hot_leads: int


class ActivityEvent(BaseModel):
    event_type: str        # "product_created" | "discovery_complete" | "leads_ranked" | "pipeline_failed"
    product_id: str
    product_name: str
    detail: str
    occurred_at: datetime


class ProviderBreakdown(BaseModel):
    provider: str        # "reddit" | "instagram" | "youtube" | "mock"
    users_discovered: int


class DashboardOverviewResponse(BaseModel):
    # Headline stats
    total_products: int
    total_discovered_users: int
    hot_leads_count: int
    warm_leads_count: int
    active_pipeline_jobs: int       # discovery jobs currently running

    # Real provider breakdown â€” populated from discovery_jobs.provider_name
    discovery_sources: list[ProviderBreakdown]

    # Per-product summary
    products: list[ProductPipelineSummary]

    # Recent activity feed (last 10 significant pipeline events)
    recent_activity: list[ActivityEvent]

    generated_at: datetime


# â”€â”€ Endpoint â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.get(
    "/overview",
    response_model=DashboardOverviewResponse,
    summary="Company-wide dashboard overview",
    description=(
        "Returns aggregate statistics for all products owned by the authenticated "
        "company: discovered user counts, lead tier counts, active pipeline jobs, "
        "and a recent activity feed."
    ),
)
async def get_dashboard_overview(
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
) -> DashboardOverviewResponse:

    # â”€â”€ 1. Load all products for this company â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    products_r = await db.execute(
        select(Product)
        .where(Product.company_id == company.id)
        .order_by(Product.created_at.desc())
    )
    products: list[Product] = list(products_r.scalars().all())
    product_ids = [p.id for p in products]

    if not product_ids:
        return DashboardOverviewResponse(
            total_products=0,
            total_discovered_users=0,
            hot_leads_count=0,
            warm_leads_count=0,
            active_pipeline_jobs=0,
            discovery_sources=[],
            products=[],
            recent_activity=[],
            generated_at=datetime.now(timezone.utc),
        )

    # â”€â”€ 2. Discovered user counts per product â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    users_r = await db.execute(
        select(DiscoveredUser.product_id, func.count().label("cnt"))
        .where(DiscoveredUser.product_id.in_(product_ids))
        .group_by(DiscoveredUser.product_id)
    )
    user_counts: dict = {row.product_id: row.cnt for row in users_r}
    total_discovered = sum(user_counts.values())

    # â”€â”€ 3. Lead tier counts per product â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # Tiers derived from final_score: hot>=75, warm>=55, cold<55
    leads_r = await db.execute(
        select(
            LeadMatch.product_id,
            LeadMatch.final_score,
        )
        .where(
            LeadMatch.product_id.in_(product_ids),
            LeadMatch.is_best_match == True,  # noqa: E712
        )
    )
    hot_per_product: dict = {}
    warm_per_product: dict = {}
    ranked_per_product: dict = {}
    for row in leads_r:
        pid = row.product_id
        ranked_per_product[pid] = ranked_per_product.get(pid, 0) + 1
        if row.final_score >= 75.0:
            hot_per_product[pid] = hot_per_product.get(pid, 0) + 1
        elif row.final_score >= 55.0:
            warm_per_product[pid] = warm_per_product.get(pid, 0) + 1

    total_hot = sum(hot_per_product.values())
    total_warm = sum(warm_per_product.values())

    # â”€â”€ 4. Active discovery jobs â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    active_r = await db.execute(
        select(func.count())
        .select_from(DiscoveryJob)
        .where(
            DiscoveryJob.product_id.in_(product_ids),
            DiscoveryJob.status.in_(["pending", "running", "collecting"]),
        )
    )
    active_jobs: int = active_r.scalar_one()

    # â”€â”€ 4b. Provider breakdown â€” count per platform from discovered_users â”€â”€â”€â”€
    # Group by DiscoveredUser.platform (not DiscoveryJob.provider_name) so that
    # multi-provider jobs (where provider_name = "youtube+instagram") still
    # produce accurate per-platform counts.
    provider_r = await db.execute(
        select(
            DiscoveredUser.platform,
            func.count().label("total"),
        )
        .where(DiscoveredUser.product_id.in_(product_ids))
        .group_by(DiscoveredUser.platform)
    )
    discovery_sources = [
        ProviderBreakdown(provider=row.platform, users_discovered=int(row.total or 0))
        for row in provider_r
        if row.total and int(row.total) > 0
    ]

    # â”€â”€ 5. Per-product summaries â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    product_summaries = [
        ProductPipelineSummary(
            product_id=str(p.id),
            product_name=p.name,
            status=p.status.value if hasattr(p.status, "value") else str(p.status),
            pipeline_step=p.pipeline_step,
            discovered_users=user_counts.get(p.id, 0),
            ranked_leads=ranked_per_product.get(p.id, 0),
            hot_leads=hot_per_product.get(p.id, 0),
        )
        for p in products
    ]

    # â”€â”€ 6. Recent activity feed â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # Derive activity events from products + discovery jobs
    activity: list[ActivityEvent] = []

    # Latest discovery jobs (up to 10)
    jobs_r = await db.execute(
        select(DiscoveryJob, Product)
        .join(Product, DiscoveryJob.product_id == Product.id)
        .where(
            DiscoveryJob.product_id.in_(product_ids),
            DiscoveryJob.status.in_(["completed", "failed", "running"]),
        )
        .order_by(DiscoveryJob.created_at.desc())
        .limit(10)
    )
    for job, prod in jobs_r:
        event_type = {
            "completed": "discovery_complete",
            "failed": "discovery_failed",
            "running": "discovery_running",
        }.get(job.status, "discovery_event")
        activity.append(ActivityEvent(
            event_type=event_type,
            product_id=str(prod.id),
            product_name=prod.name,
            detail=f"{job.users_discovered} users discovered via {job.provider_name or 'provider'}",
            occurred_at=job.completed_at or job.started_at or job.created_at,
        ))

    # Products that reached 'ranked' or 'failed' status (last 10)
    notable_r = await db.execute(
        select(Product)
        .where(
            Product.company_id == company.id,
            Product.status.in_([
                ProductStatus.ranked, ProductStatus.completed,
                ProductStatus.failed, ProductStatus.motivations_generated,
            ]),
        )
        .order_by(Product.updated_at.desc())
        .limit(10)
    )
    for prod in notable_r.scalars():
        s = prod.status.value if hasattr(prod.status, "value") else str(prod.status)
        event_type_map = {
            "ranked": "leads_ranked",
            "completed": "leads_ranked",
            "failed": "pipeline_failed",
            "motivations_generated": "motivations_ready",
        }
        activity.append(ActivityEvent(
            event_type=event_type_map.get(s, "pipeline_event"),
            product_id=str(prod.id),
            product_name=prod.name,
            detail=f"Pipeline status: {s}",
            occurred_at=prod.updated_at,
        ))

    # Sort by recency and cap at 10
    activity.sort(key=lambda e: e.occurred_at, reverse=True)
    activity = activity[:10]

    return DashboardOverviewResponse(
        total_products=len(products),
        total_discovered_users=total_discovered,
        hot_leads_count=total_hot,
        warm_leads_count=total_warm,
        active_pipeline_jobs=active_jobs,
        discovery_sources=discovery_sources,
        products=product_summaries,
        recent_activity=activity,
        generated_at=datetime.now(timezone.utc),
    )

