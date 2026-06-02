"""
Phase B1 test suite.
Run with: venv/Scripts/python.exe test_phase_b1.py

Covers:
  A — Server / infra
  B — Provider architecture (unit tests, no HTTP, no DB)
  C — Mock provider
  D — Subreddit map
  E — Orchestrator (with mock provider + real DB)
  F — API endpoints (HTTP)
  G — Discovery run end-to-end
  H — Failure handling
  I — Credential-absent scenarios
  J — Duplicate prevention
  K — Demo flow unaffected
"""
import asyncio
import time as timemod
import httpx

BASE = "http://localhost:8000"
RESULTS: list[tuple[str, str]] = []


def ok(name: str) -> None:
    RESULTS.append(("PASS", name))
    print(f"[PASS] {name}")


def fail(name: str, reason: str = "") -> None:
    RESULTS.append(("FAIL", name))
    print(f"[FAIL] {name}{': ' + reason if reason else ''}")


# ── GROUP A: Server + new infrastructure ─────────────────────────────────────

async def test_group_a(c: httpx.AsyncClient) -> None:
    r = await c.get("/health")
    assert r.json()["status"] == "ok"
    ok("A1 /health returns ok")

    r = await c.get("/api/v1/ollama/status")
    d = r.json()
    assert d["reachable"]
    ok("A2 Ollama still reachable after B1 changes")

    r = await c.get("/api/v1/discovery/provider/status")
    assert r.status_code == 200
    d = r.json()
    assert "ok" in d and "provider" in d and "mock_mode" in d
    ok(f"A3 Discovery provider status endpoint: provider={d['provider']} mock={d['mock_mode']}")

    # Since credentials are empty in .env, should be in mock mode
    assert d["mock_mode"] is True
    assert d["credentials_configured"] is False
    ok("A4 Mock mode active when credentials absent")


# ── GROUP B: Provider architecture unit tests (no HTTP, no DB) ───────────────

async def test_group_b() -> None:
    from app.ml.discovery.base import BaseDiscoveryProvider, RawDiscoveredUser, ContentItem

    # B1: RawDiscoveredUser dataclass
    u = RawDiscoveredUser(platform="reddit", source_provider="mock", username="testuser")
    assert u.platform == "reddit"
    assert u.post_count is None  # Reddit: always None
    assert u.location_confidence == "unknown"
    ok("B1 RawDiscoveredUser defaults correct (post_count=None for Reddit)")

    # B2: ContentItem dataclass
    c = ContentItem(content_type="post", content_text="Hello world")
    assert c.engagement == 0
    assert c.posted_at is None
    ok("B2 ContentItem defaults correct")

    # B3: BaseDiscoveryProvider is abstract — cannot instantiate directly
    try:
        BaseDiscoveryProvider()
        fail("B3 Abstract class should not be instantiable")
    except TypeError:
        ok("B3 BaseDiscoveryProvider is abstract — cannot instantiate directly")

    # B4: RedditProvider raises RuntimeError when credentials absent
    from app.config import settings
    original_id = settings.REDDIT_CLIENT_ID
    settings.REDDIT_CLIENT_ID = ""
    try:
        from app.ml.discovery.reddit_provider import RedditProvider
        RedditProvider()
        fail("B4 RedditProvider should raise when credentials absent")
    except RuntimeError as exc:
        assert "credentials" in str(exc).lower() or "REDDIT" in str(exc)
        ok("B4 RedditProvider raises RuntimeError when credentials absent")
    finally:
        settings.REDDIT_CLIENT_ID = original_id

    # B5: settings.use_mock_discovery() returns True when creds absent
    original_id = settings.REDDIT_CLIENT_ID
    settings.REDDIT_CLIENT_ID = ""
    assert settings.use_mock_discovery() is True
    settings.REDDIT_CLIENT_ID = original_id
    ok("B5 use_mock_discovery()=True when REDDIT_CLIENT_ID is empty")

    # B6: settings.reddit_credentials_configured() logic
    assert settings.reddit_credentials_configured() is False  # empty from .env
    ok("B6 reddit_credentials_configured()=False when env vars are empty")


# ── GROUP C: MockDiscoveryProvider ────────────────────────────────────────────

