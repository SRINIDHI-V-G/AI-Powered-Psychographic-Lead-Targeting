"""Phase A test suite — run with:  venv/Scripts/python.exe test_phase_a.py"""
import asyncio
import time as timemod
import httpx

BASE = "http://localhost:8000"
RESULTS: list[tuple[str, str]] = []


def ok(name):
    RESULTS.append(("PASS", name))
    print(f"[PASS] {name}")


def fail(name, reason):
    RESULTS.append(("FAIL", name))
    print(f"[FAIL] {name}: {reason}")


async def poll_status(c, pid, hdrs, label, timeout=360):
    """Poll /status every 5s, reconnecting on transient connection errors."""
    deadline = timemod.time() + timeout
    final = None
    while timemod.time() < deadline:
        try:
            r = await c.get(f"/api/v1/products/{pid}/status", headers=hdrs)
            s = r.json()
            elapsed = int(timeout - (deadline - timemod.time()))
            print(f"     [{elapsed:3d}s] {s['status']} step={s['pipeline_step']}", end="\r", flush=True)
            if s["status"] in ("motivations_generated", "failed", "completed"):
                final = s
                break
        except (httpx.RemoteProtocolError, httpx.ConnectError, httpx.ReadError):
            # Transient connection issue (stale keep-alive) — reconnect next poll
            pass
        await asyncio.sleep(5)
    print()
    return final


