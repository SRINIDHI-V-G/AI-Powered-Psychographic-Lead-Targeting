import asyncio, sys, json
sys.path.insert(0, ".")
from dotenv import load_dotenv; load_dotenv(".env")
PID = "eee20f77-d0d3-48bf-acb9-a4240d7918ef"
JID = "8814254b-8e1b-4eaa-8de2-f035fa4fac0c"

async def run():
    from app.database import AsyncSessionLocal
    from sqlalchemy import text
    async with AsyncSessionLocal() as db:
        t = lambda s,p={}: db.execute(text(s),p)

        print("=== TABLE: discovery_jobs ===")
        r = await t("SELECT id,status,provider_name,users_discovered,users_content_collected,started_at,completed_at FROM discovery_jobs WHERE id=:j",{"j":JID})
        row = r.fetchone()
        print(f"  id:                      {row[0]}")
        print(f"  status:                  {row[1]}")
        print(f"  provider_name:           {row[2]}")
        print(f"  users_discovered:        {row[3]}")
        print(f"  users_content_collected: {row[4]}")
        print(f"  started_at:              {row[5]}")
        print(f"  completed_at:            {row[6]}")
        dj_pass = row[1]=="completed" and row[2]=="youtube" and row[3]==15
        print(f"  RESULT: {'PASS' if dj_pass else 'FAIL'}")

        print("\n=== TABLE: discovered_users ===")
        r = await t("SELECT COUNT(*),platform,source_provider FROM discovered_users WHERE product_id=:p GROUP BY platform,source_provider",{"p":PID})
        rows = r.fetchall()
        yt_users = 0
        for row in rows:
            print(f"  platform={row[1]}  source_provider={row[2]}  count={row[0]}")
            if row[1]=="youtube": yt_users += row[0]
        print(f"  RESULT: {'PASS' if yt_users>0 else 'FAIL'} ({yt_users} youtube users)")

        print("\n=== SAMPLE: 5 YouTube leads (raw_profile — proves REAL data) ===")
        r = await t("""
            SELECT username, display_name, location, location_confidence, profile_url, raw_profile
            FROM discovered_users WHERE product_id=:p AND platform='youtube' LIMIT 5
        """,{"p":PID})
        for row in r.fetchall():
            rp = row[5] or {}
            print(f"  username:     {row[0]}")
            print(f"  display_name: {row[1]}")
            print(f"  location:     {row[2]} ({row[3]})")
            print(f"  profile_url:  {row[4]}")
            print(f"  video_id:     {rp.get('video_id','?')}")
            print(f"  keyword:      {rp.get('keyword','?')}")
            print(f"  comment:      {str(rp.get('discovery_comment',''))[:80]!r}")
            print()

        print("=== TABLE: user_content ===")
        r = await t("""
            SELECT COUNT(*), uc.content_type
            FROM user_content uc
            JOIN discovered_users du ON uc.user_id=du.id
            WHERE du.product_id=:p AND du.platform='youtube'
            GROUP BY uc.content_type
        """,{"p":PID})
        rows = r.fetchall(); total=sum(x[0] for x in rows)
        for row in rows:
            print(f"  content_type={row[1]}  count={row[0]}")
        print(f"  RESULT: {'PASS' if total>0 else 'FAIL'} ({total} content items)")

        print("\n=== SAMPLE: 3 content items (proves text stored) ===")
        r = await t("""
            SELECT du.username, uc.content_type, uc.content_text, uc.source_url, uc.engagement
            FROM user_content uc
            JOIN discovered_users du ON uc.user_id=du.id
            WHERE du.product_id=:p AND du.platform='youtube'
            ORDER BY uc.engagement DESC LIMIT 3
        """,{"p":PID})
        for row in r.fetchall():
            print(f"  @{row[0]} [{row[1]}] engagement={row[4]}")
            print(f"    text:  {row[2][:100]!r}")
            print(f"    url:   {row[3]}")
            print()

asyncio.run(run())
