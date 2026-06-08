"""
One-time fix: add embedding_vector column to user_embeddings as JSONB.

Migration 005 failed mid-transaction because pgvector PostgreSQL extension
is not installed (the ALTER TABLE ... TYPE vector(384) step failed, rolling back
the entire transaction, but Alembic still stamped the version).

This script adds the column as JSONB, which is what the NLP model uses as the
fallback type when pgvector is unavailable. The NLP service writes NULL to this
column when _HAS_PGVECTOR=False, and the matching engine falls back to the JSONB
'embedding' column for cosine similarity.
"""
import asyncio, sys
sys.path.insert(0, ".")
from dotenv import load_dotenv; load_dotenv(".env")

async def main():
    from app.database import AsyncSessionLocal
    from sqlalchemy import text
    async with AsyncSessionLocal() as db:
        # Verify column is missing
        r = await db.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='user_embeddings' AND column_name='embedding_vector'"
        ))
        if r.fetchone():
            print("embedding_vector column already exists — nothing to do.")
            return

        print("Adding embedding_vector column as JSONB (pgvector fallback)...")
        await db.execute(text(
            "ALTER TABLE user_embeddings ADD COLUMN embedding_vector JSONB"
        ))
        await db.commit()
        print("Column added successfully.")

        # Verify
        r2 = await db.execute(text(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name='user_embeddings' ORDER BY ordinal_position"
        ))
        print("user_embeddings columns now:")
        for row in r2.fetchall():
            print(f"  {row[0]}: {row[1]}")

asyncio.run(main())
