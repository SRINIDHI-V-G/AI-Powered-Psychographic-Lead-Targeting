"""
End-to-end pipeline verification for Instagram-discovered users.

Calls each pipeline stage directly (no auto-triggering) to avoid
double-execution races.  Resets scores so every run produces fresh results.

  Instagram → DB → NLP → OCEAN (Ollama) → Matching → Ranking → Dashboard

Usage:
  cd backend
  python verify_pipeline_e2e.py

Requirements:
  - backend/.env with Instagram + Ollama config
  - Ollama running: ollama serve
  - Model downloaded: ollama pull <OLLAMA_MODEL>
  - PostgreSQL accessible via DATABASE_URL
"""
from __future__ import annotations

import asyncio
import logging
import sys
from uuid import UUID

sys.stdout.reconfigure(encoding="utf-8")

# Show only WARNING+ from SQLAlchemy; let app logs through at INFO+
logging.basicConfig(level=logging.WARNING)
logging.getLogger("app").setLevel(logging.INFO)

SEP  = "=" * 60
SEP2 = "-" * 60

PRODUCT_ID   = "0c32addb-5810-4de4-a49e-20ce510e8c37"
PRODUCT_NAME = "Premium Luxury Sofa"
SEED_ACCOUNTS = ["woodenstreet", "urbanladder", "pepperfry"]
KEYWORDS      = ["interior design", "home decor", "luxury sofa", "premium furniture"]
MAX_USERS     = 10


