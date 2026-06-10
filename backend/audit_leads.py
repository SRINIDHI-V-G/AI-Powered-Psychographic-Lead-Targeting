import asyncio, sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')

async def main():
    from app.database import AsyncSessionLocal
    from app.models.discovery import DiscoveredUser, UserContent
    from sqlalchemy import select
    from uuid import UUID

    PRODUCT_ID = UUID('9d396876-38e9-4aa9-99ab-6744d2761407')

    async with AsyncSessionLocal() as db:
        ur = await db.execute(
            select(DiscoveredUser)
            .where(DiscoveredUser.product_id == PRODUCT_ID)
            .order_by(DiscoveredUser.platform, DiscoveredUser.username)
        )
        users = ur.scalars().all()

        for u in users:
            bio = u.bio or ""
            loc = u.location or ""
            raw = u.raw_profile or {}
            disc_method = raw.get("discovery_method", "")
            disc_via = raw.get("hashtags_seen", raw.get("subreddit", ""))
            disc_via_str = str(disc_via)[:100] if disc_via else ""
            print(f"USERNAME: {u.username}")
            print(f"  platform={u.platform}  followers={u.follower_count}")
            print(f"  display={u.display_name}")
            print(f"  bio={repr(bio[:200])}")
            print(f"  location={repr(loc)}  confidence={u.location_confidence}")
            print(f"  source_provider={u.source_provider}  method:{disc_method}  via:{disc_via_str}")
            cr = await db.execute(
                select(UserContent).where(UserContent.user_id == u.id).limit(3)
            )
            contents = cr.scalars().all()
            for c in contents:
                snippet = (c.content_text or "")[:150].replace("\n", " ")
                print(f"  content[{c.content_type}]: {snippet}")
            print("---")

asyncio.run(main())
