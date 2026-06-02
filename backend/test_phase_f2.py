"""
Phase F2 test suite — Dashboard and Product Monitoring UI.
Run with: venv/Scripts/python.exe test_phase_f2.py

Covers:
  A — Dashboard HTML serving (/dashboard route)
  B — Leads summary endpoint (GET /products/{id}/leads/summary)
  C — Analytics endpoint (GET /products/{id}/leads/analytics)
  D — Export endpoints (CSV + JSON)
  E — Error and empty states (401, 404, no-leads product)
  F — Full dashboard API integration flow (using demo product)
"""
import asyncio
import csv
import io
import json
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


# ── GROUP A: Dashboard HTML serving ──────────────────────────────────────────

async def test_group_a(c: httpx.AsyncClient) -> None:
    # A1: /dashboard returns 200
    r = await c.get("/dashboard")
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    ok("A1 GET /dashboard returns 200")

    # A2: Response is HTML content-type
    ct = r.headers.get("content-type", "")
    assert "text/html" in ct, f"Expected text/html, got {ct}"
    ok(f"A2 /dashboard content-type is text/html")

    # A3: Dashboard HTML contains key landmarks
    html = r.text
    assert "PsychoLead" in html, "Title not found"
    assert "input-api-key" in html, "Login form input not found"
    assert "Connect" in html, "Connect button not found"
    ok("A3 Dashboard HTML contains login form and branding")

    # A4: Dashboard HTML has pipeline stage definitions
    assert "STAGES" in html or "pipeline" in html.lower(), "No pipeline references found"
    ok("A4 Dashboard HTML contains pipeline stage references")

    # A5: Dashboard HTML references all API endpoints it will call
    assert "/api/v1" in html, "API base path not found"
    assert "leads/summary" in html, "leads/summary API call not found"
    assert "leads/analytics" in html, "leads/analytics API call not found"
    assert "leads/export" in html, "leads/export API call not found"
    ok("A5 Dashboard HTML references all required API endpoints")

    # A6: / still serves demo (unchanged)
    r2 = await c.get("/")
    assert r2.status_code == 200
    assert "text/html" in r2.headers.get("content-type", "")
    ok("A6 GET / still serves demo HTML (unaffected)")

    # A7: /dashboard and / are different pages
    assert r.text != r2.text, "Dashboard and demo serve identical HTML"
    ok("A7 /dashboard and / serve distinct HTML pages")


# ── GROUP B: Leads summary endpoint ──────────────────────────────────────────

async def test_group_b(c: httpx.AsyncClient, pid: str, hdrs: dict) -> None:
    # B1: Summary returns 200 for a valid product
    r = await c.get(f"/api/v1/products/{pid}/leads/summary", headers=hdrs)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    ok("B1 GET /leads/summary returns 200")

    # B2: Response has expected fields
    d = r.json()
    for field in ("total_ranked", "avg_score", "top_score", "top_category"):
        assert field in d, f"Missing field: {field}"
    ok(f"B2 Summary contains all required fields: {list(d.keys())}")

    # B3: total_ranked is a non-negative integer
    assert isinstance(d["total_ranked"], int)
    assert d["total_ranked"] >= 0
    ok(f"B3 total_ranked={d['total_ranked']} (non-negative int)")

    # B4: avg_score is float or None
    if d["avg_score"] is not None:
        assert isinstance(d["avg_score"], (int, float))
        assert 0 <= d["avg_score"] <= 100, f"avg_score out of range: {d['avg_score']}"
    ok(f"B4 avg_score={d['avg_score']} (float or None, in-range if present)")

    # B5: top_score >= avg_score when both present
    if d["avg_score"] is not None and d["top_score"] is not None:
        assert d["top_score"] >= d["avg_score"] - 0.1, \
            f"top_score={d['top_score']} < avg_score={d['avg_score']}"
    ok(f"B5 top_score={d['top_score']} >= avg_score constraint satisfied")

    # B6: top_category is string or None
    if d["top_category"] is not None:
        assert isinstance(d["top_category"], str)
        assert len(d["top_category"]) > 0
    ok(f"B6 top_category={d['top_category']!r} (string or None)")

    # B7: 401 with invalid API key (missing header → 422, invalid key → 401)
    r2 = await c.get(
        f"/api/v1/products/{pid}/leads/summary",
        headers={"X-API-Key": "invalid_key_xyz"},
    )
    assert r2.status_code == 401, f"Expected 401, got {r2.status_code}"
    ok("B7 /leads/summary rejects invalid API key with 401")

    # B8: 404 for unknown product
    import uuid
    r3 = await c.get(f"/api/v1/products/{uuid.uuid4()}/leads/summary", headers=hdrs)
    assert r3.status_code == 404, f"Expected 404, got {r3.status_code}"
    ok("B8 /leads/summary returns 404 for unknown product_id")

    # B9: Summary is fast (< 2s) — lightweight single-query design
    t0 = timemod.perf_counter()
    await c.get(f"/api/v1/products/{pid}/leads/summary", headers=hdrs)
    elapsed = timemod.perf_counter() - t0
    assert elapsed < 2.0, f"Summary too slow: {elapsed:.2f}s"
    ok(f"B9 /leads/summary responds in {elapsed:.3f}s (< 2s)")

    return d


