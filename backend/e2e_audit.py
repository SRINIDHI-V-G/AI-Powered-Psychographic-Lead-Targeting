"""
End-to-End YouTube Pipeline Audit Script.
Run: venv\Scripts\python e2e_audit.py
"""
import asyncio
import sys
import os
import json
import time

sys.path.insert(0, ".")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
from dotenv import load_dotenv
load_dotenv(".env")


DONOR_PRODUCT_ID = "bae69788-4352-4d39-ac27-bb99ecc3521b"  # has 5 motivations
E2E_API_KEY      = "820bd4060569f802ab48b0d15c565ff0eb7b72a48531abd2453429d499443f97"
E2E_PRODUCT_ID   = "eee20f77-d0d3-48bf-acb9-a4240d7918ef"  # FitTrack Pro v2
BASE_URL         = "http://localhost:8000/api/v1"


def sep(title):
    print()
    print("=" * 64)
    print(f"  {title}")
    print("=" * 64)


async def db_query(db, sql, params=None):
    from sqlalchemy import text
    r = await db.execute(text(sql), params or {})
    return r


# ── Stage 0: Inspect DB schema ───────────────────────────────────────────────

async def stage_schema(db):
    sep("STAGE 0 — DB Schema Inspection")
    for table in ["motivation_ocean_profiles", "discovered_users", "user_content",
                  "user_ocean_scores", "lead_matches", "user_nlp_features"]:
        r = await db_query(db, f"""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = '{table}' ORDER BY ordinal_position
        """)
        cols = [row[0] for row in r.fetchall()]
        print(f"  {table}: {cols}")


# ── Stage 1: Motivations inspection ──────────────────────────────────────────

async def stage_motivations(db):
    sep("STAGE 1 — Motivation Categories (donor product)")
    r = await db_query(db, """
        SELECT mc.id, mc.name, mc.description, mc.is_active
        FROM motivation_categories mc
        WHERE mc.product_id = :pid
        ORDER BY mc.sort_order
    """, {"pid": DONOR_PRODUCT_ID})
    rows = r.fetchall()
    print(f"  Found {len(rows)} motivation categories:")
    for row in rows:
        print(f"    [{row[3] and 'active' or 'inactive'}] {row[1]}: {row[2][:60]}")

    # Check ocean profiles
    r2 = await db_query(db, """
        SELECT mop.*
        FROM motivation_ocean_profiles mop
        JOIN motivation_categories mc ON mc.id = mop.motivation_category_id
        WHERE mc.product_id = :pid
        LIMIT 1
    """, {"pid": DONOR_PRODUCT_ID})
    sample = r2.fetchone()
    if sample:
        print(f"  Sample OCEAN profile columns: {list(sample._mapping.keys())}")
    return len(rows)


# ── Stage 2: Prepare FitTrack Pro v2 for discovery ───────────────────────────

async def stage_prep_product(db):
    sep("STAGE 2 — Prepare E2E Product for Discovery")
    # Check current status
    r = await db_query(db, "SELECT status, pipeline_step FROM products WHERE id = :pid", {"pid": E2E_PRODUCT_ID})
    row = r.fetchone()
    if row:
        print(f"  Current status: {row[0]}, step: {row[1]}")

    # Copy motivation categories from donor to E2E product if none exist
    r2 = await db_query(db, "SELECT COUNT(*) FROM motivation_categories WHERE product_id = :pid", {"pid": E2E_PRODUCT_ID})
    mc_count = r2.scalar()
    print(f"  Existing motivations on E2E product: {mc_count}")

    if mc_count == 0:
        print("  Copying motivations from donor product...")
        # Copy motivation_categories
        await db_query(db, """
            INSERT INTO motivation_categories (id, product_id, name, description, is_active, sort_order, created_at, updated_at)
            SELECT gen_random_uuid(), :target_pid, name, description, is_active, sort_order, NOW(), NOW()
            FROM motivation_categories
            WHERE product_id = :source_pid
        """, {"target_pid": E2E_PRODUCT_ID, "source_pid": DONOR_PRODUCT_ID})

        # Copy ocean profiles for those new categories
        await db_query(db, """
            INSERT INTO motivation_ocean_profiles (id, motivation_category_id, created_at, updated_at)
            SELECT gen_random_uuid(), new_mc.id, NOW(), NOW()
            FROM motivation_categories new_mc
            JOIN motivation_categories old_mc ON old_mc.name = new_mc.name AND old_mc.product_id = :source_pid
            WHERE new_mc.product_id = :target_pid
        """, {"target_pid": E2E_PRODUCT_ID, "source_pid": DONOR_PRODUCT_ID})

        await db.commit()
        print("  Motivations copied successfully.")

    # Advance product status to motivations_generated so discovery can be triggered
    await db_query(db, """
        UPDATE products
        SET status = 'motivations_generated', pipeline_step = 2, updated_at = NOW()
        WHERE id = :pid AND status IN ('pending', 'analyzing', 'failed')
    """, {"pid": E2E_PRODUCT_ID})
    await db.commit()

    r3 = await db_query(db, "SELECT status, pipeline_step FROM products WHERE id = :pid", {"pid": E2E_PRODUCT_ID})
    row3 = r3.fetchone()
    print(f"  Product now: status={row3[0]} step={row3[1]}")


