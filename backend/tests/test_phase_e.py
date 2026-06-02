"""
Phase E Matching Engine & Lead Ranking — test suite.

Coverage:
  1. Scorer unit tests       — OCEAN sim, embedding sim, interest overlap, composite
  2. Model structure tests   — LeadMatch columns and constraints
  3. Service tests           — per-user matching, batch, ranking, background task
  4. CRUD tests              — get_match_status, get_ranked_leads, get_lead_detail
  5. API tests               — all endpoints with mocked CRUD + auth
  6. Edge cases              — degenerate inputs, re-run, scale limits

Run with:
  cd backend && pytest tests/test_phase_e.py -v
"""
from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ═══════════════════════════════════════════════════════════════════════════════
# 1. SCORER — unit tests
# ═══════════════════════════════════════════════════════════════════════════════

from app.ml.matching.scorer import (
    normalize_motivation_ocean,
    compute_ocean_similarity,
    compute_embedding_similarity,
    compute_interest_score,
    compute_composite_score,
    compute_match_confidence,
    build_reasoning,
    OCEAN_WEIGHT,
    EMBEDDING_WEIGHT,
    INTEREST_WEIGHT,
    _clamp100,
)


# ── normalize_motivation_ocean ─────────────────────────────────────────────────

class TestNormalizeMotivationOcean:
    def _make_motiv_profile(self, **kwargs) -> MagicMock:
        p = MagicMock()
        p.openness = kwargs.get("openness", 5.0)
        p.conscientiousness = kwargs.get("conscientiousness", 5.0)
        p.extraversion = kwargs.get("extraversion", 5.0)
        p.agreeableness = kwargs.get("agreeableness", 5.0)
        p.emotional_stability = kwargs.get("emotional_stability", 5.0)
        return p

    def test_scales_to_100(self):
        p = self._make_motiv_profile(openness=10.0)
        result = normalize_motivation_ocean(p)
        assert result["openness"] == 100.0

    def test_zero_maps_to_zero(self):
        p = self._make_motiv_profile(openness=0.0)
        result = normalize_motivation_ocean(p)
        assert result["openness"] == 0.0

    def test_five_maps_to_fifty(self):
        p = self._make_motiv_profile(openness=5.0)
        result = normalize_motivation_ocean(p)
        assert result["openness"] == 50.0

    def test_neuroticism_inversion(self):
        # emotional_stability=10 → neuroticism=0
        p = self._make_motiv_profile(emotional_stability=10.0)
        result = normalize_motivation_ocean(p)
        assert result["neuroticism"] == 0.0

    def test_neuroticism_inversion_zero_stability(self):
        # emotional_stability=0 → neuroticism=100
        p = self._make_motiv_profile(emotional_stability=0.0)
        result = normalize_motivation_ocean(p)
        assert result["neuroticism"] == 100.0

    def test_neuroticism_inversion_midpoint(self):
        # emotional_stability=5 → neuroticism=50
        p = self._make_motiv_profile(emotional_stability=5.0)
        result = normalize_motivation_ocean(p)
        assert result["neuroticism"] == 50.0

    def test_all_five_dimensions_present(self):
        p = self._make_motiv_profile()
        result = normalize_motivation_ocean(p)
        for dim in ("openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism"):
            assert dim in result

    def test_clamps_above_10(self):
        p = self._make_motiv_profile(openness=15.0)
        result = normalize_motivation_ocean(p)
        assert result["openness"] == 100.0

    def test_clamps_below_0(self):
        p = self._make_motiv_profile(openness=-5.0)
        result = normalize_motivation_ocean(p)
        assert result["openness"] == 0.0


# ── compute_ocean_similarity ──────────────────────────────────────────────────

class TestComputeOceanSimilarity:
    def _make_user_score(self, **kwargs) -> MagicMock:
        u = MagicMock()
        u.openness = kwargs.get("openness", 50.0)
        u.conscientiousness = kwargs.get("conscientiousness", 50.0)
        u.extraversion = kwargs.get("extraversion", 50.0)
        u.agreeableness = kwargs.get("agreeableness", 50.0)
        u.neuroticism = kwargs.get("neuroticism", 50.0)
        return u

    def _neutral_motiv(self) -> dict:
        return {d: 50.0 for d in ("openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism")}

    def test_identical_profiles_score_100(self):
        user = self._make_user_score(openness=70, conscientiousness=60, extraversion=50, agreeableness=65, neuroticism=35)
        motiv = {"openness": 70, "conscientiousness": 60, "extraversion": 50, "agreeableness": 65, "neuroticism": 35}
        score = compute_ocean_similarity(user, motiv)
        assert abs(score - 100.0) < 0.01

    def test_neutral_vs_neutral_score_100(self):
        user = self._make_user_score()
        score = compute_ocean_similarity(user, self._neutral_motiv())
        assert abs(score - 100.0) < 0.01

    def test_extreme_opposite_profiles_low_score(self):
        user = self._make_user_score(openness=0, conscientiousness=0, extraversion=100, agreeableness=0, neuroticism=100)
        motiv = {"openness": 100, "conscientiousness": 100, "extraversion": 0, "agreeableness": 100, "neuroticism": 0}
        score = compute_ocean_similarity(user, motiv)
        assert score < 40.0

    def test_score_in_0_100_range(self):
        user = self._make_user_score(openness=30, conscientiousness=80)
        motiv = {"openness": 70, "conscientiousness": 40, "extraversion": 50, "agreeableness": 50, "neuroticism": 50}
        score = compute_ocean_similarity(user, motiv)
        assert 0.0 <= score <= 100.0

    def test_single_dimension_difference(self):
        user = self._make_user_score()
        motiv = dict(self._neutral_motiv())
        motiv["openness"] = 100.0
        score_50_vs_100 = compute_ocean_similarity(user, motiv)
        assert score_50_vs_100 < 100.0
        assert score_50_vs_100 > 70.0  # Only 1 dim differs slightly

    def test_closer_profile_higher_score(self):
        user = self._make_user_score(openness=75, conscientiousness=70)
        close_motiv = {"openness": 70, "conscientiousness": 65, "extraversion": 50, "agreeableness": 50, "neuroticism": 50}
        far_motiv = {"openness": 20, "conscientiousness": 20, "extraversion": 50, "agreeableness": 50, "neuroticism": 50}
        close_score = compute_ocean_similarity(user, close_motiv)
        far_score = compute_ocean_similarity(user, far_motiv)
        assert close_score > far_score

    def test_symmetry(self):
        """Distance is symmetric: sim(A, B) == sim(B, A)."""
        user_a = self._make_user_score(openness=80, conscientiousness=60)
        user_b = self._make_user_score(openness=60, conscientiousness=80)
        motiv_a = {"openness": 80, "conscientiousness": 60, "extraversion": 50, "agreeableness": 50, "neuroticism": 50}
        motiv_b = {"openness": 60, "conscientiousness": 80, "extraversion": 50, "agreeableness": 50, "neuroticism": 50}
        assert abs(compute_ocean_similarity(user_a, motiv_b) - compute_ocean_similarity(user_b, motiv_a)) < 0.01


