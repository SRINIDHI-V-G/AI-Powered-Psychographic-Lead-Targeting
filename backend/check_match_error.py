import asyncio, sys
sys.path.insert(0, ".")
from dotenv import load_dotenv; load_dotenv(".env")
PID = "eee20f77-d0d3-48bf-acb9-a4240d7918ef"

async def main():
    from app.database import AsyncSessionLocal
    from sqlalchemy import text
    async with AsyncSessionLocal() as db:
        r = await db.execute(text(
            "SELECT status, pipeline_step, error_message FROM products WHERE id=:p"
        ), {"p": PID})
        row = r.fetchone()
        print(f"Status: {row[0]}  Step: {row[1]}")
        if row[2]:
            print(f"Error:\n{row[2]}")

asyncio.run(main())