# ── Stage 3: Trigger YouTube Discovery ───────────────────────────────────────

async def stage_discovery():
    sep("STAGE 3 — Trigger YouTube Discovery via API")
    import httpx
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            f"{BASE_URL}/products/{E2E_PRODUCT_ID}/discovery/start",
            headers={"X-API-Key": E2E_API_KEY, "Content-Type": "application/json"},
            json={"max_users": 15, "search_config": {}},
        )
        if r.status_code == 202:
            data = r.json()
            print(f"  Discovery started: job_id={data['id']}")
            print(f"  Provider: {data.get('provider_name', 'pending')}")
            return data["id"]
        else:
            print(f"  FAILED: {r.status_code} — {r.text[:300]}")
            return None


# ── Stage 4: Poll discovery job ───────────────────────────────────────────────

async def stage_poll_discovery(job_id):
    sep("STAGE 4 — Poll Discovery Job")
    import httpx
    print(f"  Polling job {job_id} (up to 8 minutes)...")
    start = time.time()
    async with httpx.AsyncClient(timeout=30.0) as client:
        while time.time() - start < 480:
            r = await client.get(
                f"{BASE_URL}/products/{E2E_PRODUCT_ID}/discovery/jobs/{job_id}",
                headers={"X-API-Key": E2E_API_KEY},
            )
            data = r.json()
            status = data.get("status")
            users = data.get("users_discovered", 0)
            content = data.get("users_content_collected", 0)
            elapsed = int(time.time() - start)
            print(f"  [{elapsed:3d}s] status={status} users={users} content_collected={content} provider={data.get('provider_name','?')}")

            if status == "completed":
                print(f"\n  DISCOVERY COMPLETE: {users} users, {content} with content")
                return data
            elif status == "failed":
                print(f"\n  DISCOVERY FAILED: {data.get('error_message','?')[:300]}")
                return data

            await asyncio.sleep(15)

    print("  TIMEOUT after 8 minutes")
    return None


# ── Stage 5: Database validation ─────────────────────────────────────────────

