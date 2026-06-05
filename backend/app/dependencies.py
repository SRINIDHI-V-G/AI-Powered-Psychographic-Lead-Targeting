from fastapi import Header, HTTPException, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.company import Company
from app.crud.company import get_company_by_api_key

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or missing API key.",
    headers={"WWW-Authenticate": "ApiKey"},
)


async def get_current_company(
    x_api_key: str | None = Header(
        None,
        description="Company API key returned at registration (X-API-Key header).",
    ),
    db: AsyncSession = Depends(get_db),
) -> Company:
    if not x_api_key or not x_api_key.strip():
        raise _UNAUTHORIZED

    company = await get_company_by_api_key(db, x_api_key.strip())
    if company is None:
        raise _UNAUTHORIZED

    if not company.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Company account is inactive.",
        )

    return company