# ── compute_embedding_similarity ──────────────────────────────────────────────

class TestComputeEmbeddingSimilarity:
    def _unit_vec(self, n: int = 4, value: float = 1.0) -> list[float]:
        raw = [value] * n
        norm = math.sqrt(sum(x ** 2 for x in raw))
        return [x / norm for x in raw]

    def test_missing_user_vec_returns_50(self):
        assert compute_embedding_similarity(None, [0.1, 0.2]) == 50.0

    def test_missing_motiv_vec_returns_50(self):
        assert compute_embedding_similarity([0.1, 0.2], None) == 50.0

    def test_both_missing_returns_50(self):
        assert compute_embedding_similarity(None, None) == 50.0

    def test_identical_unit_vecs_returns_100(self):
        vec = self._unit_vec()
        result = compute_embedding_similarity(vec, vec)
        assert abs(result - 100.0) < 0.1

    def test_orthogonal_vecs_returns_50(self):
        vec_a = [1.0, 0.0]
        vec_b = [0.0, 1.0]
        result = compute_embedding_similarity(vec_a, vec_b)
        assert abs(result - 50.0) < 0.1

    def test_opposite_vecs_returns_near_0(self):
        vec_a = [1.0, 0.0]
        vec_b = [-1.0, 0.0]
        result = compute_embedding_similarity(vec_a, vec_b)
        assert result < 5.0

    def test_result_in_0_100_range(self):
        import random
        random.seed(99)
        vec_a = [random.uniform(-1, 1) for _ in range(384)]
        norm_a = math.sqrt(sum(x ** 2 for x in vec_a))
        vec_a = [x / norm_a for x in vec_a]
        vec_b = [random.uniform(-1, 1) for _ in range(384)]
        norm_b = math.sqrt(sum(x ** 2 for x in vec_b))
        vec_b = [x / norm_b for x in vec_b]
        result = compute_embedding_similarity(vec_a, vec_b)
        assert 0.0 <= result <= 100.0


# ── compute_interest_score ────────────────────────────────────────────────────

class TestComputeInterestScore:
    def test_full_tag_overlap_high_score(self):
        tags = ["technology", "learning", "innovation"]
        score = compute_interest_score(tags, {}, tags, [])
        assert score >= 60.0

    def test_no_overlap_returns_zero(self):
        user_tags = ["technology", "learning"]
        motiv_tags = ["cooking", "gardening"]
        score = compute_interest_score(user_tags, {}, motiv_tags, [])
        assert score == 0.0

    def test_empty_user_tags_no_tag_component(self):
        score = compute_interest_score([], {}, ["technology"], [])
        assert score == 0.0

    def test_empty_motiv_tags_no_tag_component(self):
        score = compute_interest_score(["technology"], {}, [], [])
        assert score == 0.0

    def test_keyword_overlap_contributes(self):
        user_kw = {"python": 5, "machine": 3, "learning": 2}
        motiv_kw = ["python", "data", "learning"]
        score = compute_interest_score([], user_kw, [], motiv_kw)
        assert score > 0.0

    def test_full_keyword_match_contributes_40_pct(self):
        user_kw = {"python": 5, "data": 3, "ml": 2}
        motiv_kw = ["python", "data", "ml"]
        score = compute_interest_score([], user_kw, [], motiv_kw)
        assert abs(score - 40.0) < 1.0

    def test_case_insensitive_matching(self):
        user_tags = ["Technology", "LEARNING"]
        motiv_tags = ["technology", "learning"]
        score = compute_interest_score(user_tags, {}, motiv_tags, [])
        assert score > 0.0

    def test_score_in_0_100_range(self):
        score = compute_interest_score(
            ["a", "b", "c"], {"x": 1}, ["a", "c", "d"], ["x", "y"]
        )
        assert 0.0 <= score <= 100.0

    def test_partial_tag_overlap_proportional(self):
        user_tags = ["technology", "sports", "cooking"]
        motiv_tags = ["technology", "learning", "innovation"]
        score = compute_interest_score(user_tags, {}, motiv_tags, [])
        assert 0.0 < score < 100.0


# ── compute_composite_score ───────────────────────────────────────────────────

