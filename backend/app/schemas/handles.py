"""Pydantic schemas for lead handle discovery."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class HandleEvidence(BaseModel):
    source: str
    raw_text: str | None = None
    generator: str
    similarity: float | None = None
    interest_tags: list[str] = []


class HandleVerification(BaseModel):
    verified: bool = False
    verification_method: str | None = None
    profile_exists: bool | None = None
    profile_url: str | None = None
    follower_count: int | None = None


class HandleResponse(BaseModel):
    id: UUID
    discovered_user_id: UUID
    platform: str
    handle: str
    handle_score: float
    confidence: float
    tier: str
    evidence_json: dict
    verification_json: dict
    created_at: datetime

    model_config = {"from_attributes": True}


class HandleListResponse(BaseModel):
    discovered_user_id: UUID
    total: int
    handles: list[HandleResponse]
