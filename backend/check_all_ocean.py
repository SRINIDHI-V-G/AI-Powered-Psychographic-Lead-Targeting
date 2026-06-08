import asyncio, sys
sys.path.insert(0, ".")
from dotenv import load_dotenv; load_dotenv(".env")
PID = "eee20f77-d0d3-48bf-acb9-a4240d7918ef"

async def main():
    from app.database import AsyncSessionLocal
    from sqlalchemy import text
    async with AsyncSessionLocal() as db:
        # All ocean scores for this product
        r = await db.execute(text("""
            SELECT du.username, uos.openness, uos.conscientiousness, uos.extraversion,
                   uos.agreeableness, uos.neuroticism, uos.confidence, uos.scoring_method,
                   du.ocean_scored
            FROM user_ocean_scores uos
            JOIN discovered_users du ON uos.user_id = du.id
            WHERE du.product_id = :p
            ORDER BY uos.openness DESC
        """), {"p": PID})
        rows = r.fetchall()
        print(f"user_ocean_scores rows for product: {len(rows)}")
        for row in rows:
            flag = "flag=True" if row[8] else "flag=False"
            print(f"  @{row[0][:30]}: O={row[1]:.0f} C={row[2]:.0f} E={row[3]:.0f} A={row[4]:.0f} N={row[5]:.0f} conf={row[6]:.0f} method={row[7]} {flag}")

        # pipeline flags
        r2 = await db.execute(text("""
            SELECT COUNT(*) FILTER(WHERE nlp_processed) as nlp,
                   COUNT(*) FILTER(WHERE ocean_scored) as ocean,
                   COUNT(*) FILTER(WHERE matched) as matched,
                   COUNT(*) as total
            FROM discovered_users WHERE product_id = :p AND platform = 'youtube'
        """), {"p": PID})
        row = r2.fetchone()
        print(f"\nFlags: nlp={row[0]} ocean={row[1]} matched={row[2]} total={row[3]}")

        # product status
        r3 = await db.execute(text("SELECT status, pipeline_step FROM products WHERE id=:p"), {"p": PID})
        prod = r3.fetchone()
        print(f"Product: {prod[0]} step={prod[1]}")

asyncio.run(main())
