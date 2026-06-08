import asyncio, sys
sys.path.insert(0, ".")
from dotenv import load_dotenv; load_dotenv(".env")

async def main():
    from app.database import AsyncSessionLocal
    from sqlalchemy import text
    async with AsyncSessionLocal() as db:
        # pgvector extension?
        r = await db.execute(text("SELECT extname, extversion FROM pg_extension WHERE extname = 'vector'"))
        row = r.fetchone()
        print("pgvector extension:", row)

        # Actual columns in user_embeddings
        r2 = await db.execute(text(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name='user_embeddings' ORDER BY ordinal_position"
        ))
        print("user_embeddings columns:")
        for row in r2.fetchall():
            print(f"  {row[0]}: {row[1]}")

        # user_nlp_features columns
        r3 = await db.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='user_nlp_features' ORDER BY ordinal_position"
        ))
        print("user_nlp_features columns:", [r[0] for r in r3.fetchall()])

asyncio.run(main())
