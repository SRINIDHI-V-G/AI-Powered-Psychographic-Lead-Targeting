"""Pydantic schemas for the discovery API."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


# ── Discovery Job ─────────────────────────────────────────────────────────────

class DiscoveryStartRequest(BaseModel):
    max_users: int = Field(
        default=150,
        ge=10,
        le=500,
        description=(
            "Maximum users to discover. Default 150 (≈37 min at Reddit rate limits). "
            "Increase to 300-500 only when Celery workers are in place."
        ),
    )
    search_config: dict = Field(
        default_factory=dict,
        description="Optional provider-specific overrides.",
    )


class DiscoveryJobResponse(BaseModel):
    id: UUID
    product_id: UUID
    provider_name: str
    status: str
    sources: list
    max_users: int
    users_discovered: int
    users_content_collected: int
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Discovered User ───────────────────────────────────────────────────────────

class DiscoveredUserResponse(BaseModel):
    id: UUID
    discovery_job_id: UUID
    product_id: UUID
    platform: str
    source_provider: str
    username: str
    display_name: str | None
    bio: str | None
    location: str | None
    location_confidence: str
    follower_count: int
    post_count: int | None
    profile_url: str | None
    content_collected: bool
    nlp_processed: bool
    ocean_scored: bool
    matched: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class DiscoveredUserListResponse(BaseModel):
    product_id: UUID
    job_id: UUID
    total: int
    page: int
    limit: int
    users: list[DiscoveredUserResponse]


# ── Content Item ──────────────────────────────────────────────────────────────

class UserContentResponse(BaseModel):
    id: UUID
    user_id: UUID
    content_type: str
    content_text: str
    source_url: str | None
    engagement: int
    posted_at: datetime | None
    collected_at: datetime

    model_config = {"from_attributes": True}


# ── Provider health ───────────────────────────────────────────────────────────

class ProviderInfo(BaseModel):
    configured: bool
    healthy: bool
    detail: str = ""


class AllProvidersStatusResponse(BaseModel):
    youtube: ProviderInfo
    instagram: ProviderInfo
    reddit: ProviderInfo
    google_reviews: ProviderInfo
    mock_mode: bool
