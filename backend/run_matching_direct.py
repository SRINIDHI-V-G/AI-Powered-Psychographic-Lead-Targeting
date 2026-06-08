"""Run matching directly (not via background task) to get the full error trace."""
import asyncio, sys, traceback, logging
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
from dotenv import load_dotenv; load_dotenv(".env")

PID = "eee20f77-d0d3-48bf-acb9-a4240d7918ef"

async def main():
    from app.database import AsyncSessionLocal
    from app.services.matching_service import run_matching_for_product
    from uuid import UUID

    async with AsyncSessionLocal() as db:
        try:
            result = await run_matching_for_product(db, UUID(PID))
            print(f"SUCCESS: {result}")
        except Exception as exc:
            print(f"ERROR: {type(exc).__name__}: {exc}")
            traceback.print_exc()

asyncio.run(main())
