"""
Pydantic schemas for the Similar Products API.

SimilarProductResponse      — one similar product entry
SimilarProductListResponse  — list wrapper returned by GET /products/{id}/similar-products
SimilarProductToggleRequest — body for PATCH /similar-products/{sp_id}/toggle
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class SimilarProductResponse(BaseModel):
    """One similar product found for a registered product."""

    id: UUID
    product_id: UUID

    similar_product_name: str
    similar_product_category: str | None = None
    similar_product_description: str | None = None

    # OCEAN profile of this similar product (0-100, LLM-generated)
    openness: float | None = None
    conscientiousness: float | None = None
    extraversion: float | None = None
    agreeableness: float | None = None
    neuroticism: float | None = None

    # How personality-aligned this product is with the source product (0.0-1.0)
    similarity_score: float | None = Field(
        default=None,
        description="Cosine similarity between this product's OCEAN and the source product's OCEAN. Range 0.0-1.0.",
    )

    # Search terms used during discovery for this similar product
    discovery_keywords: list[str] = Field(default_factory=list)

    is_active: bool
    sort_order: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class SimilarProductListResponse(BaseModel):
    """Wrapper returned by the list endpoint."""

    product_id: UUID
    count: int
    items: list[SimilarProductResponse]


class SimilarProductToggleRequest(BaseModel):
    """Request body for toggling a similar product on or off."""

    is_active: bool = Field(
        description="Set to false to exclude this similar product from future discovery runs."
    )
