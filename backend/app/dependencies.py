from fastapi import Header, HTTPException, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.company import Company
from app.crud.company import get_company_by_api_key


async def get_current_company(
    x_api_key: str = Header(..., description="Your company API key from registration"),
    db: AsyncSession = Depends(get_db),
) -> Company:
    company = await get_company_by_api_key(db, x_api_key)
    if not company:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key.",
        )
    return company
