from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.dependencies import get_current_company
from app.models.company import Company
from app.schemas.company import CompanyCreate, CompanyPublic, CompanyResponse
from app.crud.company import create_company, get_company_by_email, get_all_companies

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


@router.get(
    "/",
    response_model=list[CompanyPublic],
    summary="List all registered companies",
)
async def list_companies(
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
) -> list[CompanyPublic]:
    return await get_all_companies(db, skip=skip, limit=limit)
