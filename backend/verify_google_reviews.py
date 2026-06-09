"""
verify_google_reviews.py -- Full E2E verification for Google Reviews provider.

Tests the complete pipeline:
  GoogleReviewsProvider -> Discovery -> Content -> NLP -> OCEAN -> Leads -> Dashboard

Usage:
  cd backend
  venv/Scripts/python verify_google_reviews.py

Requirements:
  - Backend running on localhost:8000
  - GOOGLE_PLACES_API_KEY configured in .env
  - Database accessible
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime

BASE = "http://localhost:8000"
API_KEY = "psycholead-dev-3ac99095"
HEADERS = {"X-API-Key": API_KEY, "Content-Type": "application/json"}


# -- HTTP helpers --------------------------------------------------------------

def _request(method: str, path: str, body: dict | None = None, timeout: int = 30) -> dict:
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=HEADERS, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode()
        raise RuntimeError(f"HTTP {e.code} {method} {path}: {detail[:300]}")


def get(path: str, timeout: int = 30) -> dict:
    return _request("GET", path, timeout=timeout)


def post(path: str, body: dict, timeout: int = 30) -> dict:
    return _request("POST", path, body, timeout=timeout)


# -- Result tracker ------------------------------------------------------------

results: list[tuple[str, str, str]] = []   # (step, status, detail)


def report(step: str, ok: bool, detail: str = "") -> None:
    status = "PASS" if ok else "FAIL"
    results.append((step, status, detail))
    icon = "[OK] " if ok else "[ERR]"
    print(f"  {icon} [{status}] {step}")
    if detail:
        print(f"         {detail}")


def section(title: str) -> None:
    print(f"\n{'-'*60}")
    print(f"  {title}")
    print(f"{'-'*60}")


# -- Verification steps -------------------------------------------------------

def step1_backend_health() -> bool:
    section("STEP 1 -- Backend Health")
    try:
        d = get("/health")
        ok = d.get("status") == "ok" and d.get("database") == "connected"
        report("Backend reachable", ok, f"status={d.get('status')} db={d.get('database')}")
        return ok
    except Exception as e:
        report("Backend reachable", False, str(e))
        return False


def step2_provider_health() -> bool:
    section("STEP 2 -- Provider Health Check")
    try:
        d = get("/api/v1/discovery/provider/status")
        gr = d.get("google_reviews", {})
        configured = gr.get("configured", False)
        healthy = gr.get("healthy", False)
        detail = gr.get("detail", "")
        report("google_reviews key in status response", "google_reviews" in d,
               f"keys={list(d.keys())}")
        report("google_reviews configured=True", configured, detail)
        report("google_reviews healthy=True", healthy, detail)
        report("mock_mode is False", not d.get("mock_mode", True),
               f"mock_mode={d.get('mock_mode')}")
        return configured and healthy
    except Exception as e:
        report("Provider health check endpoint", False, str(e))
        return False


def step3_create_product() -> str | None:
    section("STEP 3 -- Create Product for Google Reviews Discovery")
    try:
        products = get("/api/v1/products/")
        for p in products:
            if p.get("name") == "GR-Verify-Sofa":
                prod_id = p["id"]
                report("Test product found (reusing)", True,
                       f"id={prod_id[:8]}... status={p['status']}")
                return prod_id

        body = {
            "name": "GR-Verify-Sofa",
            "description": "Premium modular sofa for Chennai living rooms -- Google Reviews E2E test",
            "category": "Furniture",
            "price_range": "premium",
            "target_location": "Chennai",
            "keywords": ["modular sofa", "furniture store Chennai", "interior design"],
        }
        p = post("/api/v1/products/", body)
        prod_id = p["id"]
        report("Product created", True, f"id={prod_id[:8]}... status={p['status']}")
        return prod_id
    except Exception as e:
        report("Create product", False, str(e))
        return None


def step4_advance_to_discovery_ready(prod_id: str) -> bool:
    section("STEP 4 -- Advance Product to Discovery-Ready State")
    # Product creation auto-triggers motivation generation in the background.
    # We just poll until the status reaches one of the discovery-ready states.
    try:
        discovery_ready = {
            "motivations_generated", "discovering", "nlp_processing",
            "ocean_scoring", "matching", "ranked", "completed",
            "product_ocean_ready", "similar_products_found",
        }
        print("         Polling for motivations to complete (auto-triggered at creation)...")
        for i in range(36):   # up to 3 minutes
            time.sleep(5)
            p = get(f"/api/v1/products/{prod_id}")
            status = p.get("status", "")
            step = p.get("pipeline_step", 0)
            print(f"         [{(i+1)*5}s] status={status} step={step}")
            if status in discovery_ready:
                report("Product reached discovery-ready state", True,
                       f"status={status} step={step}")
                return True
            if "error" in status or "failed" in status:
                report("Motivations failed", False, f"status={status}")
                return False

        p = get(f"/api/v1/products/{prod_id}")
        status = p.get("status", "")
        report("Product discovery-ready (timed out)", False,
               f"last_status={status}. Check Ollama is running.")
        return False
    except Exception as e:
        report("Advance to discovery-ready", False, str(e))
        return False


def step5_run_discovery(prod_id: str) -> str | None:
    section("STEP 5 -- Run Discovery with Google Reviews Provider")
    try:
        body = {
            "max_users": 15,
            "search_config": {
                "preferred_provider": "google_reviews",
            },
        }
        job = post(f"/api/v1/products/{prod_id}/discovery/start", body)
        job_id = job["id"]
        report("Discovery job created (202 Accepted)", True, f"job_id={job_id[:8]}...")
        print("         Polling for completion (max 180s)...")

        for i in range(36):
            time.sleep(5)
            j = get(f"/api/v1/products/{prod_id}/discovery/jobs/{job_id}", timeout=60)
            status = j.get("status", "")
            discovered = j.get("users_discovered", 0)
            content = j.get("users_content_collected", 0)
            provider = j.get("provider_name", "?")
            print(f"         [{(i+1)*5}s] status={status} provider={provider} "
                  f"users={discovered} content={content}")

            if status == "completed":
                report("Job completed successfully", True, f"status={status}")
                report("Provider used is google_reviews", provider == "google_reviews",
                       f"provider_name={provider}")
                if discovered == 0:
                    report("Users discovered > 0", False,
                           "0 users found. BILLING REQUIRED: enable GCP billing "
                           "(Atmosphere tier) at console.cloud.google.com -> Billing. "
                           "The $200/month free credit covers all dev usage.")
                    return None
                report("Users discovered > 0", True, f"users_discovered={discovered}")
                report("Content collected > 0", content > 0,
                       f"users_content_collected={content}")
                return job_id

            if status == "failed":
                err = j.get("error_message", "unknown error")
                report("Discovery job failed", False, err[:200])
                return None

        report("Discovery job timed out", False, "still running after 180s")
        return None
    except Exception as e:
        report("Run discovery job", False, str(e))
        return None


def step6_verify_users_and_content(prod_id: str, job_id: str) -> str | None:
    section("STEP 6 -- Verify Discovered Users & Review Content")
    try:
        resp = get(f"/api/v1/products/{prod_id}/discovery/users?job_id={job_id}&limit=5")
        users = resp.get("users", [])
        total = resp.get("total", 0)

        report("Discovery users endpoint returns data", total > 0, f"total={total}")
        if not users:
            return None

        u = users[0]
        user_id = u["id"]
        platform = u.get("platform", "")
        loc_conf = u.get("location_confidence", "")
        content_collected = u.get("content_collected", False)

        report("User platform == google_reviews", platform == "google_reviews",
               f"platform={platform}")
        report("Location confidence is inferred or confirmed",
               loc_conf in ("inferred", "confirmed"),
               f"location_confidence={loc_conf} location={u.get('location')}")
        report("content_collected flag is True", content_collected,
               f"content_collected={content_collected}")

        content = get(f"/api/v1/products/{prod_id}/discovery/users/{user_id}/content")
        has_content = len(content) > 0
        if has_content:
            first = content[0]
            report("Review text in content items", bool(first.get("content_text")),
                   f"type={first.get('content_type')} "
                   f"len={len(first.get('content_text',''))} chars")
            print(f"\n         Sample review text:")
            print(f"         \"{first.get('content_text','')[:200]}\"")
        else:
            report("Content items present", False, "empty content list")

        return user_id
    except Exception as e:
        report("Verify users and content", False, str(e))
        return None


def step7_verify_nlp(prod_id: str) -> bool:
    section("STEP 7 -- Verify NLP Processing")
    try:
        print("         Waiting for NLP pipeline (auto-triggered after discovery)...")
        nlp_statuses = {"nlp_processing", "ocean_scoring", "matching", "ranked",
                        "completed", "product_ocean_ready"}
        for i in range(30):
            time.sleep(5)
            p = get(f"/api/v1/products/{prod_id}")
            status = p.get("status", "")
            step_n = p.get("pipeline_step", 0)
            print(f"         [{(i+1)*5}s] status={status} step={step_n}")
            if status in nlp_statuses or step_n >= 6:
                report("NLP pipeline triggered and advanced", True,
                       f"status={status} step={step_n}")
                return True
            if "error" in status or "failed" in status:
                report("NLP pipeline failed", False, f"status={status}")
                return False

        resp = get(f"/api/v1/products/{prod_id}/discovery/users?limit=5")
        users = resp.get("users", [])
        nlp_done = any(u.get("nlp_processed") for u in users)
        report("NLP processed flag on at least one user", nlp_done,
               f"checked {len(users)} users")
        return nlp_done
    except Exception as e:
        report("Verify NLP", False, str(e))
        return False


def step8_verify_ocean(prod_id: str) -> bool:
    section("STEP 8 -- Verify OCEAN Scoring")
    try:
        p = get(f"/api/v1/products/{prod_id}")
        status = p.get("status", "")
        step_n = p.get("pipeline_step", 0)

        ocean_statuses = {"ocean_scoring", "matching", "ranked", "completed",
                          "product_ocean_ready"}
        if status not in ocean_statuses and step_n < 7:
            print("         Waiting for OCEAN pipeline...")
            for i in range(24):
                time.sleep(5)
                p = get(f"/api/v1/products/{prod_id}")
                status = p.get("status", "")
                step_n = p.get("pipeline_step", 0)
                print(f"         [{(i+1)*5}s] status={status} step={step_n}")
                if status in ocean_statuses or step_n >= 7:
                    break

        report("OCEAN pipeline advanced", status in ocean_statuses or step_n >= 7,
               f"status={status} step={step_n}")

        resp = get(f"/api/v1/products/{prod_id}/discovery/users?limit=10")
        users = resp.get("users", [])
        ocean_users = [u for u in users if u.get("ocean_scored")]
        report("Users have OCEAN scores", len(ocean_users) > 0,
               f"{len(ocean_users)}/{len(users)} users scored")
        return len(ocean_users) > 0
    except Exception as e:
        report("Verify OCEAN", False, str(e))
        return False


def step9_verify_leads(prod_id: str) -> bool:
    section("STEP 9 -- Verify Lead Generation")
    try:
        p = get(f"/api/v1/products/{prod_id}")
        status = p.get("status", "")
        step_n = p.get("pipeline_step", 0)

        lead_statuses = {"matching", "ranked", "completed"}
        if status not in lead_statuses and step_n < 8:
            print("         Waiting for lead matching pipeline...")
            for i in range(24):
                time.sleep(5)
                p = get(f"/api/v1/products/{prod_id}")
                status = p.get("status", "")
                step_n = p.get("pipeline_step", 0)
                print(f"         [{(i+1)*5}s] status={status} step={step_n}")
                if status in lead_statuses or step_n >= 8:
                    break

        report("Lead matching pipeline reached", status in lead_statuses or step_n >= 8,
               f"status={status} step={step_n}")

        for path in [f"/api/v1/products/{prod_id}/leads/",
                     f"/api/v1/products/{prod_id}/leads"]:
            try:
                leads = get(path)
                count = len(leads) if isinstance(leads, list) else leads.get("total", 0)
                has_leads = count > 0
                report("Leads created in DB", has_leads, f"count={count}")
                return has_leads
            except Exception:
                continue

        report("Leads endpoint", False, "no /leads or /leads/ endpoint found")
        return False
    except Exception as e:
        report("Verify leads", False, str(e))
        return False


def step10_verify_dashboard(prod_id: str) -> bool:
    section("STEP 10 -- Verify Dashboard Visibility")
    try:
        products = get("/api/v1/products/")
        prod_ids = [p["id"] for p in products]
        report("Product visible in /api/v1/products/ list",
               prod_id in prod_ids, f"total_products={len(products)}")

        resp = get(f"/api/v1/products/{prod_id}/discovery/users?limit=10")
        total = resp.get("total", 0)
        report("Discovery users visible (dashboard Discovery tab)",
               total > 0, f"total={total}")

        try:
            req = urllib.request.Request("http://localhost:3000", method="GET")
            with urllib.request.urlopen(req, timeout=5) as r:
                frontend_ok = r.status == 200
            report("Frontend dashboard serving (port 3000)",
                   frontend_ok, f"HTTP status={r.status}")
        except Exception as fe:
            report("Frontend dashboard serving", False, str(fe))

        users = resp.get("users", [])
        gr_users = [u for u in users if u.get("platform") == "google_reviews"]
        report("Users have platform=google_reviews",
               len(gr_users) > 0, f"{len(gr_users)}/{len(users)} are google_reviews")

        return total > 0
    except Exception as e:
        report("Verify dashboard", False, str(e))
        return False


# -- Main ---------------------------------------------------------------------

def main() -> None:
    print("\n" + "="*60)
    print("  GOOGLE REVIEWS PROVIDER -- E2E VERIFICATION")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)

    if not step1_backend_health():
        print("\n[ERR] Backend not reachable. Start with:")
        print("      cd backend && venv/Scripts/python -m uvicorn app.main:app --reload")
        _print_summary()
        sys.exit(1)

    step2_provider_health()

    prod_id = step3_create_product()
    if not prod_id:
        _print_summary()
        sys.exit(1)

    if not step4_advance_to_discovery_ready(prod_id):
        _print_summary()
        sys.exit(1)

    job_id = step5_run_discovery(prod_id)
    if not job_id:
        _print_summary()
        sys.exit(1)

    step6_verify_users_and_content(prod_id, job_id)
    step7_verify_nlp(prod_id)
    step8_verify_ocean(prod_id)
    step9_verify_leads(prod_id)
    step10_verify_dashboard(prod_id)

    _print_summary()


def _print_summary() -> None:
    print("\n" + "="*60)
    print("  VERIFICATION SUMMARY")
    print("="*60)
    passed = [r for r in results if r[1] == "PASS"]
    failed = [r for r in results if r[1] == "FAIL"]
    for step, status, detail in results:
        icon = "[OK] " if status == "PASS" else "[ERR]"
        line = f"  {icon} {step}"
        if detail and status == "FAIL":
            line += f"\n       -> {detail[:120]}"
        print(line)
    print(f"\n  Total: {len(passed)} PASS  /  {len(failed)} FAIL  /  {len(results)} checks")
    verdict = "PASS" if len(failed) == 0 else "FAIL"
    print(f"\n  Overall Verdict: {verdict}")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