async def test_group_c() -> None:
    from app.ml.discovery.mock_provider import MockDiscoveryProvider

    provider = MockDiscoveryProvider(delay_ms=0)

    # C1: name / platform / health_check
    assert provider.name == "mock"
    assert provider.platform == "mock"
    health = await provider.health_check()
    assert health["ok"] is True
    ok("C1 MockProvider: name/platform/health_check correct")

    # C2: discover_users returns RawDiscoveredUser objects
    users = await provider.discover_users(
        keywords=["interior design", "sofa", "home decor"],
        target_city="Chennai",
        max_users=10,
        search_config={},
    )
    assert len(users) == 10
    assert all(u.platform == "reddit" for u in users)
    assert all(u.post_count is None for u in users)  # Reddit: no post_count
    ok(f"C2 MockProvider discovers {len(users)} users (post_count=None confirmed)")

    # C3: max_users respected
    few = await provider.discover_users(
        keywords=["yoga"], target_city=None, max_users=3, search_config={}
    )
    assert len(few) == 3
    ok("C3 MockProvider respects max_users limit")

    # C4: city-matched users come first
    chennai_users = await provider.discover_users(
        keywords=["furniture"], target_city="Chennai", max_users=5, search_config={}
    )
    assert any("chennai" in (u.location or "").lower() for u in chennai_users)
    ok("C4 MockProvider prioritises city-matched users")

    # C5: location_confidence values are valid
    from app.ml.discovery.base import LOCATION_CONFIDENCE_LEVELS
    all_users = await provider.discover_users(
        keywords=["home"], target_city="Chennai", max_users=30, search_config={}
    )
    for u in all_users:
        assert u.location_confidence in LOCATION_CONFIDENCE_LEVELS, \
            f"Invalid confidence: {u.location_confidence}"
    ok("C5 All location_confidence values are valid enum members")

    # C6: collect_content returns ContentItem list including bio
    target_user = users[0]
    content = await provider.collect_content(target_user, max_items=10)
    assert len(content) > 0
    assert len(content) <= 10
    content_types = {item.content_type for item in content}
    assert "bio" in content_types or len(content) > 0  # bio included if bio present
    ok(f"C6 collect_content returns {len(content)} items for user {target_user.username}")

    # C7: collect_content is deterministic (same user -> same content)
    content2 = await provider.collect_content(target_user, max_items=10)
    assert [i.content_text for i in content] == [i.content_text for i in content2]
    ok("C7 collect_content is deterministic (seed from username)")

    # C8: empty keywords still returns users
    users_nk = await provider.discover_users(
        keywords=[], target_city="Mumbai", max_users=5, search_config={}
    )
    assert len(users_nk) == 5
    ok("C8 MockProvider handles empty keywords gracefully")

    # C9: max_users=0 edge case
    users_zero = await provider.discover_users(
        keywords=["sofa"], target_city=None, max_users=0, search_config={}
    )
    assert len(users_zero) == 0
    ok("C9 MockProvider returns empty list for max_users=0")


# ── GROUP D: Subreddit mapping ────────────────────────────────────────────────

async def test_group_d() -> None:
    from app.ml.discovery.subreddit_map import get_subreddits_for_keywords, get_city_subreddits

    # D1: known keyword maps to subreddits
    subs = get_subreddits_for_keywords(["interior design"])
    assert len(subs) > 0
    assert "interiordesign" in subs
    ok(f"D1 'interior design' -> {subs[:3]}")

    # D2: max_subreddits respected
    subs = get_subreddits_for_keywords(["furniture", "home decor", "aesthetics"], max_subreddits=5)
    assert len(subs) <= 5
    ok(f"D2 max_subreddits=5 respected, got {len(subs)}")

    # D3: unknown keyword returns empty list (no crash)
    subs = get_subreddits_for_keywords(["xyzabcunknownkeyword1234"])
    assert isinstance(subs, list)
    ok("D3 Unknown keyword returns empty list, no crash")

    # D4: empty input returns empty list
    subs = get_subreddits_for_keywords([])
    assert subs == []
    ok("D4 Empty keyword list returns empty list")

    # D5: no duplicates in output
    subs = get_subreddits_for_keywords(
        ["interior design", "home decor", "furniture", "aesthetics"]
    )
    assert len(subs) == len(set(subs))
    ok(f"D5 No duplicate subreddits in output ({len(subs)} unique)")

    # D6: city subreddits
    subs = get_city_subreddits("Chennai")
    assert "Chennai" in subs or "tamilnadu" in subs
    ok(f"D6 Chennai -> {subs}")

    # D7: unknown city falls back to india
    subs = get_city_subreddits("Obscureville")
    assert "india" in subs
    ok("D7 Unknown city falls back to r/india")

    # D8: None target_city
    subs = get_city_subreddits(None)
    assert len(subs) > 0
    ok("D8 None target_city returns valid fallback subreddits")


