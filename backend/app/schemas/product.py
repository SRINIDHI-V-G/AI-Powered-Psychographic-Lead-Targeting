from pydantic import BaseModel, field_validator
from uuid import UUID
from datetime import datetime
from app.models.product import PriceRange, ProductStatus


class ProductCreate(BaseModel):
    name: str
    description: str
    category: str
    subcategory: str | None = None
    price_range: PriceRange
    target_location: str
    target_city: str | None = None
    target_country: str = "India"
    keywords: list[str] = []

    @field_validator("description")
    @classmethod
    def description_min_length(cls, v: str) -> str:
        if len(v.strip()) < 20:
            raise ValueError("Description must be at least 20 characters")
        return v.strip()

    @field_validator("name", "category", "target_location")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("This field cannot be empty")
        return v.strip()


class ProductResponse(BaseModel):
    id: UUID
    company_id: UUID
    name: str
    description: str
    category: str
    subcategory: str | None
    price_range: PriceRange
    target_location: str
    target_city: str | None
    target_country: str
    keywords: list[str]
    status: ProductStatus
    pipeline_step: int
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