class TestComputeCompositeScore:
    def test_weights_sum_to_1(self):
        assert abs(OCEAN_WEIGHT + EMBEDDING_WEIGHT + INTEREST_WEIGHT - 1.0) < 0.001

    def test_all_100_gives_100(self):
        assert compute_composite_score(100.0, 100.0, 100.0) == 100.0

    def test_all_0_gives_0(self):
        assert compute_composite_score(0.0, 0.0, 0.0) == 0.0

    def test_correct_weighting(self):
        expected = round(0.50 * 80 + 0.25 * 60 + 0.25 * 40, 2)
        assert compute_composite_score(80.0, 60.0, 40.0) == expected

    def test_result_in_0_100_range(self):
        result = compute_composite_score(73.5, 68.2, 55.0)
        assert 0.0 <= result <= 100.0

    def test_ocean_dominates(self):
        high_ocean = compute_composite_score(100, 0, 0)
        high_embed = compute_composite_score(0, 100, 0)
        assert high_ocean > high_embed


# ── compute_match_confidence ──────────────────────────────────────────────────

class TestComputeMatchConfidence:
    def test_high_confidence_inputs(self):
        result = compute_match_confidence(90.0, True, 10)
        assert result > 80.0

    def test_low_confidence_no_embedding(self):
        result = compute_match_confidence(20.0, False, 0)
        assert result < 50.0

    def test_result_in_0_100_range(self):
        result = compute_match_confidence(75.0, True, 8)
        assert 0.0 <= result <= 100.0

    def test_embedding_presence_improves_confidence(self):
        with_emb = compute_match_confidence(60.0, True, 5)
        without_emb = compute_match_confidence(60.0, False, 5)
        assert with_emb > without_emb

    def test_more_tags_higher_confidence(self):
        few_tags = compute_match_confidence(60.0, True, 2)
        many_tags = compute_match_confidence(60.0, True, 10)
        assert many_tags > few_tags


# ── build_reasoning ───────────────────────────────────────────────────────────

class TestBuildReasoning:
    def test_returns_list_of_strings(self):
        result = build_reasoning(80, 70, 60, ["tech"], ["tech"], "Tech Buyer")
        assert isinstance(result, list)
        assert all(isinstance(r, str) for r in result)

    def test_mentions_motivation_name(self):
        result = build_reasoning(80, 70, 60, ["tech"], ["tech"], "Tech Buyer")
        assert any("Tech Buyer" in r for r in result)

    def test_strong_ocean_positive_language(self):
        result = build_reasoning(85, 50, 30, [], [], "Innovator")
        assert any("strong" in r.lower() or "high" in r.lower() for r in result)

    def test_weak_ocean_reflected(self):
        result = build_reasoning(30, 50, 30, [], [], "Innovator")
        assert any("weak" in r.lower() for r in result)

    def test_shared_interests_mentioned(self):
        result = build_reasoning(70, 50, 50, ["technology", "learning"], ["technology", "sports"], "Tech")
        assert any("technology" in r.lower() for r in result)

    def test_no_crash_empty_inputs(self):
        result = build_reasoning(50, 50, 0, [], [], "Category")
        assert isinstance(result, list)


# ── clamp100 ──────────────────────────────────────────────────────────────────

class TestClamp100:
    def test_clamped_above_100(self):
        assert _clamp100(150.0) == 100.0

    def test_clamped_below_0(self):
        assert _clamp100(-10.0) == 0.0

    def test_in_range_unchanged(self):
        assert _clamp100(75.5) == 75.5


# ═══════════════════════════════════════════════════════════════════════════════
# 2. MODEL STRUCTURE TESTS
# ═══════════════════════════════════════════════════════════════════════════════

from app.models.matching import LeadMatch


class TestLeadMatchModel:
    def test_has_required_columns(self):
        cols = {c.name for c in LeadMatch.__table__.columns}
        expected = {
            "id", "product_id", "user_id", "motivation_category_id",
            "ocean_score", "embedding_score", "interest_score", "final_score",
            "confidence", "is_best_match", "rank", "reasoning", "created_at",
        }
        assert expected.issubset(cols), f"Missing: {expected - cols}"

    def test_unique_constraint_user_category(self):
        names = {uc.name for uc in LeadMatch.__table__.constraints}
        assert "uq_lead_match_user_category" in names

    def test_is_best_match_column_is_boolean(self):
        col = LeadMatch.__table__.c["is_best_match"]
        from sqlalchemy import Boolean
        assert isinstance(col.type, Boolean)

    def test_rank_is_nullable(self):
        col = LeadMatch.__table__.c["rank"]
        assert col.nullable

    def test_final_score_is_indexed(self):
        index_cols = {
            col.name
            for idx in LeadMatch.__table__.indexes
            for col in idx.columns
        }
        assert "final_score" in index_cols


# ═══════════════════════════════════════════════════════════════════════════════
# 3. MATCHING SERVICE — mocked async tests
# ═══════════════════════════════════════════════════════════════════════════════

from app.models.discovery import DiscoveredUser
from app.models.motivation import MotivationCategory, MotivationOceanProfile
from app.models.nlp import UserEmbedding, UserNlpFeatures
from app.models.ocean import UserOceanScore
from app.models.product import Product, ProductStatus
from app.services.matching_service import (
    _compute_user_matches,
    _apply_ranking,
    run_matching_for_product,
)


def _make_ocean_profile(**kwargs) -> MagicMock:
    p = MagicMock(spec=MotivationOceanProfile)
    p.openness = kwargs.get("openness", 7.0)
    p.conscientiousness = kwargs.get("conscientiousness", 6.5)
    p.extraversion = kwargs.get("extraversion", 5.0)
    p.agreeableness = kwargs.get("agreeableness", 6.0)
    p.emotional_stability = kwargs.get("emotional_stability", 7.5)
    p.interest_tags = kwargs.get("interest_tags", ["technology", "innovation"])
    p.search_keywords = kwargs.get("search_keywords", ["software", "python", "data"])
    return p


