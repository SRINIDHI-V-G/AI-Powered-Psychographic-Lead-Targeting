"""Full DB validation of the NLP/OCEAN/Matching pipeline for YouTube leads."""
import asyncio, sys
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from dotenv import load_dotenv; load_dotenv(".env")

PID = "eee20f77-d0d3-48bf-acb9-a4240d7918ef"

async def main():
    from app.database import AsyncSessionLocal
    from sqlalchemy import text
    async with AsyncSessionLocal() as db:
        t = lambda s, p={}: db.execute(text(s), p)

        print("=" * 60)
        print("  STAGE 5: user_nlp_features")
        print("=" * 60)
        r = await t("SELECT COUNT(*) FROM user_nlp_features unf JOIN discovered_users du ON unf.user_id=du.id WHERE du.product_id=:p AND du.platform='youtube'", {"p": PID})
        count = r.scalar()
        print(f"  nlp_features rows: {count}  RESULT: {'PASS' if count==15 else 'FAIL'}")

        r = await t("""
            SELECT du.username, unf.total_tokens, unf.interest_tags, unf.vocabulary_richness
            FROM user_nlp_features unf JOIN discovered_users du ON unf.user_id=du.id
            WHERE du.product_id=:p AND du.platform='youtube'
            ORDER BY unf.total_tokens DESC LIMIT 5
        """, {"p": PID})
        print("  Sample NLP features (top 5 by token count):")
        for row in r.fetchall():
            tags = (row[2] or [])[:3]
            vocab_str = f"{row[3]:.2f}" if row[3] else "N/A"
            print(f"    @{str(row[0])[:30]} tokens={row[1]} tags={tags} vocab={vocab_str}")

        print("\n" + "=" * 60)
        print("  STAGE 6: user_embeddings")
        print("=" * 60)
        r = await t("SELECT COUNT(*) FROM user_embeddings ue JOIN discovered_users du ON ue.user_id=du.id WHERE du.product_id=:p AND du.platform='youtube'", {"p": PID})
        count = r.scalar()
        print(f"  embedding rows: {count}  RESULT: {'PASS' if count==15 else 'FAIL'}")

        r = await t("SELECT COUNT(*) FROM user_embeddings ue JOIN discovered_users du ON ue.user_id=du.id WHERE du.product_id=:p AND jsonb_array_length(ue.embedding)=384", {"p": PID})
        dims_ok = r.scalar()
        print(f"  384-dim embeddings: {dims_ok}  RESULT: {'PASS' if dims_ok==15 else 'FAIL'}")

        print("\n" + "=" * 60)
        print("  STAGE 7: user_ocean_scores")
        print("=" * 60)
        r = await t("SELECT COUNT(*) FROM user_ocean_scores uos JOIN discovered_users du ON uos.user_id=du.id WHERE du.product_id=:p AND du.platform='youtube'", {"p": PID})
        count = r.scalar()
        print(f"  ocean_score rows: {count}  RESULT: {'PASS' if count==15 else 'FAIL'}")

        r = await t("""
            SELECT du.username, uos.openness, uos.conscientiousness, uos.extraversion,
                   uos.agreeableness, uos.neuroticism, uos.confidence, uos.scoring_method
            FROM user_ocean_scores uos JOIN discovered_users du ON uos.user_id=du.id
            WHERE du.product_id=:p AND du.platform='youtube'
            ORDER BY uos.confidence DESC LIMIT 5
        """, {"p": PID})
        print("  Sample OCEAN scores (top 5 by confidence):")
        for row in r.fetchall():
            print(f"    @{str(row[0])[:25]}: O={row[1]:.0f} C={row[2]:.0f} E={row[3]:.0f} A={row[4]:.0f} N={row[5]:.0f} conf={row[6]:.0f} [{row[7]}]")

        r = await t("""
            SELECT scoring_method, COUNT(*) FROM user_ocean_scores uos
            JOIN discovered_users du ON uos.user_id=du.id
            WHERE du.product_id=:p AND du.platform='youtube'
            GROUP BY scoring_method
        """, {"p": PID})
        print("  Scoring method breakdown:")
        for row in r.fetchall():
            print(f"    {row[0]}: {row[1]} users")

        print("\n" + "=" * 60)
        print("  STAGE 8: lead_matches")
        print("=" * 60)
        r = await t("SELECT COUNT(*) FROM lead_matches WHERE product_id=:p", {"p": PID})
        total_matches = r.scalar()
        print(f"  lead_match rows total: {total_matches}")

        r = await t("SELECT COUNT(*) FROM lead_matches WHERE product_id=:p AND is_best_match=true", {"p": PID})
        ranked_users = r.scalar()
        print(f"  ranked leads (is_best_match=true): {ranked_users}  RESULT: {'PASS' if ranked_users==15 else 'FAIL'}")

        r = await t("""
            SELECT COUNT(*) FILTER(WHERE final_score>=75) as hot,
                   COUNT(*) FILTER(WHERE final_score>=55 AND final_score<75) as warm,
                   COUNT(*) FILTER(WHERE final_score<55) as cold
            FROM lead_matches WHERE product_id=:p AND is_best_match=true
        """, {"p": PID})
        tiers = r.fetchone()
        print(f"  Lead tiers: hot={tiers[0]} warm={tiers[1]} cold={tiers[2]}")

        r = await t("""
            SELECT lm.rank, lm.final_score, lm.ocean_score, lm.embedding_score,
                   lm.interest_score, lm.confidence, du.username
            FROM lead_matches lm JOIN discovered_users du ON lm.user_id=du.id
            WHERE lm.product_id=:p AND lm.is_best_match=true
            ORDER BY lm.rank LIMIT 5
        """, {"p": PID})
        print("\n  Top 5 ranked YouTube leads:")
        for row in r.fetchall():
            print(f"    Rank #{row[0]} @{str(row[6])[:30]}: final={row[1]:.1f} ocean={row[2]:.1f} embed={row[3]:.1f} interest={row[4]:.1f} conf={row[5]:.1f}")

        # Verify matched flag
        r = await t("SELECT COUNT(*) FILTER(WHERE matched) FROM discovered_users WHERE product_id=:p AND platform='youtube'", {"p": PID})
        matched = r.scalar()
        print(f"\n  discovered_users.matched=True: {matched}/15  RESULT: {'PASS' if matched==15 else 'FAIL'}")

        # Product status
        r = await t("SELECT status, pipeline_step FROM products WHERE id=:p", {"p": PID})
        prod = r.fetchone()
        print(f"\n  Product: status={prod[0]}  step={prod[1]}")

asyncio.run(main())