async def main() -> None:
    print(SEP)
    print("E2E PIPELINE VERIFICATION — Instagram → Dashboard")
    print(f"Product : {PRODUCT_NAME}")
    print(SEP)

    from app.config import settings
    from app.database import AsyncSessionLocal
    from app.crud.discovery import create_discovery_job
    from app.ml.discovery.instagram_provider import InstagramProvider
    from app.ml.discovery.orchestrator import DiscoveryOrchestrator
    from app.services.nlp_service import run_nlp_for_product
    from app.services.ocean_service import run_ocean_for_product
    from app.services.matching_service import run_matching_for_product

    db_sync_url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")

    # ── [0] Pre-flight ────────────────────────────────────────────────────────
    print("\n[0] Pre-flight checks")
    _assert_product_exists(db_sync_url)
    await _check_ollama(settings)

    # ── [1] Instagram discovery ───────────────────────────────────────────────
    print(f"\n{SEP2}")
    print("[1] INSTAGRAM DISCOVERY")
    print(SEP2)

    existing_count = _count_ig_users(db_sync_url)
    print(f"  Existing Instagram users in DB: {existing_count}")

    if existing_count > 0:
        print(f"  Skipping live discovery — using {existing_count} existing users from DB")
        print(f"  (To re-discover: resolve Instagram challenge and delete instagram_session.json)")
    else:
        # Run live discovery only when DB is empty
        print("  Initialising InstagramProvider...")
        try:
            provider = InstagramProvider()
        except RuntimeError as e:
            print(f"  FAIL: {e}")
            return

        health = await provider.health_check()
        print(f"  Health: {'OK' if health['ok'] else 'FAIL'} — {health['detail']}")
        if not health["ok"]:
            print("  Instagram unavailable and no existing users — cannot proceed.")
            return

        print(f"  discover_users(keywords={KEYWORDS[:2]}... seed={SEED_ACCOUNTS}) ...")
        raw_users = await provider.discover_users(
            keywords=KEYWORDS,
            target_city="Chennai",
            max_users=MAX_USERS,
            search_config={"seed_accounts": SEED_ACCOUNTS},
        )
        print(f"  Discovered: {len(raw_users)} users")
        for u in raw_users:
            print(f"    @{u.username} | method={u.raw_profile.get('discovery_method','?')} | followers={u.follower_count}")

        if not raw_users:
            print("  No users found — check session / seed accounts. Exiting.")
            return

        # ── Persist users + content ───────────────────────────────────────────
        print(f"\n{SEP2}")
        print("[2] PERSISTING USERS + CONTENT → DB")
        print(SEP2)

        orchestrator = DiscoveryOrchestrator()
        async with AsyncSessionLocal() as db:
            job = await create_discovery_job(
                db=db,
                product_id=UUID(PRODUCT_ID),
                max_users=MAX_USERS,
                search_config={"seed_accounts": SEED_ACCOUNTS, "provider": "instagram"},
            )
            job.provider_name = "instagram"
            job.sources = ["instagram"]
            job.status = "collecting"
            await db.commit()
            print(f"  Created discovery job: {str(job.id)[:8]}...")

            n_persisted = 0
            n_content   = 0
            for raw in raw_users:
                du = await orchestrator._upsert_user(db, job, raw)
                if du is None:
                    print(f"    @{raw.username}: already in DB — skipped")
                    continue
                try:
                    items = await provider.collect_content(raw, max_items=settings.DISCOVERY_CONTENT_PER_USER)
                    await orchestrator._persist_content(db, du.id, items)
                    du.content_collected = True
                    job.users_content_collected += 1
                    n_content += len(items)
                    print(f"    @{raw.username}: {len(items)} content items")
                except Exception as exc:
                    print(f"    @{raw.username}: content error — {exc}")
                n_persisted += 1

            job.users_discovered = n_persisted
            job.status = "completed"
            await db.commit()

        print(f"  Persisted: {n_persisted} new users, {n_content} content items")

    _show_users(db_sync_url)

    # ── [2b] Reset OCEAN flags so every run re-scores with Ollama ─────────────
    print(f"\n  Resetting ocean_scored + deleting stale OCEAN rows for re-scoring...")
    _reset_ocean_scores(db_sync_url)

    # ── [3] NLP Processing ────────────────────────────────────────────────────
    print(f"\n{SEP2}")
    print("[3] NLP PROCESSING")
    print(SEP2)
    async with AsyncSessionLocal() as db:
        summary = await run_nlp_for_product(db, UUID(PRODUCT_ID))
        await db.commit()
    print(f"  NLP: processed={summary['processed']} failed={summary['failed']}")
    _show_nlp(db_sync_url)

    # ── [4] OCEAN Scoring (Ollama LLM) ────────────────────────────────────────
    print(f"\n{SEP2}")
    print("[4] OCEAN SCORING (Ollama)")
    print(SEP2)
    print(f"  Model: {settings.OLLAMA_MODEL}")
    ocean_ok = False
    async with AsyncSessionLocal() as db:
        try:
            summary = await run_ocean_for_product(db, UUID(PRODUCT_ID))
            await db.commit()
            print(f"  OCEAN: processed={summary['processed']} failed={summary['failed']}")
            ocean_ok = summary["processed"] > 0
        except Exception as e:
            print(f"  OCEAN error: {e}")
    _show_ocean(db_sync_url)

    if not ocean_ok:
        print(f"\n  [!] OCEAN scoring produced 0 results.")
        print(f"      Check Ollama: ollama serve && ollama run {settings.OLLAMA_MODEL}")
        print(f"      Or set USE_MOCK_LLM=true in .env for heuristic mode.")

    # ── [5] Lead Matching + Ranking ───────────────────────────────────────────
    print(f"\n{SEP2}")
    print("[5] LEAD MATCHING + RANKING")
    print(SEP2)
    async with AsyncSessionLocal() as db:
        try:
            from app.models.product import Product, ProductStatus
            summary = await run_matching_for_product(db, UUID(PRODUCT_ID))
            # Advance product status to 'ranked' (step 9) — mirrors start_matching_background
            product = await db.get(Product, UUID(PRODUCT_ID))
            if product and summary["processed"] > 0:
                product.status = ProductStatus.ranked
                product.pipeline_step = 9
            await db.commit()
            print(f"  Matching: processed={summary['processed']} failed={summary['failed']}")
        except Exception as e:
            print(f"  Matching error: {e}")
    _show_leads(db_sync_url)

    # ── [6] Verification report ───────────────────────────────────────────────
    print(f"\n{SEP}")
    print("VERIFICATION REPORT")
    print(SEP)
    _show_summary(db_sync_url, ocean_ok)
    _print_sql()
    _print_api()


# ── Async helpers ─────────────────────────────────────────────────────────────

async def _check_ollama(settings) -> None:
    from app.ml.llm_client import OllamaClient
    client = OllamaClient()
    result = await client.health_check()
    print(f"  Ollama reachable : {result['reachable']}")
    print(f"  Configured model : {result['configured_model']}")
    print(f"  Model available  : {result['model_available']}")
    if result["error"]:
        print(f"  Error: {result['error']}")
    if not result["reachable"]:
        print("  [!] Ollama not running — start with: ollama serve")
    elif not result["model_available"]:
        print(f"  [!] Model missing — pull with: ollama pull {result['configured_model']}")


# ── Sync DB helpers ───────────────────────────────────────────────────────────

def _conn(db_sync_url: str = ""):
    from app.config import settings
    import psycopg2
    url = db_sync_url or settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    return psycopg2.connect(url)