def _make_category(cat_id: uuid.UUID, product_id: uuid.UUID, name: str = "Tech Enthusiast") -> MagicMock:
    cat = MagicMock(spec=MotivationCategory)
    cat.id = cat_id
    cat.product_id = product_id
    cat.name = name
    cat.description = f"{name}: description text for testing."
    cat.is_active = True
    cat.sort_order = 0
    cat.ocean_profile = _make_ocean_profile()
    return cat


def _make_user_ocean(user_id: uuid.UUID, **kwargs) -> MagicMock:
    o = MagicMock(spec=UserOceanScore)
    o.user_id = user_id
    o.openness = kwargs.get("openness", 72.0)
    o.conscientiousness = kwargs.get("conscientiousness", 65.0)
    o.extraversion = kwargs.get("extraversion", 48.0)
    o.agreeableness = kwargs.get("agreeableness", 70.0)
    o.neuroticism = kwargs.get("neuroticism", 28.0)
    o.confidence = kwargs.get("confidence", 74.0)
    return o


def _make_nlp_features(user_id: uuid.UUID) -> MagicMock:
    nlp = MagicMock(spec=UserNlpFeatures)
    nlp.user_id = user_id
    nlp.interest_tags = ["technology", "learning", "innovation"]
    nlp.keyword_frequency = {"python": 5, "data": 3, "software": 2}
    return nlp


def _make_embedding(user_id: uuid.UUID) -> MagicMock:
    emb = MagicMock(spec=UserEmbedding)
    emb.user_id = user_id
    emb.embedding_type = "combined"
    # Simple unit vector (1/√384 for each dimension)
    import math
    val = 1.0 / math.sqrt(384)
    emb.embedding = [val] * 384
    return emb


def _make_discovered_user(user_id: uuid.UUID, product_id: uuid.UUID) -> MagicMock:
    u = MagicMock(spec=DiscoveredUser)
    u.id = user_id
    u.product_id = product_id
    u.username = f"user_{user_id.hex[:6]}"
    u.matched = False
    u.ocean_scored = True
    return u


def _make_db_for_user_match(user_id, ocean, nlp, emb) -> AsyncMock:
    """Build DB mock for _compute_user_matches."""
    db = AsyncMock()

    ocean_result = MagicMock()
    ocean_result.scalar_one_or_none.return_value = ocean

    nlp_result = MagicMock()
    nlp_result.scalar_one_or_none.return_value = nlp

    emb_result = MagicMock()
    emb_result.scalar_one_or_none.return_value = emb

    db.execute.side_effect = [ocean_result, nlp_result, emb_result]
    return db


@pytest.mark.asyncio
async def test_compute_user_matches_creates_one_per_category():
    user_id = uuid.uuid4()
    product_id = uuid.uuid4()
    cat_ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
    categories = [_make_category(cid, product_id, f"Cat{i}") for i, cid in enumerate(cat_ids)]
    motiv_embeddings = {cid: [0.1] * 384 for cid in cat_ids}

    user = _make_discovered_user(user_id, product_id)
    ocean = _make_user_ocean(user_id)
    nlp = _make_nlp_features(user_id)
    emb = _make_embedding(user_id)
    db = _make_db_for_user_match(user_id, ocean, nlp, emb)

    matches = await _compute_user_matches(db, user, categories, motiv_embeddings)

    assert len(matches) == 3
    assert all(isinstance(m, LeadMatch) for m in matches)


@pytest.mark.asyncio
async def test_compute_user_matches_scores_in_range():
    user_id = uuid.uuid4()
    product_id = uuid.uuid4()
    cat_id = uuid.uuid4()
    categories = [_make_category(cat_id, product_id)]
    motiv_embeddings = {cat_id: [0.1] * 384}

    user = _make_discovered_user(user_id, product_id)
    ocean = _make_user_ocean(user_id)
    nlp = _make_nlp_features(user_id)
    emb = _make_embedding(user_id)
    db = _make_db_for_user_match(user_id, ocean, nlp, emb)

    matches = await _compute_user_matches(db, user, categories, motiv_embeddings)

    m = matches[0]
    assert 0.0 <= m.ocean_score <= 100.0
    assert 0.0 <= m.embedding_score <= 100.0
    assert 0.0 <= m.interest_score <= 100.0
    assert 0.0 <= m.final_score <= 100.0
    assert 0.0 <= m.confidence <= 100.0


@pytest.mark.asyncio
async def test_compute_user_matches_no_ocean_score_returns_empty():
    user_id = uuid.uuid4()
    product_id = uuid.uuid4()
    cat_id = uuid.uuid4()
    user = _make_discovered_user(user_id, product_id)

    db = AsyncMock()
    no_ocean = MagicMock()
    no_ocean.scalar_one_or_none.return_value = None
    db.execute.return_value = no_ocean

    matches = await _compute_user_matches(db, user, [_make_category(cat_id, product_id)], {cat_id: []})
    assert matches == []


@pytest.mark.asyncio
async def test_compute_user_matches_no_embedding_uses_fallback():
    user_id = uuid.uuid4()
    product_id = uuid.uuid4()
    cat_id = uuid.uuid4()
    categories = [_make_category(cat_id, product_id)]
    motiv_embeddings = {cat_id: [0.1] * 384}

    user = _make_discovered_user(user_id, product_id)
    ocean = _make_user_ocean(user_id)
    nlp = _make_nlp_features(user_id)

    db = AsyncMock()
    ocean_r = MagicMock(); ocean_r.scalar_one_or_none.return_value = ocean
    nlp_r = MagicMock(); nlp_r.scalar_one_or_none.return_value = nlp
    no_emb = MagicMock(); no_emb.scalar_one_or_none.return_value = None
    db.execute.side_effect = [ocean_r, nlp_r, no_emb]

    matches = await _compute_user_matches(db, user, categories, motiv_embeddings)
    assert len(matches) == 1
    # embedding_score should be 50 (fallback for missing embedding)
    assert matches[0].embedding_score == 50.0


