import asyncio, sys
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from dotenv import load_dotenv; load_dotenv(".env")
PID = "eee20f77-d0d3-48bf-acb9-a4240d7918ef"

async def run():
    from app.database import AsyncSessionLocal
    from sqlalchemy import text
    async with AsyncSessionLocal() as db:
        t = lambda s,p={}: db.execute(text(s),p)

        r = await t("""
            SELECT
              COUNT(*) FILTER(WHERE content_collected) as content,
              COUNT(*) FILTER(WHERE nlp_processed)     as nlp,
              COUNT(*) FILTER(WHERE ocean_scored)      as ocean,
              COUNT(*) FILTER(WHERE matched)           as matched,
              COUNT(*) as total
            FROM discovered_users WHERE product_id=:p AND platform='youtube'
        """, {"p":PID})
        row = r.fetchone()
        print(f"Users: content={row[0]} nlp={row[1]} ocean={row[2]} matched={row[3]} total={row[4]}")

        r = await t("""
            SELECT COUNT(*) FROM user_nlp_features unf
            JOIN discovered_users du ON unf.user_id=du.id
            WHERE du.product_id=:p AND du.platform='youtube'
        """, {"p":PID})
        print(f"user_nlp_features rows: {r.scalar()}")

        r = await t("""
            SELECT COUNT(*) FROM user_embeddings ue
            JOIN discovered_users du ON ue.user_id=du.id
            WHERE du.product_id=:p AND du.platform='youtube'
        """, {"p":PID})
        print(f"user_embeddings rows:   {r.scalar()}")

        r = await t("""
            SELECT COUNT(*) FROM user_ocean_scores uos
            JOIN discovered_users du ON uos.user_id=du.id
            WHERE du.product_id=:p AND du.platform='youtube'
        """, {"p":PID})
        print(f"user_ocean_scores rows: {r.scalar()}")

        r = await t("""
            SELECT COUNT(*) FROM lead_matches lm
            WHERE lm.product_id=:p
        """, {"p":PID})
        print(f"lead_matches rows:      {r.scalar()}")

        r = await t("SELECT status, pipeline_step FROM products WHERE id=:p", {"p":PID})
        row = r.fetchone()
        print(f"Product: status={row[0]} step={row[1]}")

asyncio.run(run())
