import asyncio, sys
sys.path.insert(0, ".")
from dotenv import load_dotenv; load_dotenv(".env")
PID = "eee20f77-d0d3-48bf-acb9-a4240d7918ef"

async def main():
    from app.database import AsyncSessionLocal
    from sqlalchemy import text
    async with AsyncSessionLocal() as db:
        # Schema check
        r = await db.execute(text(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name='user_ocean_scores' ORDER BY ordinal_position"
        ))
        print("user_ocean_scores columns:")
        for row in r.fetchall(): print(f"  {row[0]}: {row[1]}")

        # Check what ORM model expects
        from app.models.ocean import UserOceanScore
        orm_cols = [c.key for c in UserOceanScore.__table__.columns]
        print(f"\nORM model columns: {orm_cols}")

        # Try a direct ORM insert for one user
        r2 = await db.execute(text("""
            SELECT du.id FROM discovered_users du
            JOIN user_nlp_features unf ON unf.user_id = du.id
            WHERE du.product_id = :p AND du.platform = 'youtube'
            ORDER BY unf.total_tokens DESC LIMIT 1
        """), {"p": PID})
        user_id = r2.scalar()
        print(f"\nTesting ORM insert for user {user_id}...")

        # Direct ORM upsert
        from sqlalchemy import select
        existing = await db.execute(
            select(UserOceanScore).where(UserOceanScore.user_id == user_id)
        )
        stale = existing.scalar_one_or_none()
        if stale:
            print(f"  Deleting stale record...")
            await db.delete(stale)
            await db.flush()

        score = UserOceanScore(
            user_id=user_id,
            openness=75.0, conscientiousness=60.0, extraversion=50.0,
            agreeableness=65.0, neuroticism=35.0,
            confidence=70.0, scoring_method="heuristic",
            reasoning="Test insert", raw_llm_response=None,
        )
        db.add(score)
        await db.commit()
        print("  ORM insert succeeded!")

        r3 = await db.execute(text(
            "SELECT openness, conscientiousness, scoring_method FROM user_ocean_scores WHERE user_id=:uid"
        ), {"uid": str(user_id)})
        row = r3.fetchone()
        print(f"  Verified in DB: O={row[0]} C={row[1]} method={row[2]}")

asyncio.run(main())
