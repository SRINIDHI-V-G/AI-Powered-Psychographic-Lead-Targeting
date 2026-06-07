from pydantic import BaseModel, EmailStr, field_validator
from uuid import UUID
from datetime import datetime


class CompanyCreate(BaseModel):
    name: str
    email: EmailStr
    industry: str | None = None
    website: str | None = None
    description: str | None = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Name cannot be empty")
        return v.strip()


class CompanyPublic(BaseModel):
    id: UUID
    name: str
    email: str
    industry: str | None
    website: str | None
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CompanyResponse(CompanyPublic):
    """Returned only on POST /companies — includes the api_key."""
    api_key: str

    model_config = {"from_attributes": True}


class ApiKeyRotateResponse(BaseModel):
    """Returned only on POST /companies/me/rotate-key — new plaintext key."""
    id: UUID
    api_key: str
    message: str
