import asyncio, sys, os
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from dotenv import load_dotenv; load_dotenv(".env")
PID = "eee20f77-d0d3-48bf-acb9-a4240d7918ef"
JID = "8814254b-8e1b-4eaa-8de2-f035fa4fac0c"

async def run():
    from app.database import AsyncSessionLocal
    from sqlalchemy import text
    async with AsyncSessionLocal() as db:
        t = lambda s,p={}: db.execute(text(s),p)

        # --- discovered_users summary ---
        r = await t("SELECT COUNT(*),platform FROM discovered_users WHERE product_id=:p GROUP BY platform",{"p":PID})
        for row in r.fetchall():
            print(f"discovered_users | platform={row[1]} | count={row[0]}")

        # --- 5 lead samples ---
        r = await t("""
            SELECT username, display_name, location, location_confidence,
                   raw_profile->>'video_id' as vid,
                   raw_profile->>'keyword' as kw,
                   LEFT(raw_profile->>'discovery_comment', 80) as comment
            FROM discovered_users WHERE product_id=:p AND platform='youtube' LIMIT 5
        """,{"p":PID})
        print("\n--- 5 YouTube leads (real data proof) ---")
        for i, row in enumerate(r.fetchall(), 1):
            comment_safe = (row[6] or "").encode("ascii","replace").decode()
            print(f"  Lead {i}: @{row[0]} | loc={row[2]}({row[3]}) | video={row[4]} | kw={row[5]!r}")
            print(f"           comment: {comment_safe!r}")

        # --- user_content ---
        r = await t("""
            SELECT COUNT(*), uc.content_type
            FROM user_content uc JOIN discovered_users du ON uc.user_id=du.id
            WHERE du.product_id=:p AND du.platform='youtube' GROUP BY uc.content_type
        """,{"p":PID})
        rows = r.fetchall(); total=sum(x[0] for x in rows)
        print(f"\nuser_content | total={total}")
        for row in rows:
            print(f"  content_type={row[1]} | count={row[0]}")

        # --- 3 content samples ---
        r = await t("""
            SELECT du.username, LEFT(uc.content_text,100), uc.source_url, uc.engagement
            FROM user_content uc JOIN discovered_users du ON uc.user_id=du.id
            WHERE du.product_id=:p AND du.platform='youtube'
            ORDER BY uc.engagement DESC LIMIT 3
        """,{"p":PID})
        print("\n--- 3 content items (real comments from YouTube) ---")
        for row in r.fetchall():
            safe = (row[1] or "").encode("ascii","replace").decode()
            print(f"  @{row[0]} | engagement={row[3]}")
            print(f"    text: {safe!r}")
            print(f"    url:  {row[2]}")

        # --- flags: nlp, ocean, matched ---
        r = await t("""
            SELECT
              COUNT(*) FILTER(WHERE content_collected) as has_content,
              COUNT(*) FILTER(WHERE nlp_processed)     as nlp_done,
              COUNT(*) FILTER(WHERE ocean_scored)      as ocean_done,
              COUNT(*) FILTER(WHERE matched)           as matched,
              COUNT(*)                                 as total
            FROM discovered_users WHERE product_id=:p AND platform='youtube'
        """,{"p":PID})
        row = r.fetchone()
        print(f"\nPipeline flags:")
        print(f"  content_collected={row[0]}  nlp_processed={row[1]}  ocean_scored={row[2]}  matched={row[3]}  total={row[4]}")

asyncio.run(run())
