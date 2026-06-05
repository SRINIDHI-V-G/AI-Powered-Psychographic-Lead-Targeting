"""
Pydantic schemas for the Product OCEAN Profile API.

ProductOceanResponse    — returned by GET /products/{id}/ocean
ProductOceanTriggerResponse — returned by POST /products/{id}/ocean/trigger
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ProductOceanResponse(BaseModel):
    """Full product OCEAN profile as returned by the API."""

    id: UUID
    product_id: UUID

    # OCEAN dimensions (0-100 scale)
    openness: float = Field(ge=0.0, le=100.0)
    conscientiousness: float = Field(ge=0.0, le=100.0)
    extraversion: float = Field(ge=0.0, le=100.0)
    agreeableness: float = Field(ge=0.0, le=100.0)
    neuroticism: float = Field(ge=0.0, le=100.0)

    # Quality metadata
    confidence: float = Field(
        ge=0.0,
        le=100.0,
        description="Proportion of motivation profiles that contributed valid data (0-100).",
    )
    component_count: int | None = Field(
        default=None,
        description="How many motivation OCEAN profiles were averaged to produce this vector.",
    )
    derivation_method: str = Field(
        description="How this vector was produced. Currently always 'motivation_average'."
    )

    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProductOceanTriggerResponse(BaseModel):
    """Returned when a manual re-generation is triggered."""

    status: str = Field(description="'triggered' or 'already_running'")
    message: str
