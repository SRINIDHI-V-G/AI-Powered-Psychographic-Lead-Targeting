from pydantic import BaseModel, field_validator, model_validator
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

    @model_validator(mode="after")
    def infer_target_city(self) -> "ProductCreate":
        # Auto-parse "Chennai, India" → target_city="Chennai" when not explicitly provided
        if not self.target_city and self.target_location and "," in self.target_location:
            parts = [p.strip() for p in self.target_location.split(",")]
            if parts[0]:
                self.target_city = parts[0]
        return self


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


class ProductStatusResponse(BaseModel):
    """Lightweight schema for the /products/{id}/status poll endpoint."""
    id: UUID
    status: ProductStatus
    pipeline_step: int
    error_message: str | None
    updated_at: datetime

    model_config = {"from_attributes": True}
