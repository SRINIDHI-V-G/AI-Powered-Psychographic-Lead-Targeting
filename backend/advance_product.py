import asyncio, sys
sys.path.insert(0, ".")
from dotenv import load_dotenv; load_dotenv(".env")
PID = "eee20f77-d0d3-48bf-acb9-a4240d7918ef"

async def main():
    from app.database import AsyncSessionLocal
    from sqlalchemy import text
    async with AsyncSessionLocal() as db:
        await db.execute(text(
            "UPDATE products SET status='ocean_scoring', pipeline_step=6, updated_at=NOW() WHERE id=:p"
        ), {"p": PID})
        await db.commit()
        r = await db.execute(text("SELECT status, pipeline_step FROM products WHERE id=:p"), {"p": PID})
        row = r.fetchone()
        print(f"Product: {row[0]} step={row[1]}")

asyncio.run(main())