def _count_ig_users(db_sync_url: str) -> int:
    import psycopg2
    conn = psycopg2.connect(db_sync_url)
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM discovered_users WHERE product_id = %s AND platform = 'instagram'",
        (PRODUCT_ID,),
    )
    count = cur.fetchone()[0]
    conn.close()
    return count


def _assert_product_exists(db_sync_url: str) -> None:
    import psycopg2
    conn = psycopg2.connect(db_sync_url)
    cur = conn.cursor()
    cur.execute("SELECT name FROM products WHERE id = %s", (PRODUCT_ID,))
    row = cur.fetchone()
    conn.close()
    if not row:
        print(f"  ERROR: product {PRODUCT_ID} not found in DB")
        sys.exit(1)
    print(f"  Product: {row[0]}")


def _reset_ocean_scores(db_sync_url: str) -> None:
    """
    Reset ocean_scored flag and delete existing UserOceanScore rows for
    Instagram users of this product so OCEAN re-scores fresh with Ollama.
    """
    import psycopg2
    conn = psycopg2.connect(db_sync_url)
    cur = conn.cursor()
    cur.execute(
        """
        DELETE FROM user_ocean_scores
        WHERE user_id IN (
            SELECT id FROM discovered_users
            WHERE product_id = %s AND platform = 'instagram'
        )
        """,
        (PRODUCT_ID,),
    )
    deleted = cur.rowcount
    cur.execute(
        """
        UPDATE discovered_users SET ocean_scored = false, matched = false
        WHERE product_id = %s AND platform = 'instagram'
        """,
        (PRODUCT_ID,),
    )
    updated = cur.rowcount
    conn.commit()
    conn.close()
    print(f"  Deleted {deleted} stale OCEAN scores, reset flags on {updated} users")


def _show_users(db_sync_url: str) -> None:
    import psycopg2
    conn = psycopg2.connect(db_sync_url)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT username, follower_count, content_collected, nlp_processed,
               ocean_scored, matched
        FROM discovered_users
        WHERE product_id = %s AND platform = 'instagram'
        ORDER BY created_at DESC
        """,
        (PRODUCT_ID,),
    )
    rows = cur.fetchall()
    conn.close()
    print(f"  Instagram users in DB: {len(rows)}")
    for r in rows:
        print(f"    @{r[0]:<35} followers={r[1]:>8} content={r[2]} nlp={r[3]} ocean={r[4]} matched={r[5]}")


def _show_nlp(db_sync_url: str) -> None:
    import psycopg2
    conn = psycopg2.connect(db_sync_url)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT du.username, unf.total_tokens, unf.vocabulary_richness,
               jsonb_array_length(COALESCE(unf.interest_tags, '[]'::jsonb))
        FROM user_nlp_features unf
        JOIN discovered_users du ON du.id = unf.user_id
        WHERE du.product_id = %s AND du.platform = 'instagram'
        ORDER BY du.username
        """,
        (PRODUCT_ID,),
    )
    rows = cur.fetchall()
    conn.close()
    print(f"  NLP records: {len(rows)}")
    for r in rows:
        print(f"    @{r[0]:<35} tokens={r[1]:5} vocab={r[2]:.3f} interest_tags={r[3]}")


def _show_ocean(db_sync_url: str) -> None:
    import psycopg2
    conn = psycopg2.connect(db_sync_url)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT du.username, uos.openness, uos.conscientiousness, uos.extraversion,
               uos.agreeableness, uos.neuroticism, uos.confidence, uos.scoring_method
        FROM user_ocean_scores uos
        JOIN discovered_users du ON du.id = uos.user_id
        WHERE du.product_id = %s AND du.platform = 'instagram'
        ORDER BY uos.confidence DESC
        """,
        (PRODUCT_ID,),
    )
    rows = cur.fetchall()
    conn.close()
    print(f"  OCEAN scores: {len(rows)}")
    for r in rows:
        marker = "✓ LLM" if r[7] == "llm" else "✗ heuristic"
        print(
            f"    @{r[0]:<35} O={r[1]:.1f} C={r[2]:.1f} E={r[3]:.1f} "
            f"A={r[4]:.1f} N={r[5]:.1f} conf={r[6]:.1f} [{marker}]"
        )


def _show_leads(db_sync_url: str) -> None:
    import psycopg2
    conn = psycopg2.connect(db_sync_url)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT DISTINCT ON (du.username) du.username, lm.final_score,
               lm.ocean_score, lm.embedding_score, lm.rank, lm.is_best_match
        FROM lead_matches lm
        JOIN discovered_users du ON du.id = lm.user_id
        WHERE lm.product_id = %s AND du.platform = 'instagram'
        ORDER BY du.username, lm.final_score DESC
        """,
        (PRODUCT_ID,),
    )
    rows = cur.fetchall()
    conn.close()
    print(f"  Lead matches (best per user): {len(rows)}")
    for r in rows:
        star = "BEST" if r[5] else "    "
        rank_str = f"rank={r[4]}" if r[4] is not None else "rank=NULL"
        print(
            f"    {star} @{r[0]:<35} final={r[1]:.1f} ocean={r[2]:.1f} "
            f"embed={r[3]:.1f} {rank_str}"
        )


