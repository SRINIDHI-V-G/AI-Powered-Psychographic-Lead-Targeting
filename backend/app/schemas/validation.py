"""Pydantic schemas for lead validation, inspection, analytics, and export."""
from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from app.schemas.handles import HandleResponse


# ── Inspection ────────────────────────────────────────────────────────────────

class ContentSample(BaseModel):
    content_type: str
    content_text: str
    engagement: int
    source_url: str | None


class OceanProfile(BaseModel):
    openness: float | None
    conscientiousness: float | None
    extraversion: float | None
    agreeableness: float | None
    neuroticism: float | None
    confidence: float
    scoring_method: str


class ContentQuality(BaseModel):
    total_tokens: int
    vocabulary_richness: float | None
    avg_sentence_length: float | None
    num_content_items: int


class EmpathCategory(BaseModel):
    category: str
    score: float


class CategoryMatchScore(BaseModel):
    motivation_category_id: str
    motivation_category: str
    final_score: float
    ocean_score: float
    embedding_score: float
    interest_score: float
    product_ocean_score: float | None = None
    confidence: float
    reasoning: list[str]


class BestMatchInspection(CategoryMatchScore):
    rank: int | None


class LeadInspectionResponse(BaseModel):
    user_id: str
    username: str
    display_name: str | None
    platform: str
    profile_url: str | None
    location: str | None
    location_confidence: str
    follower_count: int
    content_quality: ContentQuality
    ocean_profile: OceanProfile
    interest_tags: list[str]
    top_empath_categories: list[EmpathCategory]
    content_samples: list[ContentSample]
    best_match: BestMatchInspection | None
    all_category_scores: list[CategoryMatchScore]
    quality_flags: list[str]
    passes_quality_filter: bool
    handles: list[HandleResponse] = []


# ── Analytics ─────────────────────────────────────────────────────────────────

class ScoreStats(BaseModel):
    count: int
    min: float | None
    max: float | None
    mean: float | None
    median: float | None
    p25: float | None
    p75: float | None
    std_dev: float | None


class HistogramBucket(BaseModel):
    range: str
    count: int


class ScoreDistributionWithHistogram(ScoreStats):
    histogram: list[HistogramBucket]


class QualitySummary(BaseModel):
    passing_all_filters: int
    pct_passing: float
    flagged_low_confidence: int
    flagged_heuristic_ocean: int
    flagged_insufficient_content: int
    recommended_min_confidence: float


class MotivationCategoryCount(BaseModel):
    category: str
    count: int


class LeadAnalyticsResponse(BaseModel):
    product_id: UUID
    total_ranked: int
    quality_summary: QualitySummary
    final_score_distribution: ScoreDistributionWithHistogram
    confidence_distribution: ScoreStats
    ocean_score_distribution: ScoreStats
    embedding_score_distribution: ScoreStats
    interest_score_distribution: ScoreStats
    top_motivation_categories: list[MotivationCategoryCount]
    calibration_notes: list[str]


# ── Export metadata (returned alongside file download) ────────────────────────

class ExportMetadata(BaseModel):
    product_id: UUID
    total_rows: int
    min_score_applied: float
    min_confidence_applied: float
    format: str
