"""Debug matching: run for first user only and print full traceback."""
import asyncio, sys, traceback, logging
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
from dotenv import load_dotenv; load_dotenv(".env")

PID = "eee20f77-d0d3-48bf-acb9-a4240d7918ef"

async def main():
    from app.database import AsyncSessionLocal
    from sqlalchemy import text, select
    from app.models.motivation import MotivationCategory, MotivationOceanProfile
    from app.models.discovery import DiscoveredUser
    from app.models.ocean import UserOceanScore
    from app.models.nlp import UserNlpFeatures, UserEmbedding
    from app.ml.matching.scorer import (
        normalize_motivation_ocean, compute_ocean_similarity,
        compute_embedding_similarity, compute_interest_score,
        compute_composite_score, compute_match_confidence, build_reasoning
    )
    from app.ml.nlp.embeddings import EmbeddingModel
    from uuid import UUID

    async with AsyncSessionLocal() as db:
        # Load one category and its profile
        cat_r = await db.execute(
            select(MotivationCategory)
            .where(MotivationCategory.product_id == UUID(PID), MotivationCategory.is_active == True)
            .limit(1)
        )
        cat = cat_r.scalar_one_or_none()
        if not cat:
            print("No motivation category found!"); return

        print(f"Category: {cat.name!r}")

        prof_r = await db.execute(
            select(MotivationOceanProfile)
            .where(MotivationOceanProfile.motivation_category_id == cat.id)
        )
        cat.ocean_profile = prof_r.scalar_one_or_none()
        if not cat.ocean_profile:
            print("No ocean profile found!"); return

        print(f"Profile: openness={cat.ocean_profile.openness} emotional_stability={cat.ocean_profile.emotional_stability}")
        print(f"Interest tags: {cat.ocean_profile.interest_tags}")
        print(f"Search keywords: {cat.ocean_profile.search_keywords}")

        # Try normalize_motivation_ocean
        try:
            motiv_ocean_100 = normalize_motivation_ocean(cat.ocean_profile)
            print(f"motiv_ocean_100: {motiv_ocean_100}")
        except Exception as e:
            print(f"normalize_motivation_ocean FAILED: {e}")
            traceback.print_exc(); return

        # Load one user
        user_r = await db.execute(
            select(DiscoveredUser)
            .where(DiscoveredUser.product_id == UUID(PID), DiscoveredUser.ocean_scored == True)
            .limit(1)
        )
        user = user_r.scalar_one_or_none()
        if not user:
            print("No scored user found!"); return
        print(f"\nUser: @{user.username}")

        # Load OCEAN score
        ocean_r = await db.execute(select(UserOceanScore).where(UserOceanScore.user_id == user.id))
        ocean = ocean_r.scalar_one_or_none()
        print(f"OCEAN: O={ocean.openness} C={ocean.conscientiousness} method={ocean.scoring_method}")

        # Load NLP features
        nlp_r = await db.execute(select(UserNlpFeatures).where(UserNlpFeatures.user_id == user.id))
        nlp = nlp_r.scalar_one_or_none()
        user_tags = list(nlp.interest_tags or []) if nlp else []
        user_keywords = dict(nlp.keyword_frequency or {}) if nlp else {}
        print(f"NLP: tags={user_tags[:3]} keywords={list(user_keywords.keys())[:3]}")

        # Load embedding
        emb_r = await db.execute(
            select(UserEmbedding)
            .where(UserEmbedding.user_id == user.id, UserEmbedding.embedding_type == "combined")
        )
        emb_row = emb_r.scalar_one_or_none()
        vec_source = getattr(emb_row, "embedding_vector", None) or (emb_row.embedding if emb_row else None)
        user_vec = list(vec_source) if vec_source else None
        print(f"Embedding: {'present' if user_vec else 'missing'} ({len(user_vec) if user_vec else 0} dims)")

        # Compute motivation embedding
        motiv_text = f"{cat.name}: {cat.description}"
        print(f"\nMotiv text: {motiv_text[:80]!r}")
        try:
            model = EmbeddingModel()
            motiv_vec = model.encode(motiv_text)
            print(f"Motiv embedding: {len(motiv_vec)} dims OK")
        except Exception as e:
            print(f"encode FAILED: {e}"); traceback.print_exc(); return

        # Compute scores step by step
        print("\nComputing scores...")
        try:
            ocean_s = compute_ocean_similarity(ocean, motiv_ocean_100)
            print(f"  ocean_s = {ocean_s}")
        except Exception as e:
            print(f"  compute_ocean_similarity FAILED: {e}"); traceback.print_exc(); return

        try:
            embed_s = compute_embedding_similarity(user_vec, motiv_vec)
            print(f"  embed_s = {embed_s}")
        except Exception as e:
            print(f"  compute_embedding_similarity FAILED: {e}"); traceback.print_exc(); return

        motiv_tags = list(cat.ocean_profile.interest_tags or [])
        motiv_kw = list(cat.ocean_profile.search_keywords or [])
        print(f"  motiv_tags type: {type(motiv_tags)}, first: {motiv_tags[0] if motiv_tags else 'empty'}")
        print(f"  user_tags type: {type(user_tags)}, first: {user_tags[0] if user_tags else 'empty'}")

        try:
            interest_s = compute_interest_score(user_tags, user_keywords, motiv_tags, motiv_kw)
            print(f"  interest_s = {interest_s}")
        except Exception as e:
            print(f"  compute_interest_score FAILED: {e}"); traceback.print_exc(); return

        try:
            final_s = compute_composite_score(ocean_s, embed_s, interest_s)
            print(f"  final_s = {final_s}")
        except Exception as e:
            print(f"  compute_composite_score FAILED: {e}"); traceback.print_exc(); return

        try:
            conf = compute_match_confidence(ocean.confidence, has_embedding=user_vec is not None, interest_tag_count=len(user_tags))
            print(f"  confidence = {conf}")
        except Exception as e:
            print(f"  compute_match_confidence FAILED: {e}"); traceback.print_exc(); return

        try:
            reasons = build_reasoning(ocean_s, embed_s, interest_s, user_tags, motiv_tags, cat.name)
            print(f"  reasoning = {reasons[:1]}")
        except Exception as e:
            print(f"  build_reasoning FAILED: {e}"); traceback.print_exc(); return

        print("\nAll steps passed!")

asyncio.run(main())
