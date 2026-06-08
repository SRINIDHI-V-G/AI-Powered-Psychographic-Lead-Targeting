"""Pydantic schemas for the OCEAN scoring API."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class OceanStatusResponse(BaseModel):
    """Pipeline OCEAN scoring status for a product."""
    product_id: UUID
    total_users: int
    ocean_scored: int
    ocean_pending: int
    progress_pct: float
    scoring_model: str = "Ollama"


class OceanReasoningResponse(BaseModel):
    openness: str = ""
    conscientiousness: str = ""
    extraversion: str = ""
    agreeableness: str = ""
    neuroticism: str = ""


class UserOceanScoreResponse(BaseModel):
    id: UUID
    user_id: UUID
    openness: float
    conscientiousness: float
    extraversion: float
    agreeableness: float
    neuroticism: float
    confidence: float
    scoring_method: str
    reasoning: dict
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