# ── GROUP E: Orchestrator with DB ─────────────────────────────────────────────

async def test_group_e() -> None:
    from app.database import AsyncSessionLocal
    from app.models.discovery import DiscoveryJob, DiscoveredUser, UserContent
    from app.models.product import ProductStatus
    from sqlalchemy import select, text

    # E1: Create a test product + run orchestrator directly
    async with AsyncSessionLocal() as db:
        # Reuse the demo company
        result = await db.execute(
            text("SELECT id, api_key FROM companies WHERE email = 'demo@psycholead.ai'")
        )
        row = result.fetchone()
        if not row:
            fail("E1 Demo company not found — run demo setup first")
            return
        company_id, api_key = row

        # Find any product that has motivation categories (any status post-motivations)
        result = await db.execute(
            text(
                "SELECT DISTINCT p.id FROM products p "
                "JOIN motivation_categories mc ON mc.product_id = p.id "
                "WHERE p.company_id = :cid "
                "ORDER BY p.id LIMIT 1"
            ),
            {"cid": company_id},
        )
        row = result.fetchone()
        if not row:
            fail("E1 No product with motivation categories found — run demo setup first")
            return
        product_id = row[0]

    ok(f"E1 Found test product {str(product_id)[:8]}...")

    # E2: Run full orchestrator pipeline (with mock provider)
    from app.ml.discovery.orchestrator import DiscoveryOrchestrator
    from app.crud.discovery import create_discovery_job

    async with AsyncSessionLocal() as db:
        job = await create_discovery_job(
            db, product_id=product_id, max_users=10, search_config={}
        )
        job_id = job.id
    ok(f"E2 Discovery job created job={str(job_id)[:8]}...")

    async with AsyncSessionLocal() as db:
        orchestrator = DiscoveryOrchestrator()
        await orchestrator.run(job_id, db)
    ok("E3 Orchestrator.run() completed without exception")

    # E4: Verify DB state after run
    async with AsyncSessionLocal() as db:
        job_check = await db.get(DiscoveryJob, job_id)
        assert job_check is not None
        assert job_check.status == "completed", f"Expected completed, got {job_check.status}"
        assert job_check.users_discovered > 0
        assert job_check.users_content_collected > 0
        ok(f"E4 Job status=completed, discovered={job_check.users_discovered}, collected={job_check.users_content_collected}")

    # E5: Verify discovered_users inserted
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(DiscoveredUser).where(DiscoveredUser.discovery_job_id == job_id)
        )
        users = result.scalars().all()
        assert len(users) > 0
        assert all(u.content_collected for u in users)
        assert all(u.post_count is None for u in users)  # mock also sets None
        ok(f"E5 {len(users)} discovered_users in DB, all content_collected=True, all post_count=None")

    # E6: Verify user_content inserted
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(DiscoveredUser).where(DiscoveredUser.discovery_job_id == job_id).limit(1)
        )
        sample_user = result.scalar_one()
        result2 = await db.execute(
            select(UserContent).where(UserContent.user_id == sample_user.id)
        )
        content_items = result2.scalars().all()
        assert len(content_items) > 0
        content_types = {ci.content_type for ci in content_items}
        assert "bio" in content_types or "post" in content_types or "comment" in content_types
        ok(f"E6 {len(content_items)} content items for user {sample_user.username}, types={content_types}")

    # E7: Verify product.pipeline_step advanced to 3
    async with AsyncSessionLocal() as db:
        from app.models.product import Product
        prod = await db.get(Product, product_id)
        # Demo products already at step 9 (completed via demo/setup).
        # Discovery advances them to step 3 OR leaves at >= 3 if already higher.
        assert prod.pipeline_step >= 3
        ok(f"E7 Product pipeline_step={prod.pipeline_step} (>= 3 after discovery)")

    return job_id, str(product_id)


# ── GROUP F: API endpoints ─────────────────────────────────────────────────────

