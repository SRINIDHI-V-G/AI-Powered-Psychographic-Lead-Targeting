import asyncio, sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')

NEW_JOB_ID = '8abf1253-99ea-4755-8083-b4af3620bfc6'
OLD_JOB_ID = 'f405529c-ff3b-419b-b61d-7749c9792a5d'

async def main():
    from app.database import AsyncSessionLocal
    from app.models.discovery import DiscoveredUser, UserContent
    from sqlalchemy import select
    from uuid import UUID

    async with AsyncSessionLocal() as db:
        for label, job_id in [("NEW (after fix)", NEW_JOB_ID), ("OLD (before fix)", OLD_JOB_ID)]:
            print(f"\n{'='*60}")
            print(f"  {label}  job={job_id[:8]}")
            print(f"{'='*60}\n")

            ur = await db.execute(
                select(DiscoveredUser)
                .where(DiscoveredUser.discovery_job_id == UUID(job_id))
                .order_by(DiscoveredUser.platform, DiscoveredUser.username)
            )
            users = ur.scalars().all()
            print(f"Total users: {len(users)}\n")

            for u in users:
                bio = u.bio or ""
                raw = u.raw_profile or {}
                disc_via = raw.get("hashtags_seen", raw.get("subreddit", ""))
                via_str = str(disc_via)[:120] if disc_via else ""
                print(f"[{u.platform.upper()}] @{u.username}")
                print(f"  display: {u.display_name}")
                print(f"  bio: {repr(bio[:150])}")
                print(f"  via: {via_str}")
                cr = await db.execute(
                    select(UserContent).where(UserContent.user_id == u.id).limit(2)
                )
                for c in cr.scalars().all():
                    print(f"  content: {(c.content_text or '')[:120].replace(chr(10),' ')}")
                print()

asyncio.run(main())