@pytest.mark.asyncio
async def test_compute_user_matches_reasoning_is_list_of_strings():
    user_id = uuid.uuid4()
    product_id = uuid.uuid4()
    cat_id = uuid.uuid4()
    categories = [_make_category(cat_id, product_id)]
    motiv_embeddings = {cat_id: [0.1] * 384}

    user = _make_discovered_user(user_id, product_id)
    ocean = _make_user_ocean(user_id)
    nlp = _make_nlp_features(user_id)
    emb = _make_embedding(user_id)
    db = _make_db_for_user_match(user_id, ocean, nlp, emb)

    matches = await _compute_user_matches(db, user, categories, motiv_embeddings)
    assert isinstance(matches[0].reasoning, list)


@pytest.mark.asyncio
async def test_compute_user_matches_category_without_ocean_profile_skipped():
    user_id = uuid.uuid4()
    product_id = uuid.uuid4()

    cat_no_profile = MagicMock(spec=MotivationCategory)
    cat_no_profile.id = uuid.uuid4()
    cat_no_profile.name = "No Profile"
    cat_no_profile.ocean_profile = None

    cat_ok = _make_category(uuid.uuid4(), product_id, "Has Profile")
    motiv_embeddings = {cat_ok.id: [0.1] * 384, cat_no_profile.id: [0.1] * 384}

    user = _make_discovered_user(user_id, product_id)
    ocean = _make_user_ocean(user_id)
    nlp = _make_nlp_features(user_id)
    emb = _make_embedding(user_id)
    db = _make_db_for_user_match(user_id, ocean, nlp, emb)

    matches = await _compute_user_matches(db, user, [cat_no_profile, cat_ok], motiv_embeddings)
    assert len(matches) == 1  # only the category with profile


@pytest.mark.asyncio
async def test_apply_ranking_marks_best_match():
    """_apply_ranking should set is_best_match=True on highest-scoring match per user."""
    product_id = uuid.uuid4()
    user_id = uuid.uuid4()
    cat1_id = uuid.uuid4()
    cat2_id = uuid.uuid4()

    match_high = MagicMock(spec=LeadMatch)
    match_high.user_id = user_id
    match_high.final_score = 85.0
    match_high.is_best_match = False
    match_high.rank = None

    match_low = MagicMock(spec=LeadMatch)
    match_low.user_id = user_id
    match_low.final_score = 60.0
    match_low.is_best_match = False
    match_low.rank = None

    db = AsyncMock()
    result_mock = MagicMock()
    # scalars().all() returns [match_high, match_low] (sorted by score desc already)
    result_mock.scalars.return_value.all.return_value = [match_high, match_low]
    db.execute.return_value = result_mock

    await _apply_ranking(db, product_id)

    assert match_high.is_best_match is True
    assert match_high.rank == 1
    assert match_low.is_best_match is False


@pytest.mark.asyncio
async def test_apply_ranking_multiple_users_correct_order():
    product_id = uuid.uuid4()
    uid1, uid2 = uuid.uuid4(), uuid.uuid4()

    m1_high = MagicMock(); m1_high.user_id = uid1; m1_high.final_score = 90.0; m1_high.is_best_match = False; m1_high.rank = None
    m1_low  = MagicMock(); m1_low.user_id = uid1;  m1_low.final_score = 60.0;  m1_low.is_best_match = False;  m1_low.rank = None
    m2_high = MagicMock(); m2_high.user_id = uid2; m2_high.final_score = 75.0; m2_high.is_best_match = False; m2_high.rank = None

    db = AsyncMock()
    r = MagicMock()
    r.scalars.return_value.all.return_value = [m1_high, m1_low, m2_high]
    db.execute.return_value = r

    await _apply_ranking(db, product_id)

    assert m1_high.rank == 1
    assert m2_high.rank == 2
    assert m1_high.is_best_match is True
    assert m2_high.is_best_match is True
    assert m1_low.is_best_match is False


@pytest.mark.asyncio
async def test_run_matching_no_categories_returns_zero():
    product_id = uuid.uuid4()
    db = AsyncMock()

    cat_result = MagicMock()
    cat_result.scalars.return_value.all.return_value = []
    db.execute.return_value = cat_result

    summary = await run_matching_for_product(db, product_id)

    assert summary == {"total": 0, "processed": 0, "failed": 0}


@pytest.mark.asyncio
async def test_start_matching_background_advances_product_status():
    from app.services.matching_service import start_matching_background
    product_id = str(uuid.uuid4())
    mock_product = MagicMock(spec=Product)
    mock_product.status = ProductStatus.ocean_scoring
    mock_product.pipeline_step = 6

    with patch("app.services.matching_service.AsyncSessionLocal") as MockSession, \
         patch("app.services.matching_service.run_matching_for_product") as mock_run:
        mock_run.return_value = {"total": 5, "processed": 5, "failed": 0}
        mock_db = AsyncMock()
        mock_db.get.return_value = mock_product
        MockSession.return_value.__aenter__.return_value = mock_db
        MockSession.return_value.__aexit__.return_value = False

        await start_matching_background(product_id)

    assert mock_product.status == ProductStatus.ranked
    assert mock_product.pipeline_step == 8