def _show_summary(db_sync_url: str, ocean_via_llm: bool) -> None:
    import psycopg2
    conn = psycopg2.connect(db_sync_url)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
          COUNT(*),
          SUM(CASE WHEN content_collected THEN 1 ELSE 0 END),
          SUM(CASE WHEN nlp_processed     THEN 1 ELSE 0 END),
          SUM(CASE WHEN ocean_scored      THEN 1 ELSE 0 END),
          SUM(CASE WHEN matched           THEN 1 ELSE 0 END)
        FROM discovered_users
        WHERE product_id = %s AND platform = 'instagram'
        """,
        (PRODUCT_ID,),
    )
    r = cur.fetchone()
    users, content, nlp, ocean, matched = r[0], r[1] or 0, r[2] or 0, r[3] or 0, r[4] or 0

    cur.execute(
        """
        SELECT COUNT(*), COUNT(*) FILTER (WHERE scoring_method = 'llm'),
               COUNT(*) FILTER (WHERE scoring_method = 'heuristic')
        FROM user_ocean_scores uos
        JOIN discovered_users du ON du.id = uos.user_id
        WHERE du.product_id = %s AND du.platform = 'instagram'
        """,
        (PRODUCT_ID,),
    )
    oc = cur.fetchone()
    ocean_total, ocean_llm, ocean_heuristic = oc[0], oc[1] or 0, oc[2] or 0

    cur.execute(
        """
        SELECT COUNT(*),
               COUNT(*) FILTER (WHERE rank IS NOT NULL),
               COUNT(*) FILTER (WHERE is_best_match)
        FROM lead_matches lm
        JOIN discovered_users du ON du.id = lm.user_id
        WHERE lm.product_id = %s AND du.platform = 'instagram'
        """,
        (PRODUCT_ID,),
    )
    lm = cur.fetchone()
    leads_total, leads_ranked, leads_best = lm[0], lm[1] or 0, lm[2] or 0

    cur.execute(
        """
        SELECT COUNT(*) FROM user_content uc
        JOIN discovered_users du ON du.id = uc.user_id
        WHERE du.product_id = %s AND du.platform = 'instagram'
        """,
        (PRODUCT_ID,),
    )
    content_rows = cur.fetchone()[0]
    conn.close()

    checks = {
        "Discovery (instagram users)": users > 0,
        "Content collection":          content > 0,
        "NLP processing":              nlp > 0,
        "OCEAN via Ollama LLM":        ocean_llm > 0,
        "OCEAN heuristic-free":        ocean_heuristic == 0,
        "Lead matches created":        leads_total > 0,
        "Ranks assigned":              leads_ranked > 0,
        "is_best_match set":           leads_best > 0,
    }

    print(f"\n  {'Check':<35} {'Result':>8}  {'Detail'}")
    print(f"  {'-'*65}")
    for label, ok in checks.items():
        icon = "PASS" if ok else "FAIL"
        detail = ""
        if label == "Discovery (instagram users)":   detail = f"{users} users"
        elif label == "Content collection":           detail = f"{content_rows} rows"
        elif label == "NLP processing":               detail = f"{nlp}/{users} users"
        elif label == "OCEAN via Ollama LLM":         detail = f"{ocean_llm} LLM / {ocean_total} total"
        elif label == "OCEAN heuristic-free":         detail = f"{ocean_heuristic} heuristic rows"
        elif label == "Lead matches created":         detail = f"{leads_total} rows"
        elif label == "Ranks assigned":               detail = f"{leads_ranked} ranked rows"
        elif label == "is_best_match set":            detail = f"{leads_best} best-match rows"
        print(f"  {'✅' if ok else '❌'} {label:<33} {icon:>8}  {detail}")

    all_pass = all(checks.values())
    print()
    if all_pass:
        print("  STATUS: PASS — full pipeline complete with Ollama OCEAN scoring")
        print(f"\n  Dashboard: http://localhost:3000 → '{PRODUCT_NAME}' → Leads tab")
    else:
        print("  STATUS: PARTIAL — see failures above")


def _print_sql() -> None:
    print(f"\n{SEP}")
    print("SQL VERIFICATION QUERIES")
    print(SEP)
    print(f"""
