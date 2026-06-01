from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.database import get_db
from app.dependencies import get_current_company
from app.crud.motivation import get_motivations_by_product
from app.crud.product import get_product_by_id
from app.schemas.motivation import MotivationListOut

router = APIRouter(tags=["Motivations"])


@router.get(
    "/products/{product_id}/motivations",
    response_model=MotivationListOut,
    summary="Get motivation categories for a product",
    description=(
        "Returns the LLM-generated buyer motivation categories and their OCEAN profiles. "
        "Poll GET /products/{id} until status is 'motivations_generated' before calling this."
    ),
)
async def get_motivations(
    product_id: UUID,
    company=Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
) -> MotivationListOut:
    product = await get_product_by_id(db, product_id, company.id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product {product_id} not found.",
        )

    categories = await get_motivations_by_product(db, product_id)
    return MotivationListOut(
        product_id=product_id,
        total=len(categories),
        categories=categories,
    )
