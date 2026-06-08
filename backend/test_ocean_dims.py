import asyncio, sys
sys.path.insert(0, ".")
from dotenv import load_dotenv; load_dotenv(".env")
PID = "eee20f77-d0d3-48bf-acb9-a4240d7918ef"

async def main():
    from app.database import AsyncSessionLocal
    from app.crud.matching import get_ranked_leads
    from uuid import UUID
    async with AsyncSessionLocal() as db:
        result = await get_ranked_leads(db, UUID(PID), page=1, page_size=3)
        for lead in result["leads"]:
            print(f"username={lead['username']}")
            print(f"  openness={lead.get('openness')}  conscientiousness={lead.get('conscientiousness')}")
            print(f"  extraversion={lead.get('extraversion')}  agreeableness={lead.get('agreeableness')}")
            print(f"  neuroticism={lead.get('neuroticism')}  method={lead.get('ocean_scoring_method')}")
            print()

asyncio.run(main())