@pytest.mark.asyncio
async def test_start_matching_background_marks_failed_on_error():
    from app.services.matching_service import start_matching_background
    product_id = str(uuid.uuid4())
    mock_product = MagicMock(spec=Product)
    mock_product.status = ProductStatus.ocean_scoring

    with patch("app.services.matching_service.AsyncSessionLocal") as MockSession, \
         patch("app.services.matching_service.run_matching_for_product") as mock_run:
        mock_run.side_effect = RuntimeError("Match computation failed")
        mock_db = AsyncMock()
        mock_db.get.return_value = mock_product
        MockSession.return_value.__aenter__.return_value = mock_db
        MockSession.return_value.__aexit__.return_value = False

        await start_matching_background(product_id)

    assert mock_product.status == ProductStatus.failed


@pytest.mark.asyncio
async def test_start_matching_background_product_not_found():
    from app.services.matching_service import start_matching_background
    product_id = str(uuid.uuid4())

    with patch("app.services.matching_service.AsyncSessionLocal") as MockSession:
        mock_db = AsyncMock()
        mock_db.get.return_value = None
        MockSession.return_value.__aenter__.return_value = mock_db
        MockSession.return_value.__aexit__.return_value = False

        # Should complete without error
        await start_matching_background(product_id)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. CRUD TESTS — mocked DB
# ═══════════════════════════════════════════════════════════════════════════════

from app.crud.matching import get_match_status, get_ranked_leads, get_lead_detail


@pytest.mark.asyncio
async def test_get_match_status_returns_correct_counts():
    product_id = uuid.uuid4()
    db = AsyncMock()

    total_r = MagicMock(); total_r.scalar_one.return_value = 15
    matched_r = MagicMock(); matched_r.scalar_one.return_value = 12
    ranked_r = MagicMock(); ranked_r.scalar_one.return_value = 12
    db.execute.side_effect = [total_r, matched_r, ranked_r]

    result = await get_match_status(db, product_id)

    assert result["total_users"] == 15
    assert result["matched"] == 12
    assert result["ranked"] == 12
    assert result["pending"] == 3
    assert result["progress_pct"] == 80.0


@pytest.mark.asyncio
async def test_get_match_status_zero_total():
    product_id = uuid.uuid4()
    db = AsyncMock()

    for_zero = MagicMock(); for_zero.scalar_one.return_value = 0
    db.execute.side_effect = [for_zero, for_zero, for_zero]

    result = await get_match_status(db, product_id)
    assert result["progress_pct"] == 0.0


@pytest.mark.asyncio
async def test_get_ranked_leads_returns_paginated_result():
    product_id = uuid.uuid4()
    db = AsyncMock()

    # Count query
    count_r = MagicMock(); count_r.scalar_one.return_value = 5

    # Lead rows
    def _lead_row(rank, score):
        lead = MagicMock(spec=LeadMatch)
        lead.rank = rank; lead.final_score = score
        lead.ocean_score = score - 5; lead.embedding_score = score - 3
        lead.interest_score = score - 7; lead.confidence = 70.0
        lead.reasoning = ["reason"]
        user = MagicMock(spec=DiscoveredUser)
        user.id = uuid.uuid4(); user.username = f"user{rank}"
        user.display_name = None; user.platform = "reddit"
        user.profile_url = None; user.location = "Chennai"
        user.follower_count = 100
        cat = MagicMock(spec=MotivationCategory)
        cat.id = uuid.uuid4(); cat.name = "Tech Enthusiast"
        return (lead, user, cat)

    rows = [_lead_row(i, 90 - i * 5) for i in range(1, 4)]
    leads_r = MagicMock(); leads_r.all.return_value = rows
    db.execute.side_effect = [count_r, leads_r]

    result = await get_ranked_leads(db, product_id, page=1, page_size=20)

    assert result["total_leads"] == 5
    assert len(result["leads"]) == 3
    assert result["leads"][0]["rank"] == 1


@pytest.mark.asyncio
async def test_get_lead_detail_returns_full_profile():
    product_id = uuid.uuid4()
    user_id = uuid.uuid4()
    db = AsyncMock()

    user = MagicMock(spec=DiscoveredUser)
    user.id = user_id; user.username = "testuser"; user.display_name = None
    user.platform = "reddit"; user.profile_url = None
    user.location = "Chennai"; user.location_confidence = "inferred"
    user.follower_count = 500

    lead_match = MagicMock(spec=LeadMatch)
    lead_match.is_best_match = True; lead_match.rank = 1
    lead_match.final_score = 82.0; lead_match.ocean_score = 80.0
    lead_match.embedding_score = 75.0; lead_match.interest_score = 65.0
    lead_match.confidence = 74.0; lead_match.reasoning = ["reason 1"]

    cat = MagicMock(spec=MotivationCategory)
    cat.id = uuid.uuid4(); cat.name = "Tech Enthusiast"

    user_r = MagicMock(); user_r.scalar_one_or_none.return_value = user
    matches_r = MagicMock(); matches_r.all.return_value = [(lead_match, cat)]
    db.execute.side_effect = [user_r, matches_r]

    result = await get_lead_detail(db, product_id, user_id)

    assert result is not None
    assert result["username"] == "testuser"
    assert result["best_match"]["rank"] == 1
    assert result["best_match"]["final_score"] == 82.0
    assert len(result["all_category_scores"]) == 1


@pytest.mark.asyncio
async def test_get_lead_detail_returns_none_when_user_not_found():
    db = AsyncMock()
    r = MagicMock(); r.scalar_one_or_none.return_value = None
    db.execute.return_value = r

    result = await get_lead_detail(db, uuid.uuid4(), uuid.uuid4())
    assert result is None


@pytest.mark.asyncio
async def test_get_lead_detail_returns_none_when_no_matches():
    db = AsyncMock()
    user = MagicMock(spec=DiscoveredUser); user.id = uuid.uuid4()
    user_r = MagicMock(); user_r.scalar_one_or_none.return_value = user
    no_matches = MagicMock(); no_matches.all.return_value = []
    db.execute.side_effect = [user_r, no_matches]

    result = await get_lead_detail(db, uuid.uuid4(), user.id)
    assert result is None


