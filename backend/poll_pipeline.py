import asyncio, sys, time
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from dotenv import load_dotenv; load_dotenv(".env")
PID = "eee20f77-d0d3-48bf-acb9-a4240d7918ef"

async def poll():
    from app.database import AsyncSessionLocal
    from sqlalchemy import text
    start = time.time()
    while time.time() - start < 600:
        async with AsyncSessionLocal() as db:
            r = await db.execute(text("""
                SELECT
                  COUNT(*) FILTER(WHERE nlp_processed) as nlp,
                  COUNT(*) FILTER(WHERE ocean_scored)  as ocean,
                  COUNT(*) FILTER(WHERE matched)       as matched,
                  COUNT(*) as total
                FROM discovered_users WHERE product_id=:p AND platform='youtube'
            """), {"p": PID})
            row = r.fetchone()
            elapsed = int(time.time()-start)
            print(f"[{elapsed:3d}s] nlp={row[0]}/{row[3]}  ocean={row[1]}/{row[3]}  matched={row[2]}/{row[3]}")
            if row[2] > 0:
                print("Matching complete!")
                break
            if row[0] == 0 and elapsed > 60:
                # NLP may not have auto-triggered — check product status
                r2 = await db.execute(text("SELECT status, pipeline_step, error_message FROM products WHERE id=:p"), {"p": PID})
                p = r2.fetchone()
                print(f"  Product status: {p[0]} step={p[1]}")
                if p[2]:
                    print(f"  Error: {p[2][:200]}")
        await asyncio.sleep(15)

asyncio.run(poll())
