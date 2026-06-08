import asyncio, sys, logging
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(name)s: %(message)s")
from dotenv import load_dotenv; load_dotenv(".env")
PID = "eee20f77-d0d3-48bf-acb9-a4240d7918ef"

async def run():
    from app.database import AsyncSessionLocal
    from sqlalchemy import text, select
    from app.models.discovery import DiscoveredUser
    from app.services.nlp_service import process_user_nlp

    async with AsyncSessionLocal() as db:
        # Get first YouTube user with content
        r = await db.execute(text("""
            SELECT du.id, du.username, du.bio
            FROM discovered_users du
            WHERE du.product_id=:p AND du.platform='youtube' AND du.content_collected=true
            LIMIT 1
        """), {"p": PID})
        row = r.fetchone()
        if not row:
            print("NO USER FOUND")
            return
        user_id, username, bio = row
        print(f"Testing NLP on user: @{username} (id={user_id})")
        print(f"  bio: {bio!r}")

        # Show their content
        r2 = await db.execute(text("""
            SELECT content_type, LEFT(content_text,120), engagement
            FROM user_content WHERE user_id=:uid
        """), {"uid": str(user_id)})
        for item in r2.fetchall():
            print(f"  content [{item[0]}] engagement={item[2]}: {item[1]!r}")

        # Now run NLP
        print("\nRunning process_user_nlp...")
        try:
            result = await process_user_nlp(db, user_id)
            print(f"Result: {result}")
            await db.commit()

            # Check what was written
            r3 = await db.execute(text("SELECT nlp_processed FROM discovered_users WHERE id=:id"), {"id": str(user_id)})
            print(f"nlp_processed flag: {r3.scalar()}")
            r4 = await db.execute(text("SELECT COUNT(*) FROM user_nlp_features WHERE user_id=:id"), {"id": str(user_id)})
            print(f"nlp_features rows:  {r4.scalar()}")
            r5 = await db.execute(text("SELECT COUNT(*) FROM user_embeddings WHERE user_id=:id"), {"id": str(user_id)})
            print(f"embeddings rows:    {r5.scalar()}")
        except Exception as exc:
            import traceback
            print(f"ERROR: {type(exc).__name__}: {exc}")
            traceback.print_exc()

asyncio.run(run())
