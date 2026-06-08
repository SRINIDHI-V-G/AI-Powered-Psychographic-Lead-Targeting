"""Run OCEAN scoring for one user and show exactly what happens."""
import asyncio, sys, logging
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
from dotenv import load_dotenv; load_dotenv(".env")

PID = "eee20f77-d0d3-48bf-acb9-a4240d7918ef"

async def main():
    from app.database import AsyncSessionLocal
    from sqlalchemy import text, select
    from app.services.ocean_service import process_user_ocean

    async with AsyncSessionLocal() as db:
        # Get token counts to understand which path OCEAN will take
        r = await db.execute(text("""
            SELECT du.id, du.username, unf.total_tokens, unf.interest_tags
            FROM discovered_users du
            JOIN user_nlp_features unf ON unf.user_id = du.id
            WHERE du.product_id = :p AND du.platform = 'youtube'
            AND du.ocean_scored = false
            ORDER BY unf.total_tokens DESC
            LIMIT 5
        """), {"p": PID})
        rows = r.fetchall()
        print(f"Top 5 users by token count (MIN_TOKENS_FOR_LLM=30):")
        for row in rows:
            tags = (row[3] or [])[:3]
            print(f"  @{row[1]}: tokens={row[2]}  tags={tags}")

        if not rows:
            print("No unscored users found.")
            return

        # Process the user with the most tokens
        best_user_id = rows[0][0]
        best_username = rows[0][1]
        print(f"\nRunning OCEAN for @{best_username} (id={best_user_id})...")
        try:
            result = await process_user_ocean(db, best_user_id)
            await db.commit()
            print(f"process_user_ocean returned: {result}")

            # Verify score was written
            r2 = await db.execute(text("""
                SELECT openness, conscientiousness, extraversion, agreeableness,
                       neuroticism, confidence, scoring_method
                FROM user_ocean_scores WHERE user_id = :uid
            """), {"uid": str(best_user_id)})
            score = r2.fetchone()
            if score:
                print(f"OCEAN score written:")
                print(f"  O={score[0]:.0f} C={score[1]:.0f} E={score[2]:.0f} A={score[3]:.0f} N={score[4]:.0f}")
                print(f"  confidence={score[5]:.0f}  method={score[6]}")
            else:
                print("NO SCORE WRITTEN — something failed silently")
        except Exception as exc:
            import traceback
            print(f"ERROR: {type(exc).__name__}: {exc}")
            traceback.print_exc()

asyncio.run(main())