async def run():
    async with httpx.AsyncClient(base_url=BASE, timeout=30, follow_redirects=True) as c:

        # ── GROUP A: Infrastructure ───────────────────────────────────────────
        r = await c.get("/health")
        assert r.json()["status"] == "ok"
        ok("A1 /health returns ok")

        r = await c.get("/api/v1/ollama/status")
        d = r.json()
        assert d["reachable"] and d["model_available"]
        ok(f"A2 Ollama reachable, llama3.1:8b available")

        # ── GROUP B: Company + Auth ───────────────────────────────────────────
        email = f"suite-{int(timemod.time())}@test.ai"
        r = await c.post("/api/v1/companies/", json={"name": "Suite Co", "email": email, "industry": "Test"})
        assert r.status_code == 201
        API_KEY = r.json()["api_key"]
        ok(f"B1 Company registered key={API_KEY[:8]}...")

        r = await c.post("/api/v1/companies/", json={"name": "Suite Co", "email": email, "industry": "Test"})
        assert r.status_code == 409
        ok("B2 Duplicate email -> 409")

        r = await c.get("/api/v1/products/", headers={"X-API-Key": "badkey"})
        assert r.status_code == 401
        ok("B3 Invalid API key -> 401")

        hdrs = {"X-API-Key": API_KEY}

        # ── GROUP C: Product CRUD ─────────────────────────────────────────────
        r = await c.post("/api/v1/products/", headers=hdrs, json={
            "name": "Smart Water Bottle",
            "description": "A 750ml insulated smart bottle that tracks hydration via bluetooth and reminds you to drink water.",
            "category": "Health & Fitness",
            "price_range": "mid_range",
            "target_location": "Delhi, India",
            "keywords": ["bottle", "hydration", "smart", "fitness"],
        })
        assert r.status_code == 201
        product = r.json()
        PID = product["id"]
        assert product["status"] == "pending"
        ok(f"C1 Product submitted id={PID[:8]}... status=pending")

        r = await c.get(f"/api/v1/products/{PID}/status", headers=hdrs)
        assert r.status_code == 200
        s = r.json()
        assert all(k in s for k in ("id", "status", "pipeline_step", "updated_at"))
        ok("C2 /status poll returns correct fields")

        r = await c.get("/api/v1/products/", headers=hdrs)
        assert PID in [p["id"] for p in r.json()]
        ok(f"C3 Product list includes new product")

        # ── GROUP D: Real LLM generation ──────────────────────────────────────
        print()
        print("[D4] Waiting for Ollama to generate motivations (up to 360s)...")
        final = await poll_status(c, PID, hdrs, "D4", timeout=360)
        assert final is not None, "Timed out after 360s"
        assert final["status"] == "motivations_generated", \
            f"Expected motivations_generated, got {final['status']}. err={final.get('error_message')}"
        ok("D4 Motivations generated (status=motivations_generated)")

        r = await c.get(f"/api/v1/products/{PID}/motivations", headers=hdrs)
        assert r.status_code == 200
        cats = r.json()["categories"]
        assert len(cats) == 5, f"Expected 5, got {len(cats)}"
        ok("D5 Exactly 5 categories stored in DB")

        all_valid = True
        for i, cat in enumerate(cats):
            if not cat["name"] or len(cat["description"]) < 15:
                all_valid = False
            op = cat["ocean_profile"]
            if op is None:
                all_valid = False
                continue
            for dim in ("openness", "conscientiousness", "extraversion", "agreeableness", "emotional_stability"):
                if not (0.0 <= op[dim] <= 10.0):
                    all_valid = False
            if not op["interest_tags"] or not op["search_keywords"]:
                all_valid = False
        assert all_valid
        names = [cat["name"] for cat in cats]
        ok(f"D6 All categories have valid structure + OCEAN in [0,10]: {names}")

        # ── GROUP E: Regenerate ───────────────────────────────────────────────
        print()
        print("[E7] Testing /motivations/regenerate...")
        r = await c.post(f"/api/v1/products/{PID}/motivations/regenerate", headers=hdrs)
        assert r.status_code == 200
        assert r.json()["status"] == "pending"
        ok("E7 Regenerate resets product to pending")

        print("[E8] Waiting for re-generation (up to 360s)...")
        final2 = await poll_status(c, PID, hdrs, "E8", timeout=360)
        assert final2 is not None and final2["status"] == "motivations_generated"
        ok("E8 Re-generation completed successfully")

        r = await c.get(f"/api/v1/products/{PID}/motivations", headers=hdrs)
        assert r.json()["total"] == 5
        ok("E9 Still exactly 5 categories after regeneration")

        # ── GROUP F: Demo flow unaffected ─────────────────────────────────────
        r = await c.post("/api/v1/demo/setup")
        assert r.status_code == 200
        demo = r.json()
        assert demo["status"] == "demo_ready"
        dpid = demo["product_id"]
        dkey = demo["api_key"]
        ok(f"F10 Demo setup still works pid={dpid[:8]}...")

        r = await c.get(f"/api/v1/products/{dpid}/motivations", headers={"X-API-Key": dkey})
        assert r.json()["total"] == 5
        ok("F11 Demo motivations readable via GET endpoint")

        r = await c.get(f"/api/v1/demo/{dpid}/users")
        assert r.json()["total_discovered"] == 847
        ok("F12 Demo users endpoint unaffected")

        r = await c.get(f"/api/v1/demo/{dpid}/leads")
        assert r.json()["hot_count"] == 4
        ok("F13 Demo leads endpoint unaffected")

        # ── GROUP G: Parser edge-cases ────────────────────────────────────────
        from app.ml.motivation_prompter import parse_motivation_response

        result = parse_motivation_response("not json at all !!!")
        assert result is None
        ok("G14 Garbage input -> parse returns None")

        partial = (
            '{ "motivation_categories": [ {"name": "Budget Shopper",'
            ' "description": "Buyers who want value for money",'
            ' "ocean": {"openness": 5.0, "conscientiousness": 8.0,'
            '           "extraversion": 3.0, "agreeableness": 7.0,'
            '           "emotional_stability": 6.0},'
            ' "interest_tags": ["deals"],'
            ' "search_keywords": ["cheap"],'
            ' "hashtags": ["#deal"]} '
        )
        result = parse_motivation_response(partial)
        assert result is not None and len(result) == 1
        ok("G15 Truncated JSON — brace-match recovers 1 partial category")

        bad_ocean = (
            '{ "motivation_categories": [ {"name": "Test",'
            ' "description": "Testing clamping for out-of-range OCEAN values",'
            ' "ocean": {"openness": 15.0, "conscientiousness": -2.0,'
            '           "extraversion": 5.0, "agreeableness": 5.0,'
            '           "emotional_stability": 5.0},'
            ' "interest_tags": ["test"],'
            ' "search_keywords": ["test"],'
            ' "hashtags": ["#test"]}]}'
        )
        result = parse_motivation_response(bad_ocean)
        assert result[0]["ocean"]["openness"] == 10.0
        assert result[0]["ocean"]["conscientiousness"] == 0.0
        ok("G16 Out-of-range OCEAN clamped to [0, 10]")

        # ── GROUP H: USE_MOCK_LLM fast path via direct service call ───────────
        from app.services.motivation_service import _build_fallback_categories, _ensure_five
        fallbacks = _build_fallback_categories("Drone Camera", "Electronics")
        assert len(fallbacks) == 5
        assert "Drone Camera" in fallbacks[0]["description"] or "Electronics" in fallbacks[0]["description"]
        ok("H17 _build_fallback_categories returns 5 product-aware categories")

        short = _build_fallback_categories("X", "Y")[:3]
        padded = _ensure_five(short, "Drone Camera", "Electronics")
        assert len(padded) == 5
        ok("H18 _ensure_five pads 3 -> 5 correctly")

        over = _build_fallback_categories("X", "Y") + [_build_fallback_categories("X","Y")[0]]
        trimmed = _ensure_five(over, "X", "Y")
        assert len(trimmed) == 5
        ok("H19 _ensure_five trims 6 -> 5 correctly")

    return RESULTS


if __name__ == "__main__":
    results = asyncio.run(run())
    passes = sum(1 for r, _ in results if r == "PASS")
    fails = sum(1 for r, _ in results if r == "FAIL")
    print()
    print("=" * 50)
    print(f"RESULTS: {passes} PASS   {fails} FAIL   (total {len(results)})")
    if fails:
        for r, n in results:
            if r == "FAIL":
                print(f"  FAIL: {n}")
    else:
        print("All tests passed.")
