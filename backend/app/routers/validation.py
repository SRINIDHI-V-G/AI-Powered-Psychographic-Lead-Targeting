"""
Lead validation, inspection, analytics, and export API router.

Endpoints:
  GET /products/{id}/leads/{uid}/inspect     — full lead inspection with OCEAN, NLP, content
  GET /products/{id}/leads/analytics         — score distributions + calibration notes
  GET /products/{id}/leads/export            — CSV or JSON export of ranked leads

These endpoints exist to answer: "Does the ranking system produce useful leads?"
They expose all signals that drove a match score so a human reviewer can validate
or invalidate the pipeline's output.
"""
from __future__ import annotations

import csv
import io
import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.handles import get_user_handles
from app.crud.product import get_product_by_id
from app.crud.validation import (
    get_lead_inspection,
    get_lead_analytics,
    get_leads_for_export,
    get_leads_summary,
    QUALITY_MIN_CONFIDENCE,
)
from app.database import get_db
from app.dependencies import get_current_company
from app.models.company import Company
from app.schemas.handles import HandleListResponse, HandleResponse
from app.schemas.validation import LeadInspectionResponse, LeadAnalyticsResponse

router = APIRouter(tags=["Lead Validation"])

# CSV column order — consistent, human-readable
_CSV_FIELDS = [
    "rank", "username", "display_name", "platform", "profile_url",
    "location", "location_confidence", "follower_count",
    "discovery_source",
    "best_motivation_category",
    "final_score", "ocean_component_score", "embedding_component_score", "interest_component_score",
    "product_ocean_score",
    "confidence",
    "openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism",
    "ocean_scoring_method",
    "interest_tags", "total_tokens",
    "reasoning", "quality_flags", "top_handle",
]


@router.get(
    "/products/{product_id}/leads/summary",
    summary="Lightweight lead summary for dashboard overview cards",
    description="Single aggregated query: total ranked, avg score, top score, dominant motivation category.",
)
async def leads_summary(
    product_id: UUID,
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
) -> dict:
    product = await get_product_by_id(db, product_id, company.id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")
    return await get_leads_summary(db, product_id)


@router.get(
    "/products/{product_id}/leads/{user_id}/inspect",
    response_model=LeadInspectionResponse,
    summary="Full psychographic inspection for one lead",
    description=(
        "Returns everything that drove this lead's rank: OCEAN profile, "
        "Empath categories, interest tags, sample content, match scores per "
        "motivation category, and quality flags. "
        "Use this endpoint to validate whether a top-ranked lead looks like "
        "the intended target audience."
    ),
)
async def inspect_lead(
    product_id: UUID,
    user_id: UUID,
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
) -> LeadInspectionResponse:
    product = await get_product_by_id(db, product_id, company.id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")
    result = await get_lead_inspection(db, product_id, user_id)
    if not result:
        raise HTTPException(
            status_code=404,
            detail="Lead not found or matching has not been run for this user.",
        )
    return LeadInspectionResponse(**result)


@router.get(
    "/products/{product_id}/leads/analytics",
    response_model=LeadAnalyticsResponse,
    summary="Score distributions and calibration analysis for a product's ranked leads",
    description=(
        "Returns statistical distributions of all scoring components, "
        "a quality summary (how many leads pass quality filters), "
        "motivation category breakdown, and calibration notes. "
        "Use this to evaluate whether the ranking algorithm is behaving sensibly "
        "before using the lead list."
    ),
)
async def lead_analytics(
    product_id: UUID,
    min_confidence: float = Query(
        0.0, ge=0.0, le=100.0,
        description="Only include leads with confidence >= this value in analysis.",
    ),
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
) -> LeadAnalyticsResponse:
    product = await get_product_by_id(db, product_id, company.id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")
    result = await get_lead_analytics(db, product_id, min_confidence=min_confidence)
    return LeadAnalyticsResponse(**result)


@router.get(
    "/products/{product_id}/leads/{user_id}/handles",
    response_model=HandleListResponse,
    summary="Discovered social handles for one lead",
    description=(
        "Returns all candidate social-media handles discovered for a lead, "
        "ordered by handle_score descending. "
        "Tier values: confirmed (found in bio/profile URL), extracted (bio @mention), "
        "inferred (username pattern), predicted (LLM/pattern-library candidate)."
    ),
)
async def get_lead_handles(
    product_id: UUID,
    user_id: UUID,
    platform: str | None = Query(
        None, description="Filter to a single platform (e.g. twitter, instagram)"
    ),
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
) -> HandleListResponse:
    product = await get_product_by_id(db, product_id, company.id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")
    handles = await get_user_handles(db, user_id, platform=platform)
    return HandleListResponse(
        discovered_user_id=user_id,
        total=len(handles),
        handles=[HandleResponse.model_validate(h) for h in handles],
    )


@router.get(
    "/products/{product_id}/leads/export",
    summary="Export ranked leads as CSV or JSON",
    description=(
        "Downloads ranked leads as a file. "
        "Includes rank, profile info, scores (all components), OCEAN dimensions, "
        "interest tags, reasoning, and quality flags. "
        "Use format=csv for spreadsheet import, format=json for programmatic use."
    ),
)
async def export_leads(
    product_id: UUID,
    format: str = Query("csv", pattern="^(csv|json)$", description="Export format: csv or json"),
    min_score: float = Query(0.0, ge=0.0, le=100.0, description="Minimum final score"),
    min_confidence: float = Query(
        0.0, ge=0.0, le=100.0,
        description=f"Minimum confidence (recommended: {QUALITY_MIN_CONFIDENCE})",
    ),
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    product = await get_product_by_id(db, product_id, company.id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")

    rows = await get_leads_for_export(
        db, product_id,
        min_score=min_score,
        min_confidence=min_confidence,
    )

    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in (product.name or "leads"))[:40]
    filename = f"leads_{safe_name}"

    if format == "csv":
        return _build_csv_response(rows, filename)
    return _build_json_response(rows, filename, product_id, min_score, min_confidence)


def _build_csv_response(rows: list[dict], filename: str) -> StreamingResponse:
    """Stream a UTF-8 CSV with BOM for Excel compatibility."""
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=_CSV_FIELDS,
        extrasaction="ignore",
        lineterminator="\r\n",
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({k: ("" if row.get(k) is None else row[k]) for k in _CSV_FIELDS})

    csv_content = output.getvalue()

    return StreamingResponse(
        iter([csv_content.encode("utf-8-sig")]),  # utf-8-sig adds BOM automatically
        media_type="text/csv; charset=utf-8-sig",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}.csv"',
            "X-Total-Rows": str(len(rows)),
        },
    )


def _build_json_response(
    rows: list[dict],
    filename: str,
    product_id: UUID,
    min_score: float,
    min_confidence: float,
) -> StreamingResponse:
    """Stream a JSON export with metadata envelope."""
    payload = {
        "product_id": str(product_id),
        "total_rows": len(rows),
        "min_score_applied": min_score,
        "min_confidence_applied": min_confidence,
        "leads": rows,
    }
    json_bytes = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")

    return StreamingResponse(
        iter([json_bytes]),
        media_type="application/json; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}.json"',
            "X-Total-Rows": str(len(rows)),
        },
    )