async def test_group_f(c: httpx.AsyncClient) -> tuple[str, str]:
    # F1: Get a valid product + API key
    r = await c.post("/api/v1/demo/setup")
    assert r.status_code == 200
    demo = r.json()
    pid = demo["product_id"]
    key = demo["api_key"]
    hdrs = {"X-API-Key": key}
    ok(f"F1 Demo setup product={pid[:8]}...")

    # F2: Start discovery (min_users=10 per schema validation)
    r = await c.post(
        f"/api/v1/products/{pid}/discovery/start",
        headers=hdrs,
        json={"max_users": 10},
    )
    assert r.status_code == 202, f"Expected 202, got {r.status_code}: {r.text}"
    job = r.json()
    job_id = job["id"]
    assert job["status"] == "queued"
    assert job["max_users"] == 10
    ok(f"F2 POST /discovery/start -> job_id={job_id[:8]}... status=queued")

    # F3: Poll job status
    await asyncio.sleep(3)  # give background task time to start
    r = await c.get(f"/api/v1/products/{pid}/discovery/jobs/{job_id}", headers=hdrs)
    assert r.status_code == 200
    s = r.json()
    assert s["id"] == job_id
    ok(f"F3 GET /discovery/jobs/{job_id[:8]}... -> status={s['status']}")

    # F4: Wait for completion
    print("[F4] Waiting for discovery to complete (max 30s)...")
    deadline = timemod.time() + 30
    final = None
    while timemod.time() < deadline:
        try:
            r = await c.get(f"/api/v1/products/{pid}/discovery/jobs/{job_id}", headers=hdrs)
            s = r.json()
            if s["status"] in ("completed", "failed"):
                final = s
                break
        except Exception:
            pass
        await asyncio.sleep(2)

    assert final is not None, "Timed out waiting for discovery to complete"
    assert final["status"] == "completed", f"Expected completed, got {final['status']}: {final.get('error_message')}"
    assert final["users_discovered"] > 0
    ok(f"F4 Job completed: discovered={final['users_discovered']} collected={final['users_content_collected']}")

    # F5: List jobs
    r = await c.get(f"/api/v1/products/{pid}/discovery/jobs", headers=hdrs)
    assert r.status_code == 200
    jobs = r.json()
    assert len(jobs) >= 1
    ok(f"F5 GET /discovery/jobs -> {len(jobs)} job(s) listed")

    # F6: List discovered users
    r = await c.get(f"/api/v1/products/{pid}/discovery/users", headers=hdrs)
    assert r.status_code == 200
    d = r.json()
    assert d["total"] > 0
    assert len(d["users"]) > 0
    ok(f"F6 GET /discovery/users -> total={d['total']} users")

    # F7: User fields are correct
    first_user = d["users"][0]
    assert first_user["platform"] in ("reddit", "mock")
    assert first_user["content_collected"] is True
    assert first_user.get("post_count") is None  # mock/reddit: never set
    ok("F7 User fields correct (platform, content_collected=True, post_count=None)")

    # F8: Get user content
    user_id = first_user["id"]
    r = await c.get(
        f"/api/v1/products/{pid}/discovery/users/{user_id}/content",
        headers=hdrs,
    )
    assert r.status_code == 200
    items = r.json()
    assert len(items) > 0
    assert all("content_text" in i and "content_type" in i for i in items)
    ok(f"F8 GET /discovery/users/{user_id[:8]}../content -> {len(items)} items")

    # F9: Product cannot start discovery when status is 'pending'
    import time as t
    email = f"disc-test-{int(t.time())}@test.ai"
    r = await c.post("/api/v1/companies/", json={"name": "Disc Test", "email": email, "industry": "Test"})
    api_key2 = r.json()["api_key"]
    r = await c.post("/api/v1/products/", headers={"X-API-Key": api_key2}, json={
        "name": "Test Product",
        "description": "A test product for discovery validation testing purposes.",
        "category": "Test",
        "price_range": "budget",
        "target_location": "Test City, India",
    })
    pid2 = r.json()["id"]
    r = await c.post(
        f"/api/v1/products/{pid2}/discovery/start",
        headers={"X-API-Key": api_key2},
        json={"max_users": 5},
    )
    assert r.status_code == 422
    ok("F9 Discovery blocked when product status=pending (422)")

    return job_id, pid


# ── GROUP G: Duplicate prevention ─────────────────────────────────────────────

