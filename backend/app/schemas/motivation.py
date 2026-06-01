from pydantic import BaseModel
from uuid import UUID
from datetime import datetime


class OceanProfileOut(BaseModel):
    openness: float
    conscientiousness: float
    extraversion: float
    agreeableness: float
    emotional_stability: float
    interest_tags: list[str]
    search_keywords: list[str]
    hashtags: list[str]

    model_config = {"from_attributes": True}


class MotivationCategoryOut(BaseModel):
    id: UUID
    product_id: UUID
    name: str
    description: str
    sort_order: int
    ocean_profile: OceanProfileOut | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class MotivationListOut(BaseModel):
    product_id: UUID
    total: int
    categories: list[MotivationCategoryOut]