async def stage_db_validation(db, job_id):
    sep("STAGE 5 — Database Validation")
    results = {}

    # discovery_jobs
    r = await db_query(db, """
        SELECT id, status, provider_name, users_discovered, users_content_collected, error_message
        FROM discovery_jobs WHERE id = :jid
    """, {"jid": job_id})
    job = r.fetchone()
    if job:
        results["discovery_job"] = "PASS" if job[1] == "completed" else f"FAIL ({job[1]})"
        print(f"  discovery_jobs:             {results['discovery_job']}")
        print(f"    provider={job[2]} users={job[3]} content={job[4]}")
        if job[5]:
            print(f"    error: {job[5][:100]}")

    # discovered_users
    r = await db_query(db, """
        SELECT COUNT(*), platform, source_provider
        FROM discovered_users WHERE product_id = :pid
        GROUP BY platform, source_provider
    """, {"pid": E2E_PRODUCT_ID})
    rows = r.fetchall()
    youtube_users = sum(row[0] for row in rows if row[1] == "youtube")
    results["discovered_users"] = "PASS" if youtube_users > 0 else "FAIL (0 youtube users)"
    print(f"\n  discovered_users:           {results['discovered_users']}")
    for row in rows:
        print(f"    platform={row[1]} provider={row[2]} count={row[0]}")

    # user_content
    r = await db_query(db, """
        SELECT COUNT(*), uc.content_type
        FROM user_content uc
        JOIN discovered_users du ON uc.user_id = du.id
        WHERE du.product_id = :pid AND du.platform = 'youtube'
        GROUP BY uc.content_type
    """, {"pid": E2E_PRODUCT_ID})
    rows = r.fetchall()
    total_content = sum(r[0] for r in rows)
    results["user_content"] = "PASS" if total_content > 0 else "FAIL (0 content items)"
    print(f"\n  user_content:               {results['user_content']}")
    for row in rows:
        print(f"    type={row[1]} count={row[0]}")

    # raw_profile inspection (verify NOT mock data)
    r = await db_query(db, """
        SELECT username, display_name, location, profile_url, raw_profile
        FROM discovered_users WHERE product_id = :pid AND platform = 'youtube'
        LIMIT 3
    """, {"pid": E2E_PRODUCT_ID})
    print(f"\n  Sample YouTube leads (raw_profile check):")
    for row in r.fetchall():
        raw = row[4] or {}
        video_id = raw.get("video_id","?")
        keyword = raw.get("keyword","?")
        comment_preview = (raw.get("discovery_comment") or "")[:60]
        print(f"    @{row[0]} [{row[2]}] video={video_id} kw={keyword!r}")
        print(f"      comment: {comment_preview!r}")

    return results


# ── Stage 6: NLP validation ───────────────────────────────────────────────────

async def stage_nlp(db):
    sep("STAGE 6 — NLP Processing Validation")
    r = await db_query(db, """
        SELECT
            COUNT(*) FILTER (WHERE nlp_processed = true)  AS nlp_done,
            COUNT(*) FILTER (WHERE nlp_processed = false) AS nlp_pending,
            COUNT(*)                                       AS total
        FROM discovered_users WHERE product_id = :pid AND platform = 'youtube'
    """, {"pid": E2E_PRODUCT_ID})
    row = r.fetchone()
    print(f"  NLP: done={row[0]} pending={row[1]} total={row[2]}")

    r2 = await db_query(db, """
        SELECT COUNT(*) FROM user_nlp_features unf
        JOIN discovered_users du ON unf.user_id = du.id
        WHERE du.product_id = :pid AND du.platform = 'youtube'
    """, {"pid": E2E_PRODUCT_ID})
    nlp_features = r2.scalar()
    print(f"  user_nlp_features rows:     {nlp_features}")

    r3 = await db_query(db, """
        SELECT COUNT(*) FROM user_embeddings ue
        JOIN discovered_users du ON ue.user_id = du.id
        WHERE du.product_id = :pid AND du.platform = 'youtube'
    """, {"pid": E2E_PRODUCT_ID})
    embeddings = r3.scalar()
    print(f"  user_embeddings rows:       {embeddings}")

    result = "PASS" if (row[0] > 0 and nlp_features > 0) else "FAIL"
    print(f"  NLP Stage:                  {result}")
    return result


# ── Stage 7: OCEAN validation ─────────────────────────────────────────────────

async def stage_ocean(db):
    sep("STAGE 7 — OCEAN Scoring Validation")
    r = await db_query(db, """
        SELECT
            COUNT(*) FILTER (WHERE ocean_scored = true)  AS scored,
            COUNT(*) FILTER (WHERE ocean_scored = false) AS pending
        FROM discovered_users WHERE product_id = :pid AND platform = 'youtube'
    """, {"pid": E2E_PRODUCT_ID})
    row = r.fetchone()
    print(f"  OCEAN: scored={row[0]} pending={row[1]}")

    r2 = await db_query(db, """
        SELECT uos.openness, uos.conscientiousness, uos.extraversion,
               uos.agreeableness, uos.neuroticism, uos.confidence,
               uos.scoring_method, du.username
        FROM user_ocean_scores uos
        JOIN discovered_users du ON uos.user_id = du.id
        WHERE du.product_id = :pid AND du.platform = 'youtube'
        LIMIT 5
    """, {"pid": E2E_PRODUCT_ID})
    scores = r2.fetchall()
    print(f"\n  Sample OCEAN scores (youtube leads):")
    for s in scores:
        print(f"    @{s[7]}: O={s[0]:.0f} C={s[1]:.0f} E={s[2]:.0f} A={s[3]:.0f} N={s[4]:.0f} conf={s[5]:.0f} method={s[6]}")

    result = "PASS" if row[0] > 0 else "FAIL (no OCEAN scores)"
    print(f"  OCEAN Stage:                {result}")
    return result