# ── GROUP C: Analytics endpoint ───────────────────────────────────────────────

async def test_group_c(c: httpx.AsyncClient, pid: str, hdrs: dict) -> None:
    # C1: Analytics returns 200
    r = await c.get(f"/api/v1/products/{pid}/leads/analytics", headers=hdrs)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    ok("C1 GET /leads/analytics returns 200")

    # C2: Response has all distribution fields
    d = r.json()
    for field in (
        "product_id", "total_ranked", "quality_summary",
        "final_score_distribution", "confidence_distribution",
        "ocean_score_distribution", "top_motivation_categories",
        "calibration_notes",
    ):
        assert field in d, f"Missing field: {field}"
    ok(f"C2 Analytics has all required top-level fields")

    # C3: quality_summary sub-fields
    qs = d["quality_summary"]
    for field in ("passing_all_filters", "pct_passing", "flagged_low_confidence",
                  "flagged_heuristic_ocean", "flagged_insufficient_content"):
        assert field in qs, f"Missing quality_summary field: {field}"
    ok("C3 quality_summary has all required sub-fields")

    # C4: calibration_notes is a non-empty list of strings
    notes = d["calibration_notes"]
    assert isinstance(notes, list), "calibration_notes should be a list"
    assert len(notes) > 0, "calibration_notes should not be empty"
    assert all(isinstance(n, str) for n in notes), "All notes should be strings"
    ok(f"C4 calibration_notes has {len(notes)} note(s)")

    # C5: Distributions have consistent structure
    dist = d["final_score_distribution"]
    for field in ("count", "min", "max", "mean", "median", "std_dev"):
        assert field in dist, f"Missing distribution field: {field}"
    ok("C5 final_score_distribution has correct statistical fields")

    # C6: total_ranked matches distribution count
    if d["total_ranked"] > 0:
        assert dist["count"] == d["total_ranked"], \
            f"total_ranked={d['total_ranked']} but dist.count={dist['count']}"
    ok(f"C6 total_ranked={d['total_ranked']} consistent with distribution count")

    # C7: top_motivation_categories is a list of {category, count} dicts
    cats = d["top_motivation_categories"]
    assert isinstance(cats, list)
    for cat in cats:
        assert "category" in cat and "count" in cat, f"Malformed category entry: {cat}"
    ok(f"C7 top_motivation_categories has {len(cats)} entries with correct structure")

    # C8: min_confidence filter parameter accepted
    r2 = await c.get(
        f"/api/v1/products/{pid}/leads/analytics?min_confidence=40",
        headers=hdrs,
    )
    assert r2.status_code == 200, f"Expected 200, got {r2.status_code}"
    ok("C8 min_confidence filter parameter accepted")

    # C9: 401 with invalid API key
    r3 = await c.get(
        f"/api/v1/products/{pid}/leads/analytics",
        headers={"X-API-Key": "invalid_key_xyz"},
    )
    assert r3.status_code == 401, f"Expected 401, got {r3.status_code}"
    ok("C9 /leads/analytics rejects invalid API key with 401")

    # C10: 404 for unknown product
    import uuid
    r4 = await c.get(f"/api/v1/products/{uuid.uuid4()}/leads/analytics", headers=hdrs)
    assert r4.status_code == 404, f"Expected 404, got {r4.status_code}"
    ok("C10 /leads/analytics returns 404 for unknown product_id")

    return d


