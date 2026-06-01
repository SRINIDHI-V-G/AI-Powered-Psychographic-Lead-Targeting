from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
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
    company = await create_company(db, data)
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