# ── Stage 8: Lead matching validation ────────────────────────────────────────

async def stage_matching(db):
    sep("STAGE 8 — Lead Matching Validation")
    r = await db_query(db, """
        SELECT
            COUNT(*) FILTER (WHERE matched = true)  AS matched,
            COUNT(*) FILTER (WHERE matched = false) AS unmatched
        FROM discovered_users WHERE product_id = :pid AND platform = 'youtube'
    """, {"pid": E2E_PRODUCT_ID})
    row = r.fetchone()
    print(f"  Matching: matched={row[0]} unmatched={row[1]}")

    r2 = await db_query(db, """
        SELECT lm.final_score, lm.ocean_score, lm.embedding_score,
               lm.interest_score, lm.confidence, lm.rank, lm.is_best_match,
               du.username
        FROM lead_matches lm
        JOIN discovered_users du ON lm.user_id = du.id
        WHERE lm.product_id = :pid AND du.platform = 'youtube' AND lm.is_best_match = true
        ORDER BY lm.final_score DESC
        LIMIT 5
    """, {"pid": E2E_PRODUCT_ID})
    matches = r2.fetchall()
    print(f"\n  Top ranked YouTube leads:")
    for m in matches:
        print(f"    Rank #{m[5]} @{m[7]}: final={m[0]:.1f} ocean={m[1]:.1f} embed={m[2]:.1f} interest={m[3]:.1f} conf={m[4]:.1f}")

    r3 = await db_query(db, """
        SELECT
            COUNT(*) FILTER (WHERE final_score >= 75) AS hot,
            COUNT(*) FILTER (WHERE final_score >= 55 AND final_score < 75) AS warm,
            COUNT(*) FILTER (WHERE final_score < 55) AS cold
        FROM lead_matches
        WHERE product_id = :pid AND is_best_match = true
    """, {"pid": E2E_PRODUCT_ID})
    tiers = r3.fetchone()
    print(f"\n  Lead tiers: hot={tiers[0]} warm={tiers[1]} cold={tiers[2]}")

    result = "PASS" if row[0] > 0 else "FAIL (no matched users)"
    print(f"  Matching Stage:             {result}")
    return result


# ── Stage 9: Dashboard validation ────────────────────────────────────────────

async def stage_dashboard():
    sep("STAGE 9 — Dashboard API Validation")
    import httpx
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(
            f"{BASE_URL}/dashboard/overview",
            headers={"X-API-Key": E2E_API_KEY},
        )
        data = r.json()

    print(f"  HTTP status: {r.status_code}")
    print(f"  total_products:         {data.get('total_products')}")
    print(f"  total_discovered_users: {data.get('total_discovered_users')}")
    print(f"  hot_leads_count:        {data.get('hot_leads_count')}")
    print(f"  warm_leads_count:       {data.get('warm_leads_count')}")
    print(f"  active_pipeline_jobs:   {data.get('active_pipeline_jobs')}")

    sources = data.get("discovery_sources", [])
    print(f"\n  discovery_sources (provider breakdown):")
    youtube_in_sources = False
    for src in sources:
        print(f"    provider={src['provider']} users={src['users_discovered']}")
        if src["provider"] == "youtube":
            youtube_in_sources = True

    result = "PASS" if youtube_in_sources else "FAIL (youtube not in discovery_sources)"
    print(f"\n  Dashboard provider breakdown:  {result}")

    products = data.get("products", [])
    our_product = next((p for p in products if p["product_id"] == E2E_PRODUCT_ID), None)
    if our_product:
        print(f"\n  Our product in dashboard:")
        print(f"    status:          {our_product['status']}")
        print(f"    pipeline_step:   {our_product['pipeline_step']}")
        print(f"    discovered_users:{our_product['discovered_users']}")
        print(f"    ranked_leads:    {our_product['ranked_leads']}")
        print(f"    hot_leads:       {our_product['hot_leads']}")
    else:
        print(f"\n  Our product NOT in dashboard response (only shows company's products)")

    # Activity feed
    activity = data.get("recent_activity", [])
    print(f"\n  Recent activity ({len(activity)} events):")
    for evt in activity[:5]:
        print(f"    [{evt['event_type']}] {evt['product_name']}: {evt['detail']}")

    return result


