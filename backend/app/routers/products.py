from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.database import get_db
from app.dependencies import get_current_company
from app.models.company import Company
from app.models.product import ProductStatus
from app.schemas.product import ProductCreate, ProductResponse, ProductStatusResponse
from app.crud.product import create_product, get_products_by_company, get_product_by_id
from app.services.motivation_service import generate_motivations_background

router = APIRouter(prefix="/products", tags=["Products"])


@router.post(
    "/",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a new product",
    description=(
        "Creates the product and immediately starts motivation generation in the "
        "background via Ollama / Llama 3.1. "
        "Poll GET /products/{id}/status until status is 'motivations_generated', "
        "then call GET /products/{id}/motivations."
    ),
)
async def submit_product(
    data: ProductCreate,
    background_tasks: BackgroundTasks,
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
) -> ProductResponse:
    product = await create_product(db, data, company.id)
    background_tasks.add_task(generate_motivations_background, str(product.id))
    return product


@router.get(
    "/",
    response_model=list[ProductResponse],
    summary="List all products for this company",
)
async def list_products(
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
) -> list[ProductResponse]:
    return await get_products_by_company(db, company.id)


@router.get(
    "/{product_id}",
    response_model=ProductResponse,
    summary="Get a single product by ID",
)
async def get_product(
    product_id: UUID,
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
) -> ProductResponse:
    product = await get_product_by_id(db, product_id, company.id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product {product_id} not found.",
        )
    return product


@router.get(
    "/{product_id}/status",
    response_model=ProductStatusResponse,
    summary="Lightweight pipeline status poll",
    description=(
        "Returns only id, status, pipeline_step, error_message, and updated_at. "
        "Poll this every 3-5 seconds while waiting for motivation generation to complete."
    ),
)
async def get_product_status(
    product_id: UUID,
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
) -> ProductStatusResponse:
    product = await get_product_by_id(db, product_id, company.id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product {product_id} not found.",
        )
    return product


@router.post(
    "/{product_id}/motivations/regenerate",
    response_model=ProductStatusResponse,
    summary="Re-run motivation generation",
    description=(
        "Resets the product to 'pending' and re-fires the Ollama motivation generation "
        "pipeline. Any previously stored motivation categories are deleted during "
        "regeneration. Use this after editing the product description or after an error."
    ),
)
async def regenerate_motivations(
    product_id: UUID,
    background_tasks: BackgroundTasks,
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
) -> ProductStatusResponse:
    product = await get_product_by_id(db, product_id, company.id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product {product_id} not found.",
        )

    # Reset to pending so the service's status guard doesn't short-circuit.
    product.status = ProductStatus.pending
    product.pipeline_step = 0
    product.error_message = None
    await db.commit()
    await db.refresh(product)

    # force=True bypasses the pending-check inside the service, providing an
    # extra safety net in case of a race condition on status reset.
    background_tasks.add_task(
        generate_motivations_background, str(product.id), True
    )
    return product
