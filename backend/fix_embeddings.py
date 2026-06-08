"""
Clear embedding_vector column (JSONB) — it contains list data that pgvector
can't deserialize. Since the DB doesn't have the pgvector extension, this column
should be NULL. The matching engine falls back to the 'embedding' JSONB column.
"""
import asyncio, sys
sys.path.insert(0, ".")
from dotenv import load_dotenv; load_dotenv(".env")

async def main():
    from app.database import AsyncSessionLocal
    from sqlalchemy import text
    async with AsyncSessionLocal() as db:
        r = await db.execute(text(
            "UPDATE user_embeddings SET embedding_vector = NULL WHERE embedding_vector IS NOT NULL"
        ))
        await db.commit()
        print(f"Cleared embedding_vector for rows (rowcount={r.rowcount})")

        # Verify
        r2 = await db.execute(text(
            "SELECT COUNT(*) FROM user_embeddings WHERE embedding_vector IS NOT NULL"
        ))
        print(f"Remaining non-NULL embedding_vector: {r2.scalar()}")

asyncio.run(main())
