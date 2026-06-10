import asyncio, sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')

PRODUCT_ID = '9d396876-38e9-4aa9-99ab-6744d2761407'

async def main():
    from app.database import AsyncSessionLocal
    from app.crud.motivation import get_motivations_by_product
    from uuid import UUID

    async with AsyncSessionLocal() as db:
        cats = await get_motivations_by_product(db, UUID(PRODUCT_ID))
        print(f"Motivation categories: {len(cats)}\n")
        for cat in cats:
            print(f"Category: {cat.name}")
            if cat.ocean_profile:
                print(f"  search_keywords: {cat.ocean_profile.search_keywords}")
                print(f"  interest_tags:   {cat.ocean_profile.interest_tags}")
            else:
                print("  (no ocean_profile)")
            print()

asyncio.run(main())