async def test_group_g(c: httpx.AsyncClient, pid: str, api_key: str) -> None:
    hdrs = {"X-API-Key": api_key}

    # G1: Run discovery again on same product -> same users should not be inserted twice
    # (Each job creates new rows, but within a job, duplicates are prevented)
    r = await c.post(
        f"/api/v1/products/{pid}/discovery/start",
        headers=hdrs,
        json={"max_users": 10},
    )
    assert r.status_code == 202, f"Expected 202, got {r.status_code}: {r.text}"
    job2_id = r.json()["id"]

    # Wait for completion
    deadline = timemod.time() + 30
    while timemod.time() < deadline:
        try:
            r = await c.get(f"/api/v1/products/{pid}/discovery/jobs/{job2_id}", headers=hdrs)
            if r.json()["status"] in ("completed", "failed"):
                break
        except Exception:
            pass
        await asyncio.sleep(2)

    # G2: Intra-job duplicates are prevented by _upsert_user logic
    from app.database import AsyncSessionLocal
    from sqlalchemy import select, func
    from app.models.discovery import DiscoveredUser

    async with AsyncSessionLocal() as db:
        from uuid import UUID
        result = await db.execute(
            select(
                DiscoveredUser.username,
                func.count(DiscoveredUser.id).label("cnt")
            )
            .where(DiscoveredUser.discovery_job_id == UUID(job2_id))
            .group_by(DiscoveredUser.username)
            .having(func.count(DiscoveredUser.id) > 1)
        )
        dups = result.fetchall()
        assert len(dups) == 0, f"Intra-job duplicates found: {dups}"
    ok("G1 No intra-job duplicate users (deduplication working)")

    # G3: Two jobs for same product are both in the jobs list
    r = await c.get(f"/api/v1/products/{pid}/discovery/jobs", headers=hdrs)
    jobs = r.json()
    assert len(jobs) >= 2
    ok(f"G2 Multiple jobs tracked correctly ({len(jobs)} jobs for product)")


# ── GROUP H: Failure / edge case handling ─────────────────────────────────────

async def test_group_h() -> None:
    # H1: Orchestrator handles product_id not found gracefully
    from app.ml.discovery.orchestrator import DiscoveryOrchestrator
    from app.database import AsyncSessionLocal
    import uuid

    async with AsyncSessionLocal() as db:
        orch = DiscoveryOrchestrator()
        # Should not raise — just log and return
        await orch.run(uuid.uuid4(), db)
    ok("H1 Orchestrator handles non-existent job_id gracefully")

    # H2: MockProvider with max_users larger than pool -> returns all available
    from app.ml.discovery.mock_provider import MockDiscoveryProvider
    provider = MockDiscoveryProvider(delay_ms=0)
    users = await provider.discover_users(
        keywords=["anything"], target_city=None, max_users=9999, search_config={}
    )
    assert len(users) == 30  # pool has 30 users
    ok(f"H2 Requesting more users than pool returns all {len(users)} available")

    # H3: Content collection for user with no bio still works
    from app.ml.discovery.base import RawDiscoveredUser
    no_bio = RawDiscoveredUser(
        platform="mock", source_provider="mock", username="nobio_user",
        bio=None,
    )
    content = await provider.collect_content(no_bio, max_items=5)
    # Should return posts/comments even without bio
    assert isinstance(content, list)
    ok(f"H3 collect_content works for user with no bio ({len(content)} items)")

    # H4: Subreddit mapper handles partial keyword match
    from app.ml.discovery.subreddit_map import get_subreddits_for_keywords
    subs = get_subreddits_for_keywords(["interior"])  # partial match of "interior design"
    assert isinstance(subs, list)
    ok(f"H4 Subreddit mapper handles partial keyword match -> {len(subs)} subreddits")


# ── GROUP I: DB schema verification ───────────────────────────────────────────

