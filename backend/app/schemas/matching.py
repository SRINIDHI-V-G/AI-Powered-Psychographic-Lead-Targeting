"""Pydantic schemas for the matching / lead ranking API."""
from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class MatchStatusResponse(BaseModel):
    product_id: UUID
    total_users: int
    matched: int
    ranked: int
    pending: int
    progress_pct: float


class LeadSummary(BaseModel):
    rank: int | None
    user_id: str
    username: str
    display_name: str | None
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
    confidence: float
    reasoning: list[str]


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
