"""
Pipeline task dispatcher.

Single module for firing any pipeline stage. Abstracts over:
  - Celery (.delay() when USE_CELERY=True and Redis is available)
  - asyncio.create_task (lightweight, in-process, same event loop)
  - FastAPI BackgroundTasks (for router-level dispatch)

Usage from routers (with BackgroundTasks handle):
    from app.workers.dispatch import dispatch
    dispatch("motivations", product_id=str(product.id), background_tasks=bt)

Usage from services (auto-chain, no BackgroundTasks handle):
    from app.workers.dispatch import dispatch
    dispatch("nlp", product_id=str(product.id))

The caller never needs to know whether Celery or asyncio runs the task.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import BackgroundTasks

from app.config import settings

logger = logging.getLogger(__name__)

# Lazy import map to avoid circular imports at module load time.
# Each key is a logical stage name; value is a (module, async_fn_name) pair.
_ASYNC_FUNCTIONS: dict[str, tuple[str, str]] = {
    "motivations":    ("app.services.motivation_service",        "generate_motivations_background"),
    "product_ocean":  ("app.services.product_ocean_service",     "generate_product_ocean_background"),
    "similar_products": ("app.services.product_similarity_service", "generate_similar_products_background"),
    "discovery":      ("app.services.discovery_service",         "start_discovery_background"),
    "nlp":            ("app.services.nlp_service",               "start_nlp_background"),
    "ocean":          ("app.services.ocean_service",             "start_ocean_background"),
    "matching":       ("app.services.matching_service",          "start_matching_background"),
    "handles":        ("app.services.handle_service",            "generate_handles_background"),
}

# Celery task map: same keys, resolved lazily.
_CELERY_TASKS: dict[str, tuple[str, str]] = {
    "motivations":    ("app.workers.tasks.product_tasks",     "generate_motivations_task"),
    "product_ocean":  ("app.workers.tasks.product_ocean_tasks", "run_product_ocean_task"),
    "similar_products": ("app.workers.tasks.similarity_tasks", "run_similarity_task"),
    "discovery":      ("app.workers.tasks.discovery_tasks",   "run_discovery_task"),
    "nlp":            ("app.workers.tasks.nlp_tasks",         "run_nlp_task"),
    "ocean":          ("app.workers.tasks.scoring_tasks",     "run_ocean_scoring_task"),
    "matching":       ("app.workers.tasks.matching_tasks",    "run_matching_task"),
    "handles":        ("app.workers.tasks.handle_tasks",      "run_handle_task"),
}


def dispatch(
    stage: str,
    product_id: str,
    *extra_args: Any,
    background_tasks: BackgroundTasks | None = None,
) -> None:
    """
    Dispatch a pipeline stage for the given product_id.

    Priority:
      1. Celery (.delay()) if celery_enabled()
      2. BackgroundTasks if a handle is provided (router context)
      3. asyncio.create_task (service auto-chain context)

    Parameters
    ----------
    stage          : one of "motivations", "nlp", "ocean", "matching"
    product_id     : str UUID of the product
    *extra_args    : additional positional args forwarded to the task/function
    background_tasks : FastAPI BackgroundTasks handle (optional)
    """
    if stage not in _ASYNC_FUNCTIONS:
        raise ValueError(f"Unknown pipeline stage: {stage!r}. Valid: {list(_ASYNC_FUNCTIONS)}")

    if settings.celery_enabled():
        _dispatch_celery(stage, product_id, *extra_args)
    elif background_tasks is not None:
        _dispatch_background_tasks(stage, product_id, *extra_args, background_tasks=background_tasks)
    else:
        _dispatch_asyncio(stage, product_id, *extra_args)


# ── Private helpers ───────────────────────────────────────────────────────────

def _dispatch_celery(stage: str, product_id: str, *extra_args: Any) -> None:
    mod_path, task_name = _CELERY_TASKS[stage]
    import importlib
    mod = importlib.import_module(mod_path)
    task = getattr(mod, task_name)
    task.delay(product_id, *extra_args)
    logger.info("Dispatched Celery task %s for product %s", task_name, product_id[:8])


def _dispatch_background_tasks(
    stage: str,
    product_id: str,
    *extra_args: Any,
    background_tasks: BackgroundTasks,
) -> None:
    mod_path, fn_name = _ASYNC_FUNCTIONS[stage]
    import importlib
    mod = importlib.import_module(mod_path)
    fn = getattr(mod, fn_name)
    background_tasks.add_task(fn, product_id, *extra_args)
    logger.info("Dispatched BackgroundTask %s for product %s", fn_name, product_id[:8])


def _dispatch_asyncio(stage: str, product_id: str, *extra_args: Any) -> None:
    mod_path, fn_name = _ASYNC_FUNCTIONS[stage]
    import importlib
    mod = importlib.import_module(mod_path)
    fn = getattr(mod, fn_name)
    asyncio.create_task(fn(product_id, *extra_args))
    logger.info("Dispatched asyncio task %s for product %s", fn_name, product_id[:8])