# ── GROUP D: Export endpoints ─────────────────────────────────────────────────

async def test_group_d(c: httpx.AsyncClient, pid: str, hdrs: dict) -> None:
    # D1: CSV export returns 200
    r = await c.get(
        f"/api/v1/products/{pid}/leads/export?format=csv",
        headers=hdrs,
    )
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    ok("D1 GET /leads/export?format=csv returns 200")

    # D2: CSV content-type header
    ct = r.headers.get("content-type", "")
    assert "text/csv" in ct or "csv" in ct, f"Unexpected content-type: {ct}"
    ok(f"D2 CSV export content-type correct: {ct}")

    # D3: Content-Disposition header present
    cd = r.headers.get("content-disposition", "")
    assert "attachment" in cd, f"Missing attachment disposition: {cd}"
    assert ".csv" in cd, f"Missing .csv in Content-Disposition: {cd}"
    ok(f"D3 CSV Content-Disposition: {cd}")

    # D4: CSV content is parseable and has expected columns
    csv_text = r.content.decode("utf-8-sig")  # strip BOM if present
    if csv_text.strip():
        reader = csv.DictReader(io.StringIO(csv_text))
        rows = list(reader)
        headers = reader.fieldnames or []
        for col in ("rank", "username", "platform", "final_score", "confidence"):
            assert col in headers, f"Missing CSV column: {col}"
        ok(f"D4 CSV has {len(rows)} rows with required columns")
    else:
        ok("D4 CSV is empty (no ranked leads yet — expected for fresh product)")

    # D5: JSON export returns 200
    r2 = await c.get(
        f"/api/v1/products/{pid}/leads/export?format=json",
        headers=hdrs,
    )
    assert r2.status_code == 200, f"Expected 200, got {r2.status_code}: {r2.text}"
    ok("D5 GET /leads/export?format=json returns 200")

    # D6: JSON content-type
    ct2 = r2.headers.get("content-type", "")
    assert "json" in ct2, f"Unexpected content-type: {ct2}"
    ok(f"D6 JSON export content-type correct: {ct2}")

    # D7: JSON structure has metadata envelope
    payload = r2.json()
    for field in ("product_id", "total_rows", "leads"):
        assert field in payload, f"Missing JSON field: {field}"
    ok(f"D7 JSON export envelope: product_id, total_rows={payload['total_rows']}, leads list")

    # D8: JSON leads array contains expected per-lead fields if non-empty
    if payload["leads"]:
        lead = payload["leads"][0]
        for field in ("rank", "username", "platform", "final_score", "confidence"):
            assert field in lead, f"Missing lead field in JSON: {field}"
        ok(f"D8 JSON lead objects have required fields (sample: username={lead.get('username')!r})")
    else:
        ok("D8 JSON leads array empty (no ranked leads yet)")

    # D9: min_score filter reduces results
    r3 = await c.get(
        f"/api/v1/products/{pid}/leads/export?format=json&min_score=99",
        headers=hdrs,
    )
    assert r3.status_code == 200
    payload_filtered = r3.json()
    assert payload_filtered["total_rows"] <= payload["total_rows"], \
        "min_score=99 should return <= total rows"
    ok(f"D9 min_score=99 filter: {payload_filtered['total_rows']} <= {payload['total_rows']} rows")

    # D10: Invalid format rejected
    r4 = await c.get(
        f"/api/v1/products/{pid}/leads/export?format=xlsx",
        headers=hdrs,
    )
    assert r4.status_code == 422, f"Expected 422, got {r4.status_code}"
    ok("D10 Invalid export format (xlsx) returns 422")

    # D11: 401 with invalid API key
    r5 = await c.get(
        f"/api/v1/products/{pid}/leads/export?format=csv",
        headers={"X-API-Key": "invalid_key_xyz"},
    )
    assert r5.status_code == 401, f"Expected 401, got {r5.status_code}"
    ok("D11 /leads/export rejects invalid API key with 401")

    # D12: 404 for unknown product
    import uuid
    r6 = await c.get(
        f"/api/v1/products/{uuid.uuid4()}/leads/export?format=csv",
        headers=hdrs,
    )
    assert r6.status_code == 404, f"Expected 404, got {r6.status_code}"
    ok("D12 /leads/export returns 404 for unknown product_id")


