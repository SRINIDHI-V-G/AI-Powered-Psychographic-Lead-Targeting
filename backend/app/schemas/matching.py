"""Pydantic schemas for the matching / lead ranking API."""
from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class MatchStatusResponse(BaseModel):
    product_id: UUID
    total_users: int
    matched: int
    ranked: int
    # Real tier counts derived from final_score thresholds
    hot: int = 0   # final_score >= 75
    warm: int = 0  # 55 <= final_score < 75
    cold: int = 0  # final_score < 55
    pending: int
    progress_pct: float


class LeadSummary(BaseModel):
    rank: int | None
    user_id: str
    username: str
    display_name: str | None
    bio: str | None = None
    platform: str
    profile_url: str | None
    location: str | None
    follower_count: int
    best_motivation_category: str
    motivation_category_id: str
    final_score: float
    ocean_score: float
    embedding_score: float
    interest_score: float
    # Alignment between lead OCEAN and the product-level OCEAN vector.
    product_ocean_score: float | None = None
    confidence: float
    reasoning: list[str]
    discovery_source: str = "primary"
    # Individual OCEAN personality dimension scores (0-100 scale)
    openness: float | None = None
    conscientiousness: float | None = None
    extraversion: float | None = None
    agreeableness: float | None = None
    neuroticism: float | None = None
    ocean_scoring_method: str | None = None


class LeadListResponse(BaseModel):
    total_leads: int
    page: int
    page_size: int
    total_pages: int
    leads: list[LeadSummary]


class CategoryScoreDetail(BaseModel):
    motivation_category_id: str
    motivation_category: str
    final_score: float
    ocean_score: float
    embedding_score: float
    interest_score: float
    product_ocean_score: float | None = None
    confidence: float
    reasoning: list[str]


class BestMatchDetail(CategoryScoreDetail):
    rank: int | None


class LeadDetailResponse(BaseModel):
    user_id: str
    username: str
    display_name: str | None
    platform: str
    profile_url: str | None
    location: str | None
    location_confidence: str
    follower_count: int
    best_match: BestMatchDetail | None
    all_category_scores: list[CategoryScoreDetail]
