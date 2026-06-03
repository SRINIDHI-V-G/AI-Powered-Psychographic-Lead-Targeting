"""
Phase H — Gap-fix verification test suite.

Coverage:
  GAP 1: Celery worker startup — discovery_tasks.py
    - discovery_tasks module is importable
    - run_discovery_task exists and is in the "discovery" queue
    - celery_app.conf.include contains discovery_tasks
    - celery_app imports without ImportError

  GAP 2: Router dispatch wiring
    - submit_product calls dispatch(), not background_tasks.add_task() directly
    - restart_pipeline calls dispatch(), not background_tasks.add_task() directly
    - dispatch() routes each restart step to the correct stage
    - USE_CELERY=True → dispatch calls Celery .delay()
    - USE_CELERY=False with BackgroundTasks → dispatch calls background_tasks.add_task()
    - dispatch() maps include "discovery" stage

Run:
  cd backend && pytest tests/test_phase_h.py -v
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_NOW = datetime.now(timezone.utc)
_COMPANY_ID = uuid.uuid4()
_PRODUCT_ID = uuid.uuid4()
RAW_KEY = "h" * 64
AUTH = {"X-API-Key": RAW_KEY}

_VALID_PRODUCT = {
    "name": "Premium Sofa",
    "description": "A handcrafted luxury sofa with Italian full-grain leather.",
    "category": "Furniture",
    "price_range": "premium",
    "target_location": "Chennai",
}


def _make_company():
    c = MagicMock()
    c.id = _COMPANY_ID
    c.name = "Test Co"
    c.email = "test@co.com"
    c.industry = "Furniture"
    c.website = None
    c.description = None
    c.is_active = True
    c.api_key = hashlib.sha256(RAW_KEY.encode()).hexdigest()
    c.created_at = _NOW
    c.updated_at = _NOW
    return c


def _make_product(status: str = "failed", step: int = 2):
    p = MagicMock()
    p.id = _PRODUCT_ID
    p.company_id = _COMPANY_ID
    p.name = "Premium Sofa"
    p.description = "Luxury sofa for modern living spaces."
    p.category = "Furniture"
    p.subcategory = None
    p.price_range = "premium"
    p.target_location = "Chennai"
    p.target_city = "Chennai"
    p.target_country = "India"
    p.keywords = []
    p.enrichment_status = None
    p.error_message = None
    p.pipeline_step = step
    p.created_at = _NOW
    p.updated_at = _NOW
    from app.models.product import ProductStatus
    p.status = ProductStatus(status)
    return p


def _auth_ok():
    return patch(
        "app.dependencies.get_company_by_api_key",
        new_callable=AsyncMock,
        return_value=_make_company(),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# GAP 1 — discovery_tasks.py exists and is correct
# ═══════════════════════════════════════════════════════════════════════════════

class TestDiscoveryTasksModule:

    def test_discovery_tasks_importable(self):
        """discovery_tasks.py must import without error."""
        import app.workers.tasks.discovery_tasks as m
        assert m is not None

    def test_run_discovery_task_exists(self):
        import app.workers.tasks.discovery_tasks as m
        assert hasattr(m, "run_discovery_task")

    def test_run_discovery_task_queue_is_discovery(self):
        import app.workers.tasks.discovery_tasks as m
        assert m.run_discovery_task.queue == "discovery"

    def test_run_discovery_task_acks_late(self):
        import app.workers.tasks.discovery_tasks as m
        assert m.run_discovery_task.acks_late is True

    def test_run_discovery_task_max_retries(self):
        import app.workers.tasks.discovery_tasks as m
        assert m.run_discovery_task.max_retries == 2


class TestCeleryAppIncludes:

    def test_celery_app_imports_without_error(self):
        """celery_app must import cleanly — this was the root cause of GAP 1."""
        from app.workers.celery_app import celery_app
        assert celery_app is not None

    def test_celery_app_includes_discovery_tasks(self):
        from app.workers.celery_app import celery_app
        assert "app.workers.tasks.discovery_tasks" in celery_app.conf.include

    def test_celery_app_discovery_queue_route(self):
        from app.workers.celery_app import celery_app
        routes = celery_app.conf.task_routes
        assert "app.workers.tasks.discovery_tasks.*" in routes
        assert routes["app.workers.tasks.discovery_tasks.*"]["queue"] == "discovery"


# ═══════════════════════════════════════════════════════════════════════════════
# GAP 2a — dispatch maps include "discovery"
# ═══════════════════════════════════════════════════════════════════════════════

class TestDispatchMapsIncludeDiscovery:

    def test_discovery_in_async_functions_map(self):
        from app.workers.dispatch import _ASYNC_FUNCTIONS
        assert "discovery" in _ASYNC_FUNCTIONS

    def test_discovery_async_function_points_to_service(self):
        from app.workers.dispatch import _ASYNC_FUNCTIONS
        mod_path, fn_name = _ASYNC_FUNCTIONS["discovery"]
        assert mod_path == "app.services.discovery_service"
        assert fn_name == "start_discovery_background"

    def test_discovery_in_celery_tasks_map(self):
        from app.workers.dispatch import _CELERY_TASKS
        assert "discovery" in _CELERY_TASKS

    def test_discovery_celery_task_points_to_correct_module(self):
        from app.workers.dispatch import _CELERY_TASKS
        mod_path, task_name = _CELERY_TASKS["discovery"]
        assert mod_path == "app.workers.tasks.discovery_tasks"
        assert task_name == "run_discovery_task"


# ═══════════════════════════════════════════════════════════════════════════════
# GAP 2b — submit_product routes through dispatch()
# Patch at app.routers.products.dispatch (where the name is USED, not defined).
# ═══════════════════════════════════════════════════════════════════════════════

class TestSubmitProductUsesDispatch:

    def test_submit_product_calls_dispatch_with_motivations_stage(self, client):
        """POST /products must call dispatch('motivations', ...) — not add_task directly."""
        product = _make_product(status="pending", step=0)
        with _auth_ok():
            with patch("app.routers.products.create_product", new_callable=AsyncMock, return_value=product):
                with patch("app.routers.products.dispatch") as mock_dispatch:
                    resp = client.post("/api/v1/products/", json=_VALID_PRODUCT, headers=AUTH)
        assert resp.status_code == 201
        mock_dispatch.assert_called_once()
        stage = mock_dispatch.call_args[0][0]
        product_id_arg = mock_dispatch.call_args[0][1]
        assert stage == "motivations"
        assert product_id_arg == str(product.id)

    def test_submit_product_passes_background_tasks_to_dispatch(self, client):
        """dispatch() must receive a background_tasks keyword arg from the router."""
        from fastapi import BackgroundTasks
        product = _make_product(status="pending", step=0)
        with _auth_ok():
            with patch("app.routers.products.create_product", new_callable=AsyncMock, return_value=product):
                with patch("app.routers.products.dispatch") as mock_dispatch:
                    client.post("/api/v1/products/", json=_VALID_PRODUCT, headers=AUTH)
        kwargs = mock_dispatch.call_args[1]
        assert "background_tasks" in kwargs
        assert isinstance(kwargs["background_tasks"], BackgroundTasks)


# ═══════════════════════════════════════════════════════════════════════════════
# GAP 2c — restart_pipeline routes through dispatch()
# ═══════════════════════════════════════════════════════════════════════════════

class TestRestartPipelineUsesDispatch:

    def _restart(self, client, product_id=_PRODUCT_ID):
        return client.post(f"/api/v1/products/{product_id}/restart", headers=AUTH)

    def test_restart_calls_dispatch_not_add_task_directly(self, client):
        """restart_pipeline must go through dispatch(), not background_tasks.add_task()."""
        product = _make_product(status="failed", step=2)
        with _auth_ok():
            with patch("app.routers.products.get_product_by_id", new_callable=AsyncMock, return_value=product):
                with patch("app.routers.products.dispatch") as mock_dispatch:
                    resp = self._restart(client)
        assert resp.status_code == 202
        mock_dispatch.assert_called_once()

    def test_restart_step_0_dispatches_motivations(self, client):
        product = _make_product(status="failed", step=0)
        with _auth_ok():
            with patch("app.routers.products.get_product_by_id", new_callable=AsyncMock, return_value=product):
                with patch("app.routers.products.dispatch") as mock_dispatch:
                    resp = self._restart(client)
        assert resp.status_code == 202
        assert mock_dispatch.call_args[0][0] == "motivations"

    def test_restart_step_1_dispatches_motivations(self, client):
        product = _make_product(status="failed", step=1)
        with _auth_ok():
            with patch("app.routers.products.get_product_by_id", new_callable=AsyncMock, return_value=product):
                with patch("app.routers.products.dispatch") as mock_dispatch:
                    resp = self._restart(client)
        assert resp.status_code == 202
        assert mock_dispatch.call_args[0][0] == "motivations"

    def test_restart_step_2_dispatches_nlp(self, client):
        product = _make_product(status="failed", step=2)
        with _auth_ok():
            with patch("app.routers.products.get_product_by_id", new_callable=AsyncMock, return_value=product):
                with patch("app.routers.products.dispatch") as mock_dispatch:
                    resp = self._restart(client)
        assert resp.status_code == 202
        assert mock_dispatch.call_args[0][0] == "nlp"

    def test_restart_step_3_dispatches_nlp(self, client):
        product = _make_product(status="failed", step=3)
        with _auth_ok():
            with patch("app.routers.products.get_product_by_id", new_callable=AsyncMock, return_value=product):
                with patch("app.routers.products.dispatch") as mock_dispatch:
                    resp = self._restart(client)
        assert resp.status_code == 202
        assert mock_dispatch.call_args[0][0] == "nlp"

    def test_restart_step_5_dispatches_ocean(self, client):
        product = _make_product(status="failed", step=5)
        with _auth_ok():
            with patch("app.routers.products.get_product_by_id", new_callable=AsyncMock, return_value=product):
                with patch("app.routers.products.dispatch") as mock_dispatch:
                    resp = self._restart(client)
        assert resp.status_code == 202
        assert mock_dispatch.call_args[0][0] == "ocean"

    def test_restart_step_6_dispatches_matching(self, client):
        product = _make_product(status="failed", step=6)
        with _auth_ok():
            with patch("app.routers.products.get_product_by_id", new_callable=AsyncMock, return_value=product):
                with patch("app.routers.products.dispatch") as mock_dispatch:
                    resp = self._restart(client)
        assert resp.status_code == 202
        assert mock_dispatch.call_args[0][0] == "matching"

    def test_restart_passes_background_tasks_to_dispatch(self, client):
        """dispatch() must receive background_tasks kwarg from restart_pipeline."""
        from fastapi import BackgroundTasks
        product = _make_product(status="failed", step=2)
        with _auth_ok():
            with patch("app.routers.products.get_product_by_id", new_callable=AsyncMock, return_value=product):
                with patch("app.routers.products.dispatch") as mock_dispatch:
                    self._restart(client)
        kwargs = mock_dispatch.call_args[1]
        assert "background_tasks" in kwargs
        assert isinstance(kwargs["background_tasks"], BackgroundTasks)


# ═══════════════════════════════════════════════════════════════════════════════
# GAP 2d — USE_CELERY=True / False routing (unit tests on dispatch directly)
# ═══════════════════════════════════════════════════════════════════════════════

class TestDispatchCeleryRouting:

    def test_use_celery_false_uses_background_tasks(self):
        """USE_CELERY=False + background_tasks provided → background_tasks.add_task()."""
        from app.workers.dispatch import dispatch
        from fastapi import BackgroundTasks

        bt = MagicMock(spec=BackgroundTasks)
        with patch("app.workers.dispatch.settings") as mock_settings:
            mock_settings.celery_enabled.return_value = False
            with patch("importlib.import_module") as mock_import:
                mock_mod = MagicMock()
                mock_import.return_value = mock_mod
                dispatch("motivations", "test-product-id-1234", background_tasks=bt)
        bt.add_task.assert_called_once()

    def test_use_celery_true_calls_delay(self):
        """USE_CELERY=True → dispatch calls Celery task .delay(), not background_tasks."""
        from app.workers.dispatch import dispatch

        with patch("app.workers.dispatch.settings") as mock_settings:
            mock_settings.celery_enabled.return_value = True
            with patch("importlib.import_module") as mock_import:
                mock_mod = MagicMock()
                mock_import.return_value = mock_mod
                dispatch("motivations", "test-product-id-1234")
        mock_mod.generate_motivations_task.delay.assert_called_once_with(
            "test-product-id-1234"
        )

    def test_use_celery_true_does_not_use_background_tasks(self):
        """When Celery is enabled, background_tasks.add_task must NOT be called."""
        from app.workers.dispatch import dispatch
        from fastapi import BackgroundTasks

        bt = MagicMock(spec=BackgroundTasks)
        with patch("app.workers.dispatch.settings") as mock_settings:
            mock_settings.celery_enabled.return_value = True
            with patch("importlib.import_module") as mock_import:
                mock_mod = MagicMock()
                mock_import.return_value = mock_mod
                dispatch("motivations", "test-product-id-1234", background_tasks=bt)
        bt.add_task.assert_not_called()

    def test_use_celery_false_asyncio_path_when_no_background_tasks(self):
        """USE_CELERY=False + no background_tasks → asyncio.create_task() path."""
        from app.workers.dispatch import dispatch

        with patch("app.workers.dispatch.settings") as mock_settings:
            mock_settings.celery_enabled.return_value = False
            with patch("asyncio.create_task") as mock_create_task:
                with patch("importlib.import_module") as mock_import:
                    mock_mod = MagicMock()
                    mock_import.return_value = mock_mod
                    dispatch("nlp", "test-product-id-1234")
        mock_create_task.assert_called_once()