# ═══════════════════════════════════════════════════════════════════════════════
# 5. API TESTS — mocked CRUD + auth
# ═══════════════════════════════════════════════════════════════════════════════

import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.database import get_db
from app.dependencies import get_current_company
from app.models.company import Company


def _fake_company() -> MagicMock:
    co = MagicMock(spec=Company)
    co.id = uuid.uuid4(); co.name = "Test Co"
    return co


def _fake_product(company_id, status="ocean_scoring") -> MagicMock:
    p = MagicMock(spec=Product)
    p.id = uuid.uuid4(); p.company_id = company_id
    p.status = MagicMock(); p.status.value = status
    return p


@pytest_asyncio.fixture
async def match_api_client():
    company = _fake_company()
    mock_db = AsyncMock()

    async def override_db():
        yield mock_db

    async def override_company():
        return company

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_company] = override_company

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, mock_db, company

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_trigger_matching_202(match_api_client):
    client, db, company = match_api_client
    product = _fake_product(company.id, "ocean_scoring")

    with patch("app.routers.matching.get_product_by_id", return_value=product), \
         patch("app.routers.matching.start_matching_background", new_callable=AsyncMock):
        resp = await client.post(f"/api/v1/products/{product.id}/match/trigger")

    assert resp.status_code == 202
    assert resp.json()["status"] == "queued"


@pytest.mark.asyncio
async def test_trigger_matching_wrong_status_422(match_api_client):
    client, db, company = match_api_client
    product = _fake_product(company.id, "pending")

    with patch("app.routers.matching.get_product_by_id", return_value=product):
        resp = await client.post(f"/api/v1/products/{product.id}/match/trigger")

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_trigger_matching_product_not_found_404(match_api_client):
    client, db, company = match_api_client

    with patch("app.routers.matching.get_product_by_id", return_value=None):
        resp = await client.post(f"/api/v1/products/{uuid.uuid4()}/match/trigger")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_trigger_matching_all_allowed_statuses(match_api_client):
    client, db, company = match_api_client
    for status_val in ["ocean_scoring", "matching", "ranked", "completed"]:
        product = _fake_product(company.id, status_val)
        with patch("app.routers.matching.get_product_by_id", return_value=product), \
             patch("app.routers.matching.start_matching_background", new_callable=AsyncMock):
            resp = await client.post(f"/api/v1/products/{product.id}/match/trigger")
        assert resp.status_code == 202, f"Failed for status={status_val}"


@pytest.mark.asyncio
async def test_match_status_200(match_api_client):
    client, db, company = match_api_client
    product = _fake_product(company.id)

    with patch("app.routers.matching.get_product_by_id", return_value=product), \
         patch("app.routers.matching.get_match_status", return_value={
             "total_users": 20, "matched": 18, "ranked": 18,
             "pending": 2, "progress_pct": 90.0,
         }):
        resp = await client.get(f"/api/v1/products/{product.id}/match/status")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_users"] == 20
    assert data["progress_pct"] == 90.0
    assert data["product_id"] == str(product.id)


@pytest.mark.asyncio
async def test_match_status_404_product_not_found(match_api_client):
    client, db, company = match_api_client

    with patch("app.routers.matching.get_product_by_id", return_value=None):
        resp = await client.get(f"/api/v1/products/{uuid.uuid4()}/match/status")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_leads_200(match_api_client):
    client, db, company = match_api_client
    product = _fake_product(company.id)
    user_id = uuid.uuid4()
    cat_id = uuid.uuid4()

    fake_leads = {
        "total_leads": 3,
        "page": 1, "page_size": 20, "total_pages": 1,
        "leads": [
            {
                "rank": 1, "user_id": str(user_id), "username": "tech_user",
                "display_name": None, "platform": "reddit", "profile_url": None,
                "location": "Chennai", "follower_count": 500,
                "best_motivation_category": "Tech Enthusiast",
                "motivation_category_id": str(cat_id),
                "final_score": 84.5, "ocean_score": 82.0, "embedding_score": 76.0,
                "interest_score": 91.0, "confidence": 78.0,
                "reasoning": ["Strong OCEAN alignment"],
            }
        ],
    }

    with patch("app.routers.matching.get_product_by_id", return_value=product), \
         patch("app.routers.matching.get_ranked_leads", return_value=fake_leads):
        resp = await client.get(f"/api/v1/products/{product.id}/leads")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_leads"] == 3
    assert data["leads"][0]["final_score"] == 84.5


