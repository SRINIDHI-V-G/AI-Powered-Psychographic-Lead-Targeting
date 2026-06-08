"""
Run OCEAN scoring for all unscored YouTube users.
Processes insufficient-content users instantly via heuristic.
Calls Ollama for users with tokens >= 30 (may be slow).
"""
import asyncio, sys, logging
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
from dotenv import load_dotenv; load_dotenv(".env")

PID = "eee20f77-d0d3-48bf-acb9-a4240d7918ef"

async def main():
    from app.database import AsyncSessionLocal
    from sqlalchemy import text, select
    from app.models.discovery import DiscoveredUser
    from app.models.nlp import UserNlpFeatures
    from app.models.ocean import UserOceanScore
    from app.ml.ocean.heuristic_scorer import compute_heuristic_scores, compute_insufficient_content_scores
    from app.ml.ocean.ocean_prompter import MIN_TOKENS_FOR_LLM, MAX_CONTENT_SAMPLES, build_ocean_prompt, parse_ocean_response
    from app.models.discovery import UserContent
    from app.config import settings

    print(f"MIN_TOKENS_FOR_LLM = {MIN_TOKENS_FOR_LLM}")
    print(f"USE_MOCK_LLM = {settings.USE_MOCK_LLM}")

    async with AsyncSessionLocal() as db:
        # Get all unscored users for this product
        r = await db.execute(text("""
            SELECT du.id, du.username, unf.total_tokens, unf.empath_scores,
                   unf.vocabulary_richness, unf.avg_sentence_length, unf.interest_tags,
                   unf.keyword_frequency
            FROM discovered_users du
            JOIN user_nlp_features unf ON unf.user_id = du.id
            WHERE du.product_id = :p AND du.platform = 'youtube'
            ORDER BY unf.total_tokens DESC
        """), {"p": PID})
        users = r.fetchall()
        print(f"\nProcessing {len(users)} YouTube users:")

        scored = 0
        for row in users:
            uid, username, tokens, empath, vocab, avg_sent, tags, kw_freq = row
            print(f"  @{username[:35]}: tokens={tokens}", end=" ... ")

            # Delete any stale scores
            ex = await db.execute(
                select(UserOceanScore).where(UserOceanScore.user_id == uid)
            )
            stale = ex.scalar_one_or_none()
            if stale:
                await db.delete(stale)
                await db.flush()

            # Choose scoring method
            if tokens is None or tokens < MIN_TOKENS_FOR_LLM:
                scores = compute_insufficient_content_scores()
                scores["scoring_method"] = "insufficient_content"
            else:
                # Try Ollama, fall back to heuristic
                try:
                    # Load content samples
                    cr = await db.execute(text("""
                        SELECT content_text FROM user_content
                        WHERE user_id = :uid AND content_type IN ('post','comment')
                        ORDER BY engagement DESC LIMIT 5
                    """), {"uid": str(uid)})
                    content_samples = [r2[0] for r2 in cr.fetchall() if r2[0]]

                    prompt = build_ocean_prompt(
                        interest_tags=list(tags or []),
                        empath_scores=dict(empath or {}),
                        keyword_frequency=dict(kw_freq or {}),
                        vocabulary_richness=float(vocab or 0.5),
                        avg_sentence_length=float(avg_sent or 10.0),
                        total_tokens=tokens,
                        content_samples=content_samples,
                    )
                    from app.ml.llm_client import OllamaClient
                    client = OllamaClient()
                    raw = await client.generate(prompt=prompt, system="", temperature=0.2, num_predict=600)
                    parsed = parse_ocean_response(raw)
                    if parsed:
                        scores = parsed
                        scores["raw_llm_response"] = raw[:1000]
                    else:
                        scores = compute_heuristic_scores(
                            empath_scores=dict(empath or {}),
                            total_tokens=tokens,
                            vocabulary_richness=vocab,
                            avg_sentence_length=avg_sent,
                        )
                        scores["scoring_method"] = "heuristic"
                except Exception as exc:
                    scores = compute_heuristic_scores(
                        empath_scores=dict(empath or {}),
                        total_tokens=tokens,
                        vocabulary_richness=vocab,
                        avg_sentence_length=avg_sent,
                    )
                    scores["scoring_method"] = "heuristic"

            # Write score
            db.add(UserOceanScore(
                user_id=uid,
                openness=scores["openness"],
                conscientiousness=scores["conscientiousness"],
                extraversion=scores["extraversion"],
                agreeableness=scores["agreeableness"],
                neuroticism=scores["neuroticism"],
                confidence=scores["confidence"],
                scoring_method=scores["scoring_method"],
                reasoning=scores.get("reasoning", []),
                raw_llm_response=scores.get("raw_llm_response"),
            ))
            # Mark user as scored
            await db.execute(text(
                "UPDATE discovered_users SET ocean_scored=true WHERE id=:uid"
            ), {"uid": str(uid)})
            await db.commit()

            method = scores["scoring_method"]
            o = scores["openness"]
            print(f"O={o:.0f} method={method}")
            scored += 1

        print(f"\nScored {scored}/{len(users)} users.")

        # Final count
        r = await db.execute(text("""
            SELECT COUNT(*) FILTER(WHERE ocean_scored) as ocean, COUNT(*) as total
            FROM discovered_users WHERE product_id=:p AND platform='youtube'
        """), {"p": PID})
        row = r.fetchone()
        print(f"DB flags: ocean_scored={row[0]}/{row[1]}")

asyncio.run(main())