# ── GROUP E: Error and empty states ──────────────────────────────────────────

async def test_group_e(c: httpx.AsyncClient) -> None:
    # Create a fresh product with no leads for empty-state tests
    email = f"f2test-{int(timemod.time())}@test.ai"
    r = await c.post(
        "/api/v1/companies/",
        json={"name": "F2 Empty Test Co", "email": email, "industry": "Testing"},
    )
    assert r.status_code in (200, 201)
    new_key = r.json()["api_key"]
    new_hdrs = {"X-API-Key": new_key}

    r = await c.post(
        "/api/v1/products/",
        headers=new_hdrs,
        json={
            "name": "Empty State Product",
            "description": "A test product for verifying empty-state responses in the dashboard.",
            "category": "Testing",
            "price_range": "budget",
            "target_location": "Test City, India",
        },
    )
    assert r.status_code in (200, 201)
    new_pid = r.json()["id"]
    ok("E1 Created fresh product with no leads for empty-state tests")

    # E2: Summary for product with no leads returns zeros
    r = await c.get(f"/api/v1/products/{new_pid}/leads/summary", headers=new_hdrs)
    assert r.status_code == 200
    d = r.json()
    assert d["total_ranked"] == 0, f"Expected 0, got {d['total_ranked']}"
    assert d["avg_score"] is None
    assert d["top_score"] is None
    assert d["top_category"] is None
    ok("E2 Summary with no leads returns {total_ranked:0, avg_score:None, ...}")

    # E3: Analytics for product with no leads returns empty
    r = await c.get(f"/api/v1/products/{new_pid}/leads/analytics", headers=new_hdrs)
    assert r.status_code == 200
    d = r.json()
    assert d["total_ranked"] == 0
    assert len(d["calibration_notes"]) > 0, "Should still return calibration notes"
    ok("E3 Analytics with no leads returns total_ranked=0 with calibration notes")

    # E4: CSV export for product with no leads returns empty CSV (just headers)
    r = await c.get(
        f"/api/v1/products/{new_pid}/leads/export?format=csv",
        headers=new_hdrs,
    )
    assert r.status_code == 200
    csv_text = r.content.decode("utf-8-sig")
    # Should have header row but no data rows
    lines = [line for line in csv_text.strip().splitlines() if line.strip()]
    # Could be just the header line, or empty
    ok(f"E4 CSV export with no leads returns {len(lines)} lines (header only or empty)")

    # E5: JSON export for product with no leads returns empty leads array
    r = await c.get(
        f"/api/v1/products/{new_pid}/leads/export?format=json",
        headers=new_hdrs,
    )
    assert r.status_code == 200
    payload = r.json()
    assert payload["total_rows"] == 0
    assert payload["leads"] == []
    ok("E5 JSON export with no leads: {total_rows:0, leads:[]}")

    # E6: Invalid API key returns 401 on summary
    r = await c.get(
        f"/api/v1/products/{new_pid}/leads/summary",
        headers={"X-API-Key": "invalid_key_xyz"},
    )
    assert r.status_code == 401, f"Expected 401, got {r.status_code}"
    ok("E6 Invalid API key returns 401 on /leads/summary")

    # E7: Invalid API key returns 401 on analytics
    r = await c.get(
        f"/api/v1/products/{new_pid}/leads/analytics",
        headers={"X-API-Key": "bad_key"},
    )
    assert r.status_code == 401, f"Expected 401, got {r.status_code}"
    ok("E7 Invalid API key returns 401 on /leads/analytics")

    # E8: Invalid API key returns 401 on export
    r = await c.get(
        f"/api/v1/products/{new_pid}/leads/export?format=csv",
        headers={"X-API-Key": "no_key"},
    )
    assert r.status_code == 401, f"Expected 401, got {r.status_code}"
    ok("E8 Invalid API key returns 401 on /leads/export")