-- 1. Instagram users + pipeline flags
SELECT username, follower_count, content_collected, nlp_processed,
       ocean_scored, matched, created_at::date
FROM discovered_users
WHERE product_id = '{PRODUCT_ID}' AND platform = 'instagram'
ORDER BY created_at DESC;

-- 2. NLP features
SELECT du.username, unf.total_tokens, unf.vocabulary_richness, unf.interest_tags
FROM user_nlp_features unf
JOIN discovered_users du ON du.id = unf.user_id
WHERE du.product_id = '{PRODUCT_ID}' AND du.platform = 'instagram';

-- 3. OCEAN scores — verify scoring_method = 'llm' (not 'heuristic')
SELECT du.username,
       ROUND(uos.openness::numeric,1)          AS O,
       ROUND(uos.conscientiousness::numeric,1) AS C,
       ROUND(uos.extraversion::numeric,1)      AS E,
       ROUND(uos.agreeableness::numeric,1)     AS A,
       ROUND(uos.neuroticism::numeric,1)       AS N,
       uos.confidence, uos.scoring_method
FROM user_ocean_scores uos
JOIN discovered_users du ON du.id = uos.user_id
WHERE du.product_id = '{PRODUCT_ID}' AND du.platform = 'instagram'
ORDER BY uos.confidence DESC;

-- 4. Lead matches with ranks — verify rank IS NOT NULL
SELECT du.username,
       ROUND(lm.final_score::numeric,1)  AS final,
       ROUND(lm.ocean_score::numeric,1)  AS ocean,
       ROUND(lm.embedding_score::numeric,1) AS embed,
       lm.rank, lm.is_best_match, lm.confidence
FROM lead_matches lm
JOIN discovered_users du ON du.id = lm.user_id
WHERE lm.product_id = '{PRODUCT_ID}' AND du.platform = 'instagram'
ORDER BY lm.rank NULLS LAST, lm.final_score DESC;

-- 5. Full pipeline summary
SELECT
  (SELECT COUNT(*) FROM discovered_users
   WHERE product_id = '{PRODUCT_ID}' AND platform = 'instagram') AS ig_users,
  (SELECT COUNT(*) FROM user_content uc
   JOIN discovered_users du ON du.id = uc.user_id
   WHERE du.product_id = '{PRODUCT_ID}' AND du.platform = 'instagram') AS content_rows,
  (SELECT COUNT(*) FROM user_nlp_features unf
   JOIN discovered_users du ON du.id = unf.user_id
   WHERE du.product_id = '{PRODUCT_ID}' AND du.platform = 'instagram') AS nlp_rows,
  (SELECT COUNT(*) FILTER (WHERE scoring_method = 'llm') FROM user_ocean_scores uos
   JOIN discovered_users du ON du.id = uos.user_id
   WHERE du.product_id = '{PRODUCT_ID}' AND du.platform = 'instagram') AS ocean_llm,
  (SELECT COUNT(*) FILTER (WHERE rank IS NOT NULL) FROM lead_matches lm
   JOIN discovered_users du ON du.id = lm.user_id
   WHERE lm.product_id = '{PRODUCT_ID}' AND du.platform = 'instagram') AS ranked_leads;
""")


def _print_api() -> None:
    print(f"\n{SEP}")
    print("API COMMANDS")
    print(SEP)
    print(f"""
# 1. Provider health
curl -s http://localhost:8000/api/v1/discovery/provider/status | python -m json.tool

# 2. Discovered users
curl -s "http://localhost:8000/api/v1/products/{PRODUCT_ID}/discovery/users?limit=20" \\
  -H "X-API-Key: <API_KEY>" | python -m json.tool

# 3. Lead matches (dashboard)
curl -s "http://localhost:8000/api/v1/products/{PRODUCT_ID}/leads" \\
  -H "X-API-Key: <API_KEY>" | python -m json.tool

# 4. Dashboard: http://localhost:3000 → {PRODUCT_NAME} → Leads tab
""")


if __name__ == "__main__":
    asyncio.run(main())
