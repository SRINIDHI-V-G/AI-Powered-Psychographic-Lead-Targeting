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
from app.workers.dispatch import dispatch

router = APIRouter(prefix="/products", tags=["Products"])


@router.post(
    "",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a new product (no trailing slash)",
    include_in_schema=False,
)
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
    dispatch("motivations", str(product.id), background_tasks=background_tasks)
    return product


@router.get(
    "",
    response_model=list[ProductResponse],
    summary="List all products for this company (no trailing slash)",
    include_in_schema=False,
)
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
    "/{product_id}/restart",
    response_model=ProductStatusResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Restart the pipeline from the last completed checkpoint",
    description=(
        "Detects where the pipeline stalled or failed and re-fires the appropriate "
        "stage. Useful after transient errors (Ollama timeout, Reddit rate-limit, etc.).\n\n"
        "Restart map:\n"
        "  pipeline_step 0–1  → re-run motivation generation\n"
        "  pipeline_step 2    → re-run NLP (motivations exist)\n"
        "  pipeline_step 3–4  → re-run NLP batch\n"
        "  pipeline_step 5    → re-run OCEAN scoring\n"
        "  pipeline_step 6+   → re-run matching + ranking\n\n"
        "Only allowed when product status is 'failed'. "
        "To restart from scratch, use POST /products/{id}/motivations/regenerate."
    ),
)
async def restart_pipeline(
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

    if product.status != ProductStatus.failed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Product is in status '{product.status.value}' — restart is only "
                "allowed when status is 'failed'. "
                "Use POST /products/{id}/motivations/regenerate to start over."
            ),
        )

    step = product.pipeline_step
    product.error_message = None

    if step <= 1:
        # step 0–1: motivations not complete — restart from scratch
        product.status = ProductStatus.pending
        product.pipeline_step = 0
        await db.commit()
        await db.refresh(product)
        dispatch("motivations", str(product.id), background_tasks=background_tasks)

    elif step == 2:
        # step 2: motivations exist — re-derive product OCEAN
        product.status = ProductStatus.motivations_generated
        await db.commit()
        await db.refresh(product)
        dispatch("product_ocean", str(product.id), background_tasks=background_tasks)

    elif step == 3:
        # step 3: product OCEAN exists — re-discover similar products
        product.status = ProductStatus.product_ocean_ready
        await db.commit()
        await db.refresh(product)
        dispatch("similar_products", str(product.id), background_tasks=background_tasks)

    elif step in (4, 5):
        # step 4: similar products done, discovery not started
        # step 5: discovery complete — run NLP on collected users
        product.status = ProductStatus.similar_products_found
        await db.commit()
        await db.refresh(product)
        dispatch("nlp", str(product.id), background_tasks=background_tasks)

    elif step == 6:
        # step 6: NLP in progress or failed — re-run NLP
        # process_user_nlp skips already-processed users, then auto-triggers OCEAN
        product.status = ProductStatus.nlp_processing
        await db.commit()
        await db.refresh(product)
        dispatch("nlp", str(product.id), background_tasks=background_tasks)

    elif step == 7:
        # step 7: NLP complete, OCEAN failed — re-run OCEAN scoring
        product.status = ProductStatus.ocean_scoring
        await db.commit()
        await db.refresh(product)
        dispatch("ocean", str(product.id), background_tasks=background_tasks)

    else:
        # step 8+: OCEAN complete, matching/ranking failed — re-run matching
        product.status = ProductStatus.ocean_scoring
        await db.commit()
        await db.refresh(product)
        dispatch("matching", str(product.id), background_tasks=background_tasks)

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
