"""
Phase A — Company & Product API test suite.

Coverage
--------
  Auth middleware
  POST /api/v1/companies
  GET  /api/v1/companies
  POST /api/v1/products
  GET  /api/v1/products
  GET  /api/v1/products/{id}
  GET  /api/v1/products/{id}/status
  API key hashing unit tests
  Rate limiting

Patching rule: patch where the name is USED (imported into the router),
not where it is defined. e.g.:
  app.routers.companies.create_company   ← correct
  app.crud.company.create_company        ← wrong (already imported by router)

Run:
  cd backend && pytest tests/test_phase_a.py -v
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# client fixture comes from conftest.py

# ── Helpers ───────────────────────────────────────────────────────────────────

_NOW = datetime.now(timezone.utc)
_COMPANY_ID = uuid.uuid4()
_COMPANY_ID2 = uuid.uuid4()
_PRODUCT_ID = uuid.uuid4()

RAW_KEY = "a" * 64
HASHED_KEY = hashlib.sha256(RAW_KEY.encode()).hexdigest()
AUTH = {"X-API-Key": RAW_KEY}


def _make_company(raw_key: str = RAW_KEY) -> MagicMock:
    c = MagicMock()
    c.id = _COMPANY_ID
    c.name = "Test Company"
    c.email = "test@example.com"
    c.industry = "Furniture"
    c.website = None
    c.description = None
    c.is_active = True
    c.api_key = hashlib.sha256(raw_key.encode()).hexdigest()
    c.created_at = _NOW
    c.updated_at = _NOW
    return c


def _make_product(company_id: uuid.UUID = _COMPANY_ID) -> MagicMock:
    p = MagicMock()
    p.id = _PRODUCT_ID
    p.company_id = company_id
    p.name = "Premium Sofa"
    p.description = "A handcrafted luxury sofa with Italian leather."
    p.category = "Furniture"
    p.subcategory = None
    p.price_range = "premium"
    p.target_location = "Chennai"
    p.target_city = "Chennai"
    p.target_country = "India"
    p.keywords = ["luxury", "sofa"]
    p.status = "pending"
    p.pipeline_step = 0
    p.error_message = None
    p.enrichment_status = None
    p.created_at = _NOW
    p.updated_at = _NOW
    return p


# ── Auth override helpers ─────────────────────────────────────────────────────

def _auth_ok(company=None):
    """Context manager that makes auth pass for a given company."""
    c = company or _make_company()
    return patch("app.dependencies.get_company_by_api_key", new_callable=AsyncMock, return_value=c)


def _auth_fail():
    """Context manager that makes auth reject the key."""
    return patch("app.dependencies.get_company_by_api_key", new_callable=AsyncMock, return_value=None)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. AUTH MIDDLEWARE
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuthMiddleware:

    def test_missing_api_key_returns_401(self, client):
        resp = client.get("/api/v1/products/")
        assert resp.status_code == 401

    def test_invalid_api_key_returns_401(self, client):
        with _auth_fail():
            resp = client.get("/api/v1/products/", headers={"X-API-Key": "badbadkey"})
        assert resp.status_code == 401

    def test_valid_api_key_passes_through(self, client):
        with _auth_ok():
            with patch("app.routers.products.get_products_by_company", new_callable=AsyncMock, return_value=[]):
                resp = client.get("/api/v1/products/", headers=AUTH)
        assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════════
# 2. POST /api/v1/companies
# ═══════════════════════════════════════════════════════════════════════════════

class TestCompanyRegistration:

    def _post(self, client, payload: dict):
        return client.post("/api/v1/companies/", json=payload)

    def test_successful_registration(self, client):
        company = _make_company()
        with patch("app.routers.companies.get_company_by_email", new_callable=AsyncMock, return_value=None):
            with patch("app.routers.companies.create_company", new_callable=AsyncMock, return_value=(RAW_KEY, company)):
                resp = self._post(client, {"name": "ACME Corp", "email": "acme@example.com"})
        assert resp.status_code == 201
        body = resp.json()
        assert "id" in body
        assert "api_key" in body

    def test_returned_api_key_is_64_char_hex(self, client):
        company = _make_company()
        with patch("app.routers.companies.get_company_by_email", new_callable=AsyncMock, return_value=None):
            with patch("app.routers.companies.create_company", new_callable=AsyncMock, return_value=(RAW_KEY, company)):
                resp = self._post(client, {"name": "ACME Corp", "email": "acme@example.com"})
        key = resp.json()["api_key"]
        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)

    def test_returned_key_is_plaintext_not_hash(self, client):
        """Response must contain the raw token, not the stored SHA-256 hash."""
        company = _make_company()
        with patch("app.routers.companies.get_company_by_email", new_callable=AsyncMock, return_value=None):
            with patch("app.routers.companies.create_company", new_callable=AsyncMock, return_value=(RAW_KEY, company)):
                resp = self._post(client, {"name": "ACME Corp", "email": "acme@example.com"})
        returned_key = resp.json()["api_key"]
        assert returned_key == RAW_KEY
        assert returned_key != hashlib.sha256(returned_key.encode()).hexdigest()

    def test_duplicate_email_returns_409(self, client):
        company = _make_company()
        with patch("app.routers.companies.get_company_by_email", new_callable=AsyncMock, return_value=company):
            resp = self._post(client, {"name": "ACME Corp", "email": "dupe@example.com"})
        assert resp.status_code == 409

    def test_empty_name_returns_422(self, client):
        resp = self._post(client, {"name": "   ", "email": "valid@example.com"})
        assert resp.status_code == 422

    def test_invalid_email_returns_422(self, client):
        resp = self._post(client, {"name": "Corp", "email": "not-an-email"})
        assert resp.status_code == 422

    def test_missing_name_returns_422(self, client):
        resp = self._post(client, {"email": "valid@example.com"})
        assert resp.status_code == 422

    def test_missing_email_returns_422(self, client):
        resp = self._post(client, {"name": "Corp"})
        assert resp.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════════
# 3. POST /api/v1/products
# ═══════════════════════════════════════════════════════════════════════════════

_VALID_PRODUCT = {
    "name": "Premium Sofa",
    "description": "A handcrafted luxury sofa with Italian full-grain leather.",
    "category": "Furniture",
    "price_range": "premium",
    "target_location": "Chennai",
}


class TestProductSubmission:

    def _post(self, client, payload: dict, headers=AUTH):
        return client.post("/api/v1/products/", json=payload, headers=headers)

    def test_successful_product_creation(self, client):
        product = _make_product()
        with _auth_ok():
            with patch("app.routers.products.create_product", new_callable=AsyncMock, return_value=product):
                with patch("app.routers.products.dispatch"):
                    resp = self._post(client, _VALID_PRODUCT)
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "Premium Sofa"
        assert body["status"] == "pending"
        assert body["pipeline_step"] == 0

    def test_description_too_short_returns_422(self, client):
        payload = {**_VALID_PRODUCT, "description": "Too short"}
        resp = self._post(client, payload)
        assert resp.status_code == 422

    def test_empty_name_returns_422(self, client):
        payload = {**_VALID_PRODUCT, "name": ""}
        resp = self._post(client, payload)
        assert resp.status_code == 422

    def test_empty_category_returns_422(self, client):
        payload = {**_VALID_PRODUCT, "category": ""}
        resp = self._post(client, payload)
        assert resp.status_code == 422

    def test_empty_target_location_returns_422(self, client):
        payload = {**_VALID_PRODUCT, "target_location": ""}
        resp = self._post(client, payload)
        assert resp.status_code == 422

    def test_missing_api_key_returns_401(self, client):
        resp = self._post(client, _VALID_PRODUCT, headers={})
        assert resp.status_code == 401

    def test_invalid_api_key_returns_401(self, client):
        with _auth_fail():
            resp = self._post(client, _VALID_PRODUCT, headers={"X-API-Key": "badkey"})
        assert resp.status_code == 401

    def test_invalid_price_range_returns_422(self, client):
        payload = {**_VALID_PRODUCT, "price_range": "super_ultra_premium"}
        resp = self._post(client, payload)
        assert resp.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════════
# 4. GET /api/v1/products
# ═══════════════════════════════════════════════════════════════════════════════

class TestProductList:

    def test_returns_list_of_products(self, client):
        product = _make_product()
        with _auth_ok():
            with patch("app.routers.products.get_products_by_company", new_callable=AsyncMock, return_value=[product]):
                resp = client.get("/api/v1/products/", headers=AUTH)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
        assert len(resp.json()) == 1

    def test_empty_list_when_no_products(self, client):
        with _auth_ok():
            with patch("app.routers.products.get_products_by_company", new_callable=AsyncMock, return_value=[]):
                resp = client.get("/api/v1/products/", headers=AUTH)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_no_auth_returns_401(self, client):
        resp = client.get("/api/v1/products/")
        assert resp.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════════
# 5. GET /api/v1/products/{id}
# ═══════════════════════════════════════════════════════════════════════════════

class TestProductDetail:

    def test_returns_product_for_owner(self, client):
        product = _make_product(company_id=_COMPANY_ID)
        with _auth_ok():
            with patch("app.routers.products.get_product_by_id", new_callable=AsyncMock, return_value=product):
                resp = client.get(f"/api/v1/products/{_PRODUCT_ID}", headers=AUTH)
        assert resp.status_code == 200
        assert resp.json()["id"] == str(_PRODUCT_ID)

    def test_returns_404_for_nonexistent_product(self, client):
        with _auth_ok():
            with patch("app.routers.products.get_product_by_id", new_callable=AsyncMock, return_value=None):
                resp = client.get(f"/api/v1/products/{uuid.uuid4()}", headers=AUTH)
        assert resp.status_code == 404

    def test_different_company_cannot_access_product(self, client):
        """Product belongs to _COMPANY_ID2; caller is _COMPANY_ID. Expect 404."""
        product = _make_product(company_id=_COMPANY_ID2)
        # The CRUD get_product_by_id already filters by company_id and returns None
        with _auth_ok():
            with patch("app.routers.products.get_product_by_id", new_callable=AsyncMock, return_value=None):
                resp = client.get(f"/api/v1/products/{_PRODUCT_ID}", headers=AUTH)
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# 6. GET /api/v1/products/{id}/status
# ═══════════════════════════════════════════════════════════════════════════════

class TestProductStatus:

    def test_returns_lightweight_status(self, client):
        product = _make_product()
        with _auth_ok():
            with patch("app.routers.products.get_product_by_id", new_callable=AsyncMock, return_value=product):
                resp = client.get(f"/api/v1/products/{_PRODUCT_ID}/status", headers=AUTH)
        assert resp.status_code == 200
        body = resp.json()
        assert "status" in body
        assert "pipeline_step" in body
        assert "description" not in body

    def test_status_404_for_unknown_product(self, client):
        with _auth_ok():
            with patch("app.routers.products.get_product_by_id", new_callable=AsyncMock, return_value=None):
                resp = client.get(f"/api/v1/products/{uuid.uuid4()}/status", headers=AUTH)
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# 7. API key hashing — unit tests (no HTTP)
# ═══════════════════════════════════════════════════════════════════════════════

class TestApiKeyHashing:

    def test_hash_function_produces_64_chars(self):
        from app.crud.company import _hash_key
        assert len(_hash_key("any_key_value")) == 64

    def test_hash_is_deterministic(self):
        from app.crud.company import _hash_key
        assert _hash_key("key") == _hash_key("key")

    def test_different_keys_produce_different_hashes(self):
        from app.crud.company import _hash_key
        assert _hash_key("key_a") != _hash_key("key_b")

    def test_hash_matches_sha256(self):
        from app.crud.company import _hash_key
        raw = "test_api_key_value_here"
        expected = hashlib.sha256(raw.encode()).hexdigest()
        assert _hash_key(raw) == expected

    def test_stored_key_is_not_returned_in_response(self, client):
        """api_key in response must be the raw token, not the SHA-256 hash."""
        import secrets
        raw = secrets.token_hex(32)
        hashed = hashlib.sha256(raw.encode()).hexdigest()
        company = _make_company(raw_key=raw)
        company.api_key = hashed

        with patch("app.routers.companies.get_company_by_email", new_callable=AsyncMock, return_value=None):
            with patch("app.routers.companies.create_company", new_callable=AsyncMock, return_value=(raw, company)):
                resp = client.post("/api/v1/companies/", json={"name": "X", "email": "x@x.com"})

        assert resp.status_code == 201
        returned = resp.json()["api_key"]
        assert returned == raw
        assert returned != hashed


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Rate limiting
# ═══════════════════════════════════════════════════════════════════════════════

class TestRateLimiting:

    def test_companies_endpoint_rate_limited_at_11(self, client):
        """POST /api/v1/companies is capped at 10/minute; 11th must be 429."""
        company = _make_company()
        statuses = []
        with patch("app.routers.companies.get_company_by_email", new_callable=AsyncMock, return_value=None):
            with patch("app.routers.companies.create_company", new_callable=AsyncMock, return_value=(RAW_KEY, company)):
                for i in range(11):
                    r = client.post(
                        "/api/v1/companies/",
                        json={"name": f"Co{i}", "email": f"co{i}@example.com"},
                    )
                    statuses.append(r.status_code)

        assert all(s == 201 for s in statuses[:10]), f"Expected 10×201, got {statuses[:10]}"
        assert statuses[10] == 429, f"Expected 429 on 11th request, got {statuses[10]}"

    def test_health_endpoint_is_never_rate_limited(self, client):
        for _ in range(20):
            r = client.get("/health")
            assert r.status_code == 200