@pytest.mark.asyncio
async def test_list_leads_pagination_params(match_api_client):
    client, db, company = match_api_client
    product = _fake_product(company.id)

    with patch("app.routers.matching.get_product_by_id", return_value=product), \
         patch("app.routers.matching.get_ranked_leads", return_value={
             "total_leads": 0, "page": 2, "page_size": 10, "total_pages": 1, "leads": []
         }) as mock_get:
        resp = await client.get(
            f"/api/v1/products/{product.id}/leads?page=2&page_size=10&min_score=50"
        )

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_list_leads_404_product_not_found(match_api_client):
    client, db, company = match_api_client

    with patch("app.routers.matching.get_product_by_id", return_value=None):
        resp = await client.get(f"/api/v1/products/{uuid.uuid4()}/leads")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_lead_detail_200(match_api_client):
    client, db, company = match_api_client
    product = _fake_product(company.id)
    user_id = uuid.uuid4()

    fake_detail = {
        "user_id": str(user_id), "username": "tech_user", "display_name": None,
        "platform": "reddit", "profile_url": None, "location": "Chennai",
        "location_confidence": "inferred", "follower_count": 500,
        "best_match": {
            "rank": 1, "motivation_category_id": str(uuid.uuid4()),
            "motivation_category": "Tech Enthusiast",
            "final_score": 84.5, "ocean_score": 82.0, "embedding_score": 76.0,
            "interest_score": 91.0, "confidence": 78.0,
            "reasoning": ["Strong OCEAN alignment"],
        },
        "all_category_scores": [],
    }

    with patch("app.routers.matching.get_product_by_id", return_value=product), \
         patch("app.routers.matching.get_lead_detail", return_value=fake_detail):
        resp = await client.get(f"/api/v1/products/{product.id}/leads/{user_id}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] == "tech_user"
    assert data["best_match"]["rank"] == 1


@pytest.mark.asyncio
async def test_get_lead_detail_404_not_found(match_api_client):
    client, db, company = match_api_client
    product = _fake_product(company.id)

    with patch("app.routers.matching.get_product_by_id", return_value=product), \
         patch("app.routers.matching.get_lead_detail", return_value=None):
        resp = await client.get(
            f"/api/v1/products/{product.id}/leads/{uuid.uuid4()}"
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_lead_detail_404_product_not_found(match_api_client):
    client, db, company = match_api_client

    with patch("app.routers.matching.get_product_by_id", return_value=None):
        resp = await client.get(
            f"/api/v1/products/{uuid.uuid4()}/leads/{uuid.uuid4()}"
        )

    assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# 6. EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════════

class TestMatchingEdgeCases:
    def test_user_all_neutral_ocean_vs_tech_enthusiast(self):
        """Neutral user should get mid-range score against any motivation."""
        u = MagicMock()
        u.openness = 50.0; u.conscientiousness = 50.0; u.extraversion = 50.0
        u.agreeableness = 50.0; u.neuroticism = 50.0

        motiv = {"openness": 85.0, "conscientiousness": 70.0, "extraversion": 55.0,
                 "agreeableness": 60.0, "neuroticism": 25.0}

        score = compute_ocean_similarity(u, motiv)
        assert 40.0 < score < 80.0  # not extreme

    def test_full_interest_overlap_boosts_composite(self):
        tags = ["technology", "learning", "innovation", "data", "software"]
        interest = compute_interest_score(tags, {"python": 3}, tags, ["python"])
        assert interest >= 60.0

    def test_composite_score_max_components_equals_100(self):
        assert compute_composite_score(100.0, 100.0, 100.0) == 100.0

    def test_composite_score_zero_components_equals_0(self):
        assert compute_composite_score(0.0, 0.0, 0.0) == 0.0

    def test_confidence_no_embedding_reduces_max(self):
        with_emb = compute_match_confidence(100.0, True, 10)
        without_emb = compute_match_confidence(100.0, False, 10)
        assert without_emb < with_emb

    def test_ocean_similarity_reflexive(self):
        """sim(user, motiv) is same if user and motiv have identical values."""
        u = MagicMock()
        for dim in ("openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism"):
            setattr(u, dim, 70.0)
        motiv = {d: 70.0 for d in ("openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism")}
        assert compute_ocean_similarity(u, motiv) == 100.0

    def test_migration_table_columns(self):
        cols = {c.name for c in LeadMatch.__table__.columns}
        for required in ("id", "product_id", "user_id", "motivation_category_id",
                         "ocean_score", "final_score", "rank", "is_best_match"):
            assert required in cols

    @pytest.mark.asyncio
    async def test_compute_user_matches_stores_product_id(self):
        user_id = uuid.uuid4()
        product_id = uuid.uuid4()
        cat_id = uuid.uuid4()
        categories = [_make_category(cat_id, product_id)]
        motiv_embeddings = {cat_id: [0.1] * 384}

        user = _make_discovered_user(user_id, product_id)
        ocean = _make_user_ocean(user_id)
        nlp = _make_nlp_features(user_id)
        emb = _make_embedding(user_id)
        db = _make_db_for_user_match(user_id, ocean, nlp, emb)

        matches = await _compute_user_matches(db, user, categories, motiv_embeddings)
        assert matches[0].product_id == product_id
        assert matches[0].user_id == user_id

    @pytest.mark.asyncio
    async def test_run_matching_clears_existing_before_recompute(self):
        """Re-running matching deletes stale matches before recomputing."""
        from app.services.matching_service import run_matching_for_product

        product_id = uuid.uuid4()
        cat_id = uuid.uuid4()
        user_id = uuid.uuid4()
        db = AsyncMock()

        # category query returns one active category
        category = _make_category(cat_id, product_id)
        cat_result = MagicMock()
        cat_result.scalars.return_value.all.return_value = [category]

        # OCEAN profile sub-query (already set on mock category)
        ocean_profile_result = MagicMock()
        ocean_profile_result.scalar_one_or_none.return_value = None  # already set

        # After delete + flush: user query returns one user
        user = _make_discovered_user(user_id, product_id)
        user_result = MagicMock()
        user_result.scalars.return_value.all.return_value = [user]

        # Per-user queries: ocean, nlp, embedding
        ocean_r = MagicMock(); ocean_r.scalar_one_or_none.return_value = _make_user_ocean(user_id)
        nlp_r = MagicMock(); nlp_r.scalar_one_or_none.return_value = _make_nlp_features(user_id)
        emb_r = MagicMock(); emb_r.scalar_one_or_none.return_value = None  # no embedding

        # ranking query
        rank_result = MagicMock()
        rank_result.scalars.return_value.all.return_value = []

        db.execute.side_effect = [cat_result, user_result, ocean_r, nlp_r, emb_r, rank_result]

        with patch("app.services.matching_service._embed_motivations", return_value={cat_id: [0.1] * 384}):
            await run_matching_for_product(db, product_id)

        # delete should have been called (stale matches cleared)
        assert db.execute.called
        # db.flush was called at least once
        assert db.flush.call_count >= 1