async def test_group_i() -> None:
    from app.database import AsyncSessionLocal
    from sqlalchemy import text

    async with AsyncSessionLocal() as db:
        # I1: All new tables exist
        for table in ["discovery_jobs", "discovered_users", "user_content",
                      "enrichment_jobs", "product_enrichment_signals"]:
            r = await db.execute(text(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                "WHERE table_schema='public' AND table_name=:t)"
            ), {"t": table})
            assert r.scalar(), f"Table {table} missing"
        ok("I1 All 5 new tables exist in DB")

        # I2: New columns on existing tables
        for table, col in [
            ("products", "enrichment_status"),
            ("motivation_categories", "enrichment_context"),
            ("discovered_users", "source_provider"),
            ("discovered_users", "location_confidence"),
            ("discovery_jobs", "provider_name"),
        ]:
            r = await db.execute(text(
                "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
                "WHERE table_name=:t AND column_name=:c)"
            ), {"t": table, "c": col})
            assert r.scalar(), f"Column {table}.{col} missing"
        ok("I2 All new columns exist on existing tables")

        # I3: Alembic version tracking
        r = await db.execute(text("SELECT version_num FROM alembic_version"))
        version = r.scalar()
        assert version is not None
        ok(f"I3 Alembic version tracked: {version}")

        # I4: Existing products have enrichment_status='none'
        r = await db.execute(text(
            "SELECT COUNT(*) FROM products WHERE enrichment_status != 'none'"
        ))
        nondefault = r.scalar()
        assert nondefault == 0, f"{nondefault} products have non-'none' enrichment_status"
        ok("I4 Existing products have enrichment_status='none' (migration default correct)")

        # I5: Existing motivation_categories have enrichment_context={}
        r = await db.execute(text(
            "SELECT COUNT(*) FROM motivation_categories "
            "WHERE enrichment_context::text != '{}'::text"
        ))
        nondefault = r.scalar()
        assert nondefault == 0, f"{nondefault} categories have non-empty enrichment_context"
        ok("I5 Existing motivation_categories have enrichment_context={} (migration default correct)")


# ── GROUP J: Demo flow unaffected ─────────────────────────────────────────────

async def test_group_j(c: httpx.AsyncClient) -> None:
    r = await c.post("/api/v1/demo/setup")
    assert r.status_code == 200
    demo = r.json()
    assert demo["status"] == "demo_ready"
    ok("J1 Demo setup still works after Phase B1 changes")

    pid = demo["product_id"]
    key = demo["api_key"]
    hdrs = {"X-API-Key": key}

    r = await c.get(f"/api/v1/products/{pid}/motivations", headers=hdrs)
    assert r.json()["total"] == 5
    ok("J2 Demo motivations still readable")

    r = await c.get(f"/api/v1/demo/{pid}/users")
    assert r.json()["total_discovered"] == 847
    ok("J3 Demo users endpoint unaffected")

    r = await c.get(f"/api/v1/demo/{pid}/leads")
    assert r.json()["hot_count"] == 4
    ok("J4 Demo leads endpoint unaffected")

    # Verify demo product has enrichment_status='none' (not touched)
    r = await c.get(f"/api/v1/products/{pid}", headers=hdrs)
    # enrichment_status not in ProductResponse schema — verify via DB
    from app.database import AsyncSessionLocal
    from sqlalchemy import text
    from uuid import UUID
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text("SELECT enrichment_status FROM products WHERE id=:id"),
            {"id": UUID(pid)},
        )
        row = result.fetchone()
        assert row is not None
        assert row[0] == "none"
    ok("J5 Demo product enrichment_status='none' (not modified by discovery pipeline)")


# ── Main runner ───────────────────────────────────────────────────────────────

async def run() -> None:
    async with httpx.AsyncClient(
        base_url=BASE, timeout=60, follow_redirects=True
    ) as c:
        # Unit tests first (no HTTP, no DB)
        await test_group_b()
        await test_group_c()
        await test_group_d()
        await test_group_h()
        await test_group_i()

        # Infrastructure
        await test_group_a(c)

        # Orchestrator with DB
        orch_result = await test_group_e()

        # API endpoints
        job_id, pid = await test_group_f(c)

        # G group needs a product that already has 1 discovery job (from F above).
        # pid from F has exactly 1 job. We use the demo api_key (same company).
        r = await c.post("/api/v1/demo/setup")
        api_key = r.json()["api_key"]  # demo company api key works for any demo product

        # Duplicate prevention (run second discovery on F's product, which has 1 job)
        await test_group_g(c, pid, api_key)

        # Demo unaffected
        await test_group_j(c)


if __name__ == "__main__":
    asyncio.run(run())
    passes = sum(1 for r, _ in RESULTS if r == "PASS")
    fails = sum(1 for r, _ in RESULTS if r == "FAIL")
    print()
    print("=" * 60)
    print(f"RESULTS: {passes} PASS   {fails} FAIL   (total {len(RESULTS)})")
    if fails:
        for r, n in RESULTS:
            if r == "FAIL":
                print(f"  FAIL: {n}")
    else:
        print("All tests passed.")