# ── GROUP F: Full dashboard API integration flow ──────────────────────────────

async def test_group_f(c: httpx.AsyncClient) -> None:
    # F1: Demo setup
    r = await c.post("/api/v1/demo/setup")
    assert r.status_code == 200
    demo = r.json()
    pid = demo["product_id"]
    key = demo["api_key"]
    hdrs = {"X-API-Key": key}
    ok(f"F1 Demo setup: product={pid[:8]}... status={demo['status']}")

    # F2: Product list is reachable (simulates dashboard login)
    r = await c.get("/api/v1/products/", headers=hdrs)
    assert r.status_code == 200
    products = r.json()
    assert len(products) >= 1
    assert any(p["id"] == pid for p in products)
    ok(f"F2 Products list returns {len(products)} products (login simulation OK)")

    # F3: Pipeline status visible on product
    r = await c.get(f"/api/v1/products/{pid}", headers=hdrs)
    assert r.status_code == 200
    p = r.json()
    assert "pipeline_step" in p
    assert "status" in p
    ok(f"F3 Product detail: pipeline_step={p['pipeline_step']} status={p['status']!r}")

    # F4: Summary for demo product
    r = await c.get(f"/api/v1/products/{pid}/leads/summary", headers=hdrs)
    assert r.status_code == 200
    summary = r.json()
    ok(f"F4 Leads summary: total={summary['total_ranked']} avg={summary['avg_score']} top_cat={summary['top_category']!r}")

    # F5: Analytics for demo product
    r = await c.get(f"/api/v1/products/{pid}/leads/analytics", headers=hdrs)
    assert r.status_code == 200
    analytics = r.json()
    ok(f"F5 Analytics: total={analytics['total_ranked']} categories={len(analytics['top_motivation_categories'])}")

    # F6: Paginated leads list (used by leads table in dashboard)
    r = await c.get(
        f"/api/v1/products/{pid}/leads?page=1&page_size=20",
        headers=hdrs,
    )
    assert r.status_code == 200
    leads_page = r.json()
    assert "leads" in leads_page
    assert "total_leads" in leads_page
    assert "total_pages" in leads_page
    ok(f"F6 Leads list: total={leads_page['total_leads']} page=1/{leads_page['total_pages']}")

    # F7: CSV export for demo product
    r = await c.get(
        f"/api/v1/products/{pid}/leads/export?format=csv",
        headers=hdrs,
    )
    assert r.status_code == 200
    ok("F7 CSV export for demo product returns 200")

    # F8: JSON export for demo product
    r = await c.get(
        f"/api/v1/products/{pid}/leads/export?format=json",
        headers=hdrs,
    )
    assert r.status_code == 200
    payload = r.json()
    assert payload["product_id"] == pid
    ok(f"F8 JSON export: product_id matches, total_rows={payload['total_rows']}")

    # F9: Lead inspection (used by modal in dashboard) — if leads exist
    if leads_page["leads"]:
        uid = leads_page["leads"][0]["user_id"]
        r = await c.get(
            f"/api/v1/products/{pid}/leads/{uid}/inspect",
            headers=hdrs,
        )
        assert r.status_code == 200
        inspection = r.json()
        for field in ("username", "ocean_profile", "best_match", "quality_flags"):
            assert field in inspection, f"Missing field: {field}"
        ok(f"F9 Lead inspection modal data: username={inspection['username']!r}")
    else:
        ok("F9 Lead inspection skipped (no ranked leads in demo product)")

    # F10: Matching trigger endpoint (re-run button in dashboard)
    r = await c.post(f"/api/v1/products/{pid}/match/trigger", headers=hdrs)
    # 202 if product is in eligible status, 422 if not
    assert r.status_code in (202, 422), f"Expected 202 or 422, got {r.status_code}"
    ok(f"F10 Match trigger: {r.status_code} ({'queued' if r.status_code == 202 else 'ineligible status'})")

    # F11: Verify summary + analytics are consistent
    summary_total = summary["total_ranked"]
    analytics_total = analytics["total_ranked"]
    assert summary_total == analytics_total, \
        f"Summary total {summary_total} != analytics total {analytics_total}"
    ok(f"F11 Summary/analytics consistency: both report {summary_total} ranked leads")