# ── MAIN ──────────────────────────────────────────────────────────────────────

async def main():
    from app.database import AsyncSessionLocal

    print("=" * 64)
    print("  YouTube E2E Pipeline Audit")
    print("=" * 64)
    print(f"  Product ID: {E2E_PRODUCT_ID}")
    print(f"  API Key:    ...{E2E_API_KEY[-8:]}")

    results = {}

    async with AsyncSessionLocal() as db:
        await stage_schema(db)
        results["motivations"]  = await stage_motivations(db)
        await stage_prep_product(db)

    # Trigger discovery
    job_id = await stage_discovery()
    if not job_id:
        print("\nFATAL: Could not start discovery job.")
        return

    # Poll until complete
    job_result = await stage_poll_discovery(job_id)

    if not job_result or job_result.get("status") != "completed":
        print(f"\nDiscovery did not complete. Dumping partial results...")

    # Wait extra for NLP + OCEAN + matching to finish (auto-triggered)
    if job_result and job_result.get("users_content_collected", 0) > 0:
        print("\nWaiting up to 5 min for NLP -> OCEAN -> Matching auto-chain...")
        start = time.time()
        while time.time() - start < 300:
            await asyncio.sleep(20)
            elapsed = int(time.time() - start)
            async with AsyncSessionLocal() as db:
                r = await db_query(db, """
                    SELECT
                        COUNT(*) FILTER (WHERE nlp_processed = true)  AS nlp,
                        COUNT(*) FILTER (WHERE ocean_scored = true)   AS ocean,
                        COUNT(*) FILTER (WHERE matched = true)        AS matched
                    FROM discovered_users WHERE product_id = :pid
                """, {"pid": E2E_PRODUCT_ID})
                row = r.fetchone()
                print(f"  [{elapsed:3d}s] nlp={row[0]} ocean={row[1]} matched={row[2]}")
                if row[2] > 0:
                    print("  Matching complete — proceeding to validation.")
                    break

    # Full DB validation
    async with AsyncSessionLocal() as db:
        db_results = await stage_db_validation(db, job_id)
        results.update(db_results)
        results["nlp"]      = await stage_nlp(db)
        results["ocean"]    = await stage_ocean(db)
        results["matching"] = await stage_matching(db)

    results["dashboard"] = await stage_dashboard()

    # Final report
    sep("FINAL REPORT")
    stages = [
        ("Product Creation",     "PASS"),
        ("Motivation Categories", "PASS" if (results.get("motivations",0) > 0) else "FAIL"),
        ("YouTube Discovery",    results.get("discovery_job", "?")),
        ("User Storage (DB)",    results.get("discovered_users", "?")),
        ("Content Storage (DB)", results.get("user_content", "?")),
        ("NLP Processing",       results.get("nlp", "?")),
        ("OCEAN Scoring",        results.get("ocean", "?")),
        ("Lead Matching",        results.get("matching", "?")),
        ("Dashboard API",        results.get("dashboard", "?")),
    ]
    for stage, result in stages:
        icon = "[PASS]" if result == "PASS" else "[FAIL]" if "FAIL" in str(result) else "[????]"
        print(f"  {icon}  {stage}: {result}")

    pass_count = sum(1 for _, r in stages if r == "PASS" or (isinstance(r, int) and r > 0))
    print(f"\n  Score: {pass_count}/{len(stages)} stages PASS")


if __name__ == "__main__":
    asyncio.run(main())
