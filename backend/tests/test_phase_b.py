"""
Phase B — Discovery API test suite.

Patching rule: patch where the name is USED (router import), not defined.
  app.routers.discovery.get_product_by_id   ← correct
  app.crud.product.get_product_by_id        ← wrong

Run:
  cd backend && pytest tests/test_phase_b.py -v
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# client fixture from conftest.py

_NOW = datetime.now(timezone.utc)
_PRODUCT_ID = uuid.uuid4()
_JOB_ID = uuid.uuid4()
_USER_ID = uuid.uuid4()
RAW_KEY = "b" * 64
AUTH = {"X-API-Key": RAW_KEY}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_company():
    import hashlib
    c = MagicMock()
    c.id = uuid.uuid4()
    c.api_key = hashlib.sha256(RAW_KEY.encode()).hexdigest()
    c.is_active = True
    return c


def _make_product(status: str = "motivations_generated"):
    p = MagicMock()
    p.id = _PRODUCT_ID
    p.name = "Premium Sofa"
    status_mock = MagicMock()
    status_mock.value = status
    p.status = status_mock
    p.pipeline_step = 2
    p.error_message = None
    p.enrichment_status = None
    p.category = "Furniture"
    p.subcategory = None
    p.price_range = "premium"
    p.target_location = "Chennai"
    p.target_city = "Chennai"
    p.target_country = "India"
    p.keywords = []
    p.description = "A luxury sofa for modern living spaces in Chennai."
    p.company_id = uuid.uuid4()
    p.created_at = _NOW
    p.updated_at = _NOW
    return p


def _make_job(status: str = "pending"):
    j = MagicMock()
    j.id = _JOB_ID
    j.product_id = _PRODUCT_ID
    j.status = status
    j.provider_name = "mock"
    j.sources = ["reddit"]
    j.max_users = 50
    j.users_discovered = 0
    j.users_content_collected = 0
    j.search_config = {}
    j.error_message = None
    j.started_at = None
    j.completed_at = None
    j.created_at = _NOW
    return j


def _make_user():
    u = MagicMock()
    u.id = _USER_ID
    u.discovery_job_id = _JOB_ID
    u.product_id = _PRODUCT_ID
    u.platform = "reddit"
    u.source_provider = "mock"
    u.platform_user_id = "uid_123"
    u.username = "mock_user_1"
    u.display_name = "Mock User"
    u.bio = "I love interior design."
    u.location = "Chennai"
    u.location_confidence = "inferred"
    u.follower_count = 1500
    u.post_count = None
    u.profile_url = "https://reddit.com/u/mock_user_1"
    u.raw_profile = {}
    u.nlp_processed = False
    u.ocean_scored = False
    u.content_collected = True
    u.created_at = _NOW
    return u


def _make_content():
    item = MagicMock()
    item.id = uuid.uuid4()
    item.user_id = _USER_ID
    item.content_type = "post"
    item.content_text = "Just redecorated my living room with a new leather sofa."
    item.source_url = "https://reddit.com/r/interiordesign/abc"
    item.engagement = 42
    item.posted_at = _NOW
    item.created_at = _NOW
    return item


def _auth_ok():
    return patch("app.dependencies.get_company_by_api_key",
                 new_callable=AsyncMock, return_value=_make_company())


def _auth_fail():
    return patch("app.dependencies.get_company_by_api_key",
                 new_callable=AsyncMock, return_value=None)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. MOCK DISCOVERY PROVIDER — unit tests (no HTTP, no DB)
# ═══════════════════════════════════════════════════════════════════════════════

class TestMockDiscoveryProvider:

    @pytest.fixture
    def provider(self):
        from app.ml.discovery.mock_provider import MockDiscoveryProvider
        return MockDiscoveryProvider(delay_ms=0)

    @pytest.mark.asyncio
    async def test_health_check_returns_ok(self, provider):
        result = await provider.health_check()
        assert result["ok"] is True
        assert result["provider"] == "mock"

    @pytest.mark.asyncio
    async def test_discover_users_returns_list(self, provider):
        users = await provider.discover_users(
            keywords=["interior design", "luxury sofa"],
            target_city="Chennai",
            max_users=5,
            search_config={},
        )
        assert isinstance(users, list)
        assert len(users) > 0

    @pytest.mark.asyncio
    async def test_discover_users_respects_max_users(self, provider):
        users = await provider.discover_users(
            keywords=["sofa"], target_city=None, max_users=3, search_config={}
        )
        assert len(users) <= 3

    @pytest.mark.asyncio
    async def test_discovered_users_have_required_fields(self, provider):
        from app.ml.discovery.base import RawDiscoveredUser
        users = await provider.discover_users(
            keywords=["design"], target_city=None, max_users=5, search_config={}
        )
        for u in users:
            assert isinstance(u, RawDiscoveredUser)
            assert u.username
            assert u.platform
            assert u.source_provider

    @pytest.mark.asyncio
    async def test_collect_content_returns_list(self, provider):
        users = await provider.discover_users(
            keywords=["sofa"], target_city=None, max_users=1, search_config={}
        )
        assert users
        items = await provider.collect_content(users[0], max_items=5)
        assert isinstance(items, list)

    @pytest.mark.asyncio
    async def test_collect_content_respects_max_items(self, provider):
        users = await provider.discover_users(
            keywords=["sofa"], target_city=None, max_users=1, search_config={}
        )
        items = await provider.collect_content(users[0], max_items=3)
        assert len(items) <= 3

    @pytest.mark.asyncio
    async def test_content_items_have_required_fields(self, provider):
        from app.ml.discovery.base import ContentItem
        users = await provider.discover_users(
            keywords=["sofa"], target_city=None, max_users=1, search_config={}
        )
        items = await provider.collect_content(users[0], max_items=5)
        for item in items:
            assert isinstance(item, ContentItem)
            assert item.content_type in ("bio", "post", "comment")
            assert item.content_text

    def test_provider_name_and_platform(self, provider):
        assert provider.name == "mock"
        assert provider.platform == "mock"

    def test_supported_categories_is_wildcard(self, provider):
        assert provider.supported_categories == ["*"]


# ═══════════════════════════════════════════════════════════════════════════════
# 2. PROVIDER HEALTH ENDPOINT (unauthenticated)
# ═══════════════════════════════════════════════════════════════════════════════

class TestProviderHealthEndpoint:

    def test_provider_status_returns_200(self, client):
        resp = client.get("/api/v1/discovery/provider/status")
        assert resp.status_code == 200

    def test_provider_status_has_required_fields(self, client):
        body = client.get("/api/v1/discovery/provider/status").json()
        assert "ok" in body
        assert "provider" in body
        assert "mock_mode" in body

    def test_provider_status_requires_no_auth(self, client):
        resp = client.get("/api/v1/discovery/provider/status")
        assert resp.status_code != 401


# ═══════════════════════════════════════════════════════════════════════════════
# 3. POST /products/{id}/discovery/start
# ═══════════════════════════════════════════════════════════════════════════════

_BODY = {"max_users": 20, "search_config": {}}


class TestStartDiscovery:

    def test_start_discovery_returns_202(self, client):
        job = _make_job()
        with _auth_ok():
            with patch("app.routers.discovery.get_product_by_id", new_callable=AsyncMock, return_value=_make_product()):
                with patch("app.routers.discovery.create_discovery_job", new_callable=AsyncMock, return_value=job):
                    with patch("app.routers.discovery.start_discovery_background"):
                        resp = client.post(
                            f"/api/v1/products/{_PRODUCT_ID}/discovery/start",
                            json=_BODY, headers=AUTH,
                        )
        assert resp.status_code == 202

    def test_start_discovery_returns_job_id(self, client):
        job = _make_job()
        with _auth_ok():
            with patch("app.routers.discovery.get_product_by_id", new_callable=AsyncMock, return_value=_make_product()):
                with patch("app.routers.discovery.create_discovery_job", new_callable=AsyncMock, return_value=job):
                    with patch("app.routers.discovery.start_discovery_background"):
                        resp = client.post(
                            f"/api/v1/products/{_PRODUCT_ID}/discovery/start",
                            json=_BODY, headers=AUTH,
                        )
        assert resp.json()["id"] == str(_JOB_ID)

    def test_unknown_product_returns_404(self, client):
        with _auth_ok():
            with patch("app.routers.discovery.get_product_by_id", new_callable=AsyncMock, return_value=None):
                resp = client.post(
                    f"/api/v1/products/{uuid.uuid4()}/discovery/start",
                    json=_BODY, headers=AUTH,
                )
        assert resp.status_code == 404

    def test_product_not_ready_returns_422(self, client):
        """'pending' status must be rejected — discovery requires motivations_generated."""
        with _auth_ok():
            with patch("app.routers.discovery.get_product_by_id",
                       new_callable=AsyncMock, return_value=_make_product(status="pending")):
                resp = client.post(
                    f"/api/v1/products/{_PRODUCT_ID}/discovery/start",
                    json=_BODY, headers=AUTH,
                )
        assert resp.status_code == 422

    def test_no_auth_returns_401(self, client):
        with _auth_fail():
            resp = client.post(
                f"/api/v1/products/{_PRODUCT_ID}/discovery/start",
                json=_BODY,
            )
        assert resp.status_code == 401

    def test_discovery_allowed_for_ranked_status(self, client):
        job = _make_job()
        with _auth_ok():
            with patch("app.routers.discovery.get_product_by_id",
                       new_callable=AsyncMock, return_value=_make_product(status="ranked")):
                with patch("app.routers.discovery.create_discovery_job", new_callable=AsyncMock, return_value=job):
                    with patch("app.routers.discovery.start_discovery_background"):
                        resp = client.post(
                            f"/api/v1/products/{_PRODUCT_ID}/discovery/start",
                            json=_BODY, headers=AUTH,
                        )
        assert resp.status_code == 202


# ═══════════════════════════════════════════════════════════════════════════════
# 4. GET /products/{id}/discovery/jobs
# ═══════════════════════════════════════════════════════════════════════════════

class TestListDiscoveryJobs:

    def test_returns_job_list(self, client):
        job = _make_job()
        with _auth_ok():
            with patch("app.routers.discovery.get_product_by_id", new_callable=AsyncMock, return_value=_make_product()):
                with patch("app.routers.discovery.get_discovery_jobs_for_product",
                           new_callable=AsyncMock, return_value=[job]):
                    resp = client.get(f"/api/v1/products/{_PRODUCT_ID}/discovery/jobs", headers=AUTH)
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_empty_list_when_no_jobs(self, client):
        with _auth_ok():
            with patch("app.routers.discovery.get_product_by_id", new_callable=AsyncMock, return_value=_make_product()):
                with patch("app.routers.discovery.get_discovery_jobs_for_product",
                           new_callable=AsyncMock, return_value=[]):
                    resp = client.get(f"/api/v1/products/{_PRODUCT_ID}/discovery/jobs", headers=AUTH)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_product_not_found_returns_404(self, client):
        with _auth_ok():
            with patch("app.routers.discovery.get_product_by_id", new_callable=AsyncMock, return_value=None):
                resp = client.get(f"/api/v1/products/{uuid.uuid4()}/discovery/jobs", headers=AUTH)
        assert resp.status_code == 404

    def test_no_auth_returns_401(self, client):
        with _auth_fail():
            resp = client.get(f"/api/v1/products/{_PRODUCT_ID}/discovery/jobs")
        assert resp.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════════
# 5. GET /products/{id}/discovery/jobs/{job_id}
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetDiscoveryJob:

    def test_returns_job_detail(self, client):
        job = _make_job()
        with _auth_ok():
            with patch("app.routers.discovery.get_product_by_id", new_callable=AsyncMock, return_value=_make_product()):
                with patch("app.routers.discovery.get_discovery_job", new_callable=AsyncMock, return_value=job):
                    resp = client.get(
                        f"/api/v1/products/{_PRODUCT_ID}/discovery/jobs/{_JOB_ID}",
                        headers=AUTH,
                    )
        assert resp.status_code == 200
        assert resp.json()["id"] == str(_JOB_ID)

    def test_unknown_job_returns_404(self, client):
        with _auth_ok():
            with patch("app.routers.discovery.get_product_by_id", new_callable=AsyncMock, return_value=_make_product()):
                with patch("app.routers.discovery.get_discovery_job", new_callable=AsyncMock, return_value=None):
                    resp = client.get(
                        f"/api/v1/products/{_PRODUCT_ID}/discovery/jobs/{uuid.uuid4()}",
                        headers=AUTH,
                    )
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# 6. GET /products/{id}/discovery/users
# ═══════════════════════════════════════════════════════════════════════════════

class TestListDiscoveredUsers:

    def test_returns_paginated_user_list(self, client):
        user = _make_user()
        with _auth_ok():
            with patch("app.routers.discovery.get_product_by_id", new_callable=AsyncMock, return_value=_make_product()):
                with patch("app.routers.discovery.get_discovery_jobs_for_product",
                           new_callable=AsyncMock, return_value=[]):
                    with patch("app.routers.discovery.get_discovered_users",
                               new_callable=AsyncMock, return_value=[user]):
                        with patch("app.routers.discovery.count_discovered_users",
                                   new_callable=AsyncMock, return_value=1):
                            resp = client.get(
                                f"/api/v1/products/{_PRODUCT_ID}/discovery/users",
                                headers=AUTH,
                            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert "users" in body

    def test_pagination_params_accepted(self, client):
        with _auth_ok():
            with patch("app.routers.discovery.get_product_by_id", new_callable=AsyncMock, return_value=_make_product()):
                with patch("app.routers.discovery.get_discovery_jobs_for_product",
                           new_callable=AsyncMock, return_value=[]):
                    with patch("app.routers.discovery.get_discovered_users",
                               new_callable=AsyncMock, return_value=[]):
                        with patch("app.routers.discovery.count_discovered_users",
                                   new_callable=AsyncMock, return_value=0):
                            resp = client.get(
                                f"/api/v1/products/{_PRODUCT_ID}/discovery/users?page=2&limit=10",
                                headers=AUTH,
                            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["page"] == 2
        assert body["limit"] == 10

    def test_product_not_found_returns_404(self, client):
        with _auth_ok():
            with patch("app.routers.discovery.get_product_by_id", new_callable=AsyncMock, return_value=None):
                resp = client.get(
                    f"/api/v1/products/{uuid.uuid4()}/discovery/users",
                    headers=AUTH,
                )
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# 7. GET /products/{id}/discovery/users/{uid}/content
# ═══════════════════════════════════════════════════════════════════════════════

class TestUserContent:

    def test_returns_content_list(self, client):
        item = _make_content()
        with _auth_ok():
            with patch("app.routers.discovery.get_product_by_id", new_callable=AsyncMock, return_value=_make_product()):
                with patch("app.routers.discovery.get_user_content",
                           new_callable=AsyncMock, return_value=[item]):
                    resp = client.get(
                        f"/api/v1/products/{_PRODUCT_ID}/discovery/users/{_USER_ID}/content",
                        headers=AUTH,
                    )
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_returns_empty_list_for_uncollected_user(self, client):
        with _auth_ok():
            with patch("app.routers.discovery.get_product_by_id", new_callable=AsyncMock, return_value=_make_product()):
                with patch("app.routers.discovery.get_user_content",
                           new_callable=AsyncMock, return_value=[]):
                    resp = client.get(
                        f"/api/v1/products/{_PRODUCT_ID}/discovery/users/{_USER_ID}/content",
                        headers=AUTH,
                    )
        assert resp.status_code == 200
        assert resp.json() == []
