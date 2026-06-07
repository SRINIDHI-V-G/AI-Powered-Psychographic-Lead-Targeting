from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.company import (
    create_company,
    get_company_by_email,
    rotate_api_key,
)
from app.database import get_db
from app.dependencies import get_current_company
from app.models.company import Company
from app.schemas.company import (
    ApiKeyRotateResponse,
    CompanyCreate,
    CompanyPublic,
    CompanyResponse,
)

router = APIRouter(prefix="/companies", tags=["Companies"])


@router.post(
    "/",
    response_model=CompanyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new company",
    description=(
        "Creates a company account and returns a one-time API key. "
        "Store the api_key immediately — it is shown only once."
    ),
)
async def register_company(
    data: CompanyCreate,
    db: AsyncSession = Depends(get_db),
) -> CompanyResponse:
    existing = await get_company_by_email(db, data.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A company with email '{data.email}' is already registered.",
        )
    raw_key, company = await create_company(db, data)
    # Build response manually so api_key is the plaintext key, not the stored hash.
    return CompanyResponse(
        id=company.id,
        name=company.name,
        email=company.email,
        industry=company.industry,
        website=company.website,
        description=company.description,
        is_active=company.is_active,
        created_at=company.created_at,
        updated_at=company.updated_at,
        api_key=raw_key,
    )


@router.get(
    "/me",
    response_model=CompanyPublic,
    summary="Get the authenticated company's profile",
    description="Returns the profile of the company associated with the provided API key.",
)
async def get_my_company(
    company: Company = Depends(get_current_company),
) -> CompanyPublic:
    return company


@router.post(
    "/me/rotate-key",
    response_model=ApiKeyRotateResponse,
    status_code=status.HTTP_200_OK,
    summary="Rotate the API key for the authenticated company",
    description=(
        "Generates a new API key and immediately invalidates the current one. "
        "The new key is returned once in plaintext — store it immediately. "
        "All existing sessions using the old key will receive 401 on the next request."
    ),
)
async def rotate_company_key(
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
) -> ApiKeyRotateResponse:
    new_raw_key = await rotate_api_key(db, company)
    return ApiKeyRotateResponse(
        id=company.id,
        api_key=new_raw_key,
        message=(
            "API key rotated successfully. "
            "Your previous key is now invalid. "
            "Update all integrations immediately."
        ),
    )