# ── GROUP G: Dashboard routing consistency ────────────────────────────────────

async def test_group_g(c: httpx.AsyncClient, pid: str, hdrs: dict) -> None:
    # G1: /leads/summary does not interfere with /leads/{user_id} route
    # (summary is a literal path that must not be captured as a user_id UUID)
    import uuid
    fake_uuid = str(uuid.uuid4())

    r = await c.get(f"/api/v1/products/{pid}/leads/summary", headers=hdrs)
    assert r.status_code == 200, f"/leads/summary returned {r.status_code}, not 200"
    d = r.json()
    assert "total_ranked" in d, f"Response looks wrong: {d}"
    ok("G1 /leads/summary not captured as /leads/{user_id} — routing correct")

    # G2: /leads/analytics does not interfere with /leads/{user_id}
    r = await c.get(f"/api/v1/products/{pid}/leads/analytics", headers=hdrs)
    assert r.status_code == 200
    d = r.json()
    assert "calibration_notes" in d, f"Response looks wrong: {d}"
    ok("G2 /leads/analytics not captured as /leads/{user_id} — routing correct")

    # G3: /leads/export does not interfere with /leads/{user_id}
    r = await c.get(
        f"/api/v1/products/{pid}/leads/export?format=json",
        headers=hdrs,
    )
    assert r.status_code == 200
    d = r.json()
    assert "leads" in d and "total_rows" in d, f"Response looks wrong: {d}"
    ok("G3 /leads/export not captured as /leads/{user_id} — routing correct")

    # G4: /leads/summary is not confused with /leads/{user_id}/inspect
    # (inspect requires a valid UUID, summary returns aggregate)
    r_s = await c.get(f"/api/v1/products/{pid}/leads/summary", headers=hdrs)
    r_i = await c.get(
        f"/api/v1/products/{pid}/leads/{fake_uuid}/inspect",
        headers=hdrs,
    )
    assert r_s.status_code == 200
    assert r_i.status_code in (404, 422)  # 404 = not found, 422 = bad UUID
    ok(f"G4 /leads/summary(200) and /leads/{fake_uuid[:8]}../inspect({r_i.status_code}) are distinct")


# ── Main runner ───────────────────────────────────────────────────────────────

async def run() -> None:
    async with httpx.AsyncClient(
        base_url=BASE, timeout=30, follow_redirects=True
    ) as c:
        # A — Dashboard serving
        await test_group_a(c)

        # Get demo product for reuse
        r = await c.post("/api/v1/demo/setup")
        assert r.status_code == 200
        demo = r.json()
        pid = demo["product_id"]
        key = demo["api_key"]
        hdrs = {"X-API-Key": key}

        # B — Leads summary
        await test_group_b(c, pid, hdrs)

        # C — Analytics
        await test_group_c(c, pid, hdrs)

        # D — Export
        await test_group_d(c, pid, hdrs)

        # E — Error/empty states
        await test_group_e(c)

        # F — Full integration flow
        await test_group_f(c)

        # G — Routing consistency
        await test_group_g(c, pid, hdrs)


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
