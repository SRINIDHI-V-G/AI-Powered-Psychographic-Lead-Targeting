"""
Phase D OCEAN Scoring — test suite.

Coverage:
  1. OceanPrompter  — prompt building + response parsing (unit)
  2. HeuristicScorer — Empath → OCEAN signal mapping (unit)
  3. OceanService  — per-user + batch service (mocked DB)
  4. OceanCRUD     — get_ocean_status, get_user_ocean_score (mocked DB)
  5. OceanAPI      — endpoint status codes + response shapes (mocked)
  6. EdgeCases     — malformed LLM, clamping, duplicate prevention, etc.

Run with:
  cd backend && pytest tests/test_phase_d.py -v
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# 1. OCEAN PROMPTER — unit tests
# ═══════════════════════════════════════════════════════════════════════════════

from app.ml.ocean.ocean_prompter import (
    build_ocean_prompt,
    parse_ocean_response,
    OCEAN_SYSTEM_PROMPT,
    MAX_CONTENT_SAMPLES,
    MAX_SAMPLE_CHARS,
)


class TestOceanPromptBuilder:
    def _base_prompt(self) -> str:
        return build_ocean_prompt(
            interest_tags=["technology", "learning", "innovation"],
            empath_scores={"intellectual": 0.18, "achievement": 0.12, "work": 0.08},
            keyword_frequency={"python": 5, "learning": 4, "data": 3},
            vocabulary_richness=0.72,
            avg_sentence_length=14.2,
            total_tokens=234,
        )

    def test_prompt_contains_interest_tags(self):
        p = self._base_prompt()
        assert "technology" in p
        assert "learning" in p

    def test_prompt_contains_empath_signals(self):
        p = self._base_prompt()
        assert "intellectual" in p
        assert "achievement" in p

    def test_prompt_contains_keywords(self):
        p = self._base_prompt()
        assert "python" in p
        assert "data" in p

    def test_prompt_contains_writing_metrics(self):
        p = self._base_prompt()
        assert "0.72" in p
        assert "14.2" in p
        assert "234" in p

    def test_prompt_contains_ocean_dimensions(self):
        p = self._base_prompt()
        for dim in ("Openness", "Conscientiousness", "Extraversion", "Agreeableness", "Neuroticism"):
            assert dim in p

    def test_prompt_contains_json_format_hint(self):
        p = self._base_prompt()
        assert '"openness"' in p
        assert '"neuroticism"' in p
        assert '"reasoning"' in p

    def test_content_samples_included(self):
        p = build_ocean_prompt(
            interest_tags=[],
            empath_scores={},
            keyword_frequency={},
            vocabulary_richness=0.5,
            avg_sentence_length=10.0,
            total_tokens=100,
            content_samples=["I love building things", "Learning new tech is fun"],
        )
        assert "I love building things" in p
        assert "Learning new tech is fun" in p

    def test_content_samples_truncated(self):
        long_sample = "x" * 300
        p = build_ocean_prompt(
            interest_tags=[],
            empath_scores={},
            keyword_frequency={},
            vocabulary_richness=0.5,
            avg_sentence_length=10.0,
            total_tokens=100,
            content_samples=[long_sample],
        )
        assert "x" * (MAX_SAMPLE_CHARS + 1) not in p

    def test_max_content_samples_respected(self):
        samples = [f"Sample {i}" for i in range(10)]
        p = build_ocean_prompt(
            interest_tags=[],
            empath_scores={},
            keyword_frequency={},
            vocabulary_richness=0.5,
            avg_sentence_length=10.0,
            total_tokens=100,
            content_samples=samples,
        )
        # Only MAX_CONTENT_SAMPLES should appear
        count = sum(1 for s in samples if s in p)
        assert count <= MAX_CONTENT_SAMPLES

    def test_prompt_is_compact(self):
        p = self._base_prompt()
        # Rough token estimate: characters / 4 → should be < 700 tokens
        assert len(p) < 2800

    def test_system_prompt_not_empty(self):
        assert len(OCEAN_SYSTEM_PROMPT) > 50
        assert "OCEAN" in OCEAN_SYSTEM_PROMPT or "personality" in OCEAN_SYSTEM_PROMPT.lower()


class TestParseOceanResponse:
    def _valid_json(self) -> str:
        return (
            '{"openness":75,"conscientiousness":60,"extraversion":45,'
            '"agreeableness":70,"neuroticism":30,"confidence":68,'
            '"reasoning":{"openness":"Curious user","conscientiousness":"Organized",'
            '"extraversion":"Introverted","agreeableness":"Empathetic",'
            '"neuroticism":"Stable"}}'
        )

    def test_parses_valid_json(self):
        result = parse_ocean_response(self._valid_json())
        assert result is not None
        assert result["openness"] == 75.0
        assert result["neuroticism"] == 30.0

    def test_all_dimensions_present(self):
        result = parse_ocean_response(self._valid_json())
        for dim in ("openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism"):
            assert dim in result

    def test_confidence_present(self):
        result = parse_ocean_response(self._valid_json())
        assert "confidence" in result
        assert result["confidence"] == 68.0

    def test_reasoning_dict_preserved(self):
        result = parse_ocean_response(self._valid_json())
        assert isinstance(result["reasoning"], dict)
        assert result["reasoning"]["openness"] == "Curious user"

    def test_scoring_method_is_llm(self):
        result = parse_ocean_response(self._valid_json())
        assert result["scoring_method"] == "llm"

    def test_scores_clamped_above_100(self):
        raw = '{"openness":150,"conscientiousness":60,"extraversion":45,"agreeableness":70,"neuroticism":30,"confidence":68,"reasoning":{}}'
        result = parse_ocean_response(raw)
        assert result["openness"] == 100.0

    def test_scores_clamped_below_0(self):
        raw = '{"openness":-20,"conscientiousness":60,"extraversion":45,"agreeableness":70,"neuroticism":30,"confidence":68,"reasoning":{}}'
        result = parse_ocean_response(raw)
        assert result["openness"] == 0.0

    def test_missing_dimension_defaults_to_50(self):
        # neuroticism is missing
        raw = '{"openness":75,"conscientiousness":60,"extraversion":45,"agreeableness":70,"confidence":68,"reasoning":{}}'
        result = parse_ocean_response(raw)
        assert result["neuroticism"] == 50.0

    def test_string_score_defaults_to_50(self):
        raw = '{"openness":"high","conscientiousness":60,"extraversion":45,"agreeableness":70,"neuroticism":30,"confidence":68,"reasoning":{}}'
        result = parse_ocean_response(raw)
        assert result["openness"] == 50.0

    def test_null_score_defaults_to_50(self):
        raw = '{"openness":null,"conscientiousness":60,"extraversion":45,"agreeableness":70,"neuroticism":30,"confidence":68,"reasoning":{}}'
        result = parse_ocean_response(raw)
        assert result["openness"] == 50.0

    def test_markdown_fences_stripped(self):
        raw = '```json\n{"openness":70,"conscientiousness":65,"extraversion":50,"agreeableness":60,"neuroticism":35,"confidence":72,"reasoning":{}}\n```'
        result = parse_ocean_response(raw)
        assert result is not None
        assert result["openness"] == 70.0

    def test_extra_fields_ignored(self):
        raw = '{"openness":70,"conscientiousness":65,"extraversion":50,"agreeableness":60,"neuroticism":35,"confidence":72,"reasoning":{},"extra_field":"ignored"}'
        result = parse_ocean_response(raw)
        assert result is not None

    def test_empty_string_returns_none(self):
        assert parse_ocean_response("") is None

    def test_garbage_input_returns_none(self):
        assert parse_ocean_response("not json at all!!!") is None

    def test_partial_json_recovered(self):
        # Truncated but contains some scores
        raw = '{"openness":75,"conscientiousness":60,"extraversion":45'
        result = parse_ocean_response(raw)
        # Should either succeed with partial recovery or return None gracefully
        if result is not None:
            assert 0 <= result["openness"] <= 100

    def test_reasoning_long_string_truncated(self):
        long_reason = "x" * 1000
        raw = (
            '{"openness":75,"conscientiousness":60,"extraversion":45,'
            f'"agreeableness":70,"neuroticism":30,"confidence":68,'
            f'"reasoning":{{"openness":"{long_reason}","conscientiousness":"",'
            '"extraversion":"","agreeableness":"","neuroticism":""}}'
            "}"
        )
        result = parse_ocean_response(raw)
        if result and result.get("reasoning", {}).get("openness"):
            assert len(result["reasoning"]["openness"]) <= 500

    def test_non_dict_reasoning_becomes_empty_dict(self):
        raw = '{"openness":75,"conscientiousness":60,"extraversion":45,"agreeableness":70,"neuroticism":30,"confidence":68,"reasoning":"not a dict"}'
        result = parse_ocean_response(raw)
        assert result is not None
        assert isinstance(result["reasoning"], dict)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. HEURISTIC SCORER — unit tests
# ═══════════════════════════════════════════════════════════════════════════════

from app.ml.ocean.heuristic_scorer import (
    compute_heuristic_scores,
    compute_insufficient_content_scores,
    compute_confidence,
)


class TestHeuristicScorer:
    def test_empty_empath_returns_all_neutral(self):
        result = compute_heuristic_scores({}, total_tokens=100, vocabulary_richness=0.5)
        for dim in ("openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism"):
            assert result[dim] == 50.0

    def test_strong_openness_signal(self):
        empath = {"art": 0.2, "music": 0.18, "intellectual": 0.15, "creativity": 0.12}
        result = compute_heuristic_scores(empath, total_tokens=200)
        assert result["openness"] > 65

    def test_strong_neuroticism_signal(self):
        empath = {"negative_emotion": 0.2, "anxiety": 0.18, "anger": 0.15, "sadness": 0.12}
        result = compute_heuristic_scores(empath, total_tokens=200)
        assert result["neuroticism"] > 65

    def test_strong_conscientiousness_signal(self):
        empath = {"work": 0.2, "achievement": 0.18, "discipline": 0.15, "order": 0.12}
        result = compute_heuristic_scores(empath, total_tokens=200)
        assert result["conscientiousness"] > 65

    def test_strong_extraversion_signal(self):
        empath = {"social": 0.2, "fun": 0.18, "joy": 0.15, "party": 0.12}
        result = compute_heuristic_scores(empath, total_tokens=200)
        assert result["extraversion"] > 65

    def test_strong_agreeableness_signal(self):
        empath = {"affection": 0.2, "helping": 0.18, "love": 0.15, "care": 0.12}
        result = compute_heuristic_scores(empath, total_tokens=200)
        assert result["agreeableness"] > 65

    def test_all_scores_in_range(self):
        import random
        random.seed(42)
        empath = {f"cat{i}": random.uniform(0.01, 0.3) for i in range(20)}
        result = compute_heuristic_scores(empath, total_tokens=500, vocabulary_richness=0.7)
        for dim in ("openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism"):
            assert 0.0 <= result[dim] <= 100.0

    def test_scoring_method_is_heuristic(self):
        result = compute_heuristic_scores({"art": 0.1})
        assert result["scoring_method"] == "heuristic"

    def test_reasoning_dict_present(self):
        result = compute_heuristic_scores({"intellectual": 0.15, "work": 0.1})
        assert isinstance(result["reasoning"], dict)
        for dim in ("openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism"):
            assert dim in result["reasoning"]

    def test_reasoning_includes_matched_signals(self):
        result = compute_heuristic_scores({"art": 0.15})
        assert "art" in result["reasoning"]["openness"]

    def test_high_tokens_high_confidence(self):
        result_low = compute_heuristic_scores({"art": 0.1}, total_tokens=10)
        result_high = compute_heuristic_scores({"art": 0.1}, total_tokens=500)
        assert result_high["confidence"] > result_low["confidence"]

    def test_confidence_in_range(self):
        result = compute_heuristic_scores(
            {"art": 0.1, "work": 0.1},
            total_tokens=200,
            vocabulary_richness=0.7,
        )
        assert 0.0 <= result["confidence"] <= 100.0


class TestComputeConfidence:
    def test_zero_tokens_zero_confidence(self):
        conf = compute_confidence(0, {}, 0.0)
        assert conf == 0.0

    def test_max_tokens_contributes_50(self):
        conf = compute_confidence(500, {}, 0.0)
        assert conf == 50.0

    def test_empath_coverage_contributes(self):
        conf_no_empath = compute_confidence(100, {}, 0.0)
        conf_with_empath = compute_confidence(100, {f"cat{i}": 0.1 for i in range(30)}, 0.0)
        assert conf_with_empath > conf_no_empath

    def test_vocab_richness_contributes(self):
        conf_low = compute_confidence(100, {}, 0.0)
        conf_high = compute_confidence(100, {}, 1.0)
        assert conf_high > conf_low

    def test_max_confidence_is_100(self):
        conf = compute_confidence(10000, {f"cat{i}": 0.1 for i in range(100)}, 2.0)
        assert conf <= 100.0


class TestInsufficientContentScores:
    def test_all_dimensions_neutral(self):
        result = compute_insufficient_content_scores()
        for dim in ("openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism"):
            assert result[dim] == 50.0

    def test_very_low_confidence(self):
        result = compute_insufficient_content_scores()
        assert result["confidence"] <= 15.0

    def test_scoring_method(self):
        result = compute_insufficient_content_scores()
        assert result["scoring_method"] == "insufficient_content"

    def test_reasoning_present(self):
        result = compute_insufficient_content_scores()
        assert isinstance(result["reasoning"], dict)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. OCEAN SERVICE — mocked async tests
# ═══════════════════════════════════════════════════════════════════════════════

from app.models.discovery import DiscoveredUser, UserContent
from app.models.nlp import UserNlpFeatures
from app.models.ocean import UserOceanScore
from app.models.product import Product, ProductStatus
from app.services.ocean_service import process_user_ocean, run_ocean_for_product


def _mock_nlp_features(
    user_id: uuid.UUID,
    total_tokens: int = 200,
    empath: dict | None = None,
    vocabulary_richness: float = 0.65,
    interest_tags: list | None = None,
    keyword_frequency: dict | None = None,
    avg_sentence_length: float = 12.0,
) -> MagicMock:
    nlp = MagicMock(spec=UserNlpFeatures)
    nlp.user_id = user_id
    nlp.total_tokens = total_tokens
    nlp.empath_scores = empath if empath is not None else {"intellectual": 0.15, "work": 0.1}
    nlp.vocabulary_richness = vocabulary_richness
    nlp.interest_tags = interest_tags if interest_tags is not None else ["technology", "learning"]
    nlp.keyword_frequency = keyword_frequency if keyword_frequency is not None else {"python": 5}
    nlp.avg_sentence_length = avg_sentence_length
    return nlp


def _mock_user(user_id: uuid.UUID, *, ocean_scored: bool = False) -> MagicMock:
    u = MagicMock(spec=DiscoveredUser)
    u.id = user_id
    u.username = "testuser"
    u.ocean_scored = ocean_scored
    return u


def _make_db(
    user: MagicMock,
    nlp: MagicMock | None,
    content_items: list | None = None,
) -> AsyncMock:
    db = AsyncMock()
    db.get.return_value = user

    nlp_result = MagicMock()
    nlp_result.scalar_one_or_none.return_value = nlp

    # existing score check → no stale record
    no_existing = MagicMock()
    no_existing.scalar_one_or_none.return_value = None

    # content items result
    content_result = MagicMock()
    content_result.scalars.return_value.all.return_value = content_items or []

    db.execute.side_effect = [nlp_result, content_result, no_existing]
    return db


@pytest.mark.asyncio
async def test_process_user_ocean_success_heuristic():
    """Heuristic path: USE_MOCK_LLM=True"""
    user_id = uuid.uuid4()
    user = _mock_user(user_id)
    nlp = _mock_nlp_features(user_id)
    db = _make_db(user, nlp)

    with patch("app.services.ocean_service.settings") as mock_settings:
        mock_settings.USE_MOCK_LLM = True

        result = await process_user_ocean(db, user_id)

    assert result is True
    assert user.ocean_scored is True
    assert db.add.called
    added_score: UserOceanScore = db.add.call_args[0][0]
    assert isinstance(added_score, UserOceanScore)
    assert added_score.scoring_method == "heuristic"
    assert 0 <= added_score.openness <= 100
    assert 0 <= added_score.neuroticism <= 100


@pytest.mark.asyncio
async def test_process_user_ocean_already_scored():
    user_id = uuid.uuid4()
    user = _mock_user(user_id, ocean_scored=True)
    db = AsyncMock()
    db.get.return_value = user

    result = await process_user_ocean(db, user_id)

    assert result is False
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_process_user_ocean_user_not_found():
    db = AsyncMock()
    db.get.return_value = None

    result = await process_user_ocean(db, uuid.uuid4())

    assert result is False


@pytest.mark.asyncio
async def test_process_user_ocean_no_nlp_features():
    """User has no NLP features → insufficient_content scoring."""
    user_id = uuid.uuid4()
    user = _mock_user(user_id)
    db = AsyncMock()
    db.get.return_value = user

    nlp_result = MagicMock()
    nlp_result.scalar_one_or_none.return_value = None
    no_existing = MagicMock()
    no_existing.scalar_one_or_none.return_value = None
    db.execute.side_effect = [nlp_result, no_existing]

    result = await process_user_ocean(db, user_id)

    assert result is True
    added: UserOceanScore = db.add.call_args[0][0]
    assert added.scoring_method == "insufficient_content"
    assert added.openness == 50.0
    assert added.confidence <= 15.0


@pytest.mark.asyncio
async def test_process_user_ocean_insufficient_tokens():
    """User has NLP features but very few tokens → insufficient_content scoring."""
    user_id = uuid.uuid4()
    user = _mock_user(user_id)
    nlp = _mock_nlp_features(user_id, total_tokens=5)  # below MIN_TOKENS_FOR_LLM
    db = _make_db(user, nlp)

    with patch("app.services.ocean_service.settings") as mock_settings:
        mock_settings.USE_MOCK_LLM = False

        result = await process_user_ocean(db, user_id)

    assert result is True
    added: UserOceanScore = db.add.call_args[0][0]
    assert added.scoring_method == "insufficient_content"


@pytest.mark.asyncio
async def test_process_user_ocean_llm_success():
    """Full LLM path returns valid scores."""
    user_id = uuid.uuid4()
    user = _mock_user(user_id)
    nlp = _mock_nlp_features(user_id)
    db = _make_db(user, nlp)

    llm_json = (
        '{"openness":72,"conscientiousness":65,"extraversion":48,'
        '"agreeableness":71,"neuroticism":28,"confidence":74,'
        '"reasoning":{"openness":"Tech enthusiast","conscientiousness":"Methodical",'
        '"extraversion":"Moderate","agreeableness":"Supportive","neuroticism":"Stable"}}'
    )

    with patch("app.services.ocean_service.settings") as mock_settings, \
         patch("app.services.ocean_service.OllamaClient") as MockClient:
        mock_settings.USE_MOCK_LLM = False
        mock_instance = AsyncMock()
        mock_instance.generate.return_value = llm_json
        MockClient.return_value = mock_instance

        result = await process_user_ocean(db, user_id)

    assert result is True
    added: UserOceanScore = db.add.call_args[0][0]
    assert added.scoring_method == "llm"
    assert added.openness == 72.0
    assert added.neuroticism == 28.0
    assert added.reasoning["openness"] == "Tech enthusiast"


@pytest.mark.asyncio
async def test_process_user_ocean_llm_failure_falls_back():
    """LLM connection error → heuristic fallback."""
    user_id = uuid.uuid4()
    user = _mock_user(user_id)
    nlp = _mock_nlp_features(user_id)
    db = _make_db(user, nlp)

    with patch("app.services.ocean_service.settings") as mock_settings, \
         patch("app.services.ocean_service.OllamaClient") as MockClient:
        mock_settings.USE_MOCK_LLM = False
        mock_instance = AsyncMock()
        mock_instance.generate.side_effect = ConnectionError("Ollama not reachable")
        MockClient.return_value = mock_instance

        result = await process_user_ocean(db, user_id)

    assert result is True
    added: UserOceanScore = db.add.call_args[0][0]
    assert added.scoring_method == "heuristic"


@pytest.mark.asyncio
async def test_process_user_ocean_llm_unparseable_falls_back():
    """LLM returns garbage → heuristic fallback."""
    user_id = uuid.uuid4()
    user = _mock_user(user_id)
    nlp = _mock_nlp_features(user_id)
    db = _make_db(user, nlp)

    with patch("app.services.ocean_service.settings") as mock_settings, \
         patch("app.services.ocean_service.OllamaClient") as MockClient:
        mock_settings.USE_MOCK_LLM = False
        mock_instance = AsyncMock()
        mock_instance.generate.return_value = "Sorry, I cannot score this user."
        MockClient.return_value = mock_instance

        result = await process_user_ocean(db, user_id)

    assert result is True
    added: UserOceanScore = db.add.call_args[0][0]
    assert added.scoring_method == "heuristic"


@pytest.mark.asyncio
async def test_process_user_ocean_upsert_replaces_stale():
    """Re-running on an already-scored user (ocean_scored=False but old record exists) replaces it."""
    user_id = uuid.uuid4()
    user = _mock_user(user_id, ocean_scored=False)
    nlp = _mock_nlp_features(user_id)

    stale_score = MagicMock(spec=UserOceanScore)

    db = AsyncMock()
    db.get.return_value = user

    nlp_result = MagicMock()
    nlp_result.scalar_one_or_none.return_value = nlp
    existing_result = MagicMock()
    existing_result.scalar_one_or_none.return_value = stale_score

    # With USE_MOCK_LLM=True there is NO content query, so sequence is:
    # [nlp_result, existing_result]
    db.execute.side_effect = [nlp_result, existing_result]

    with patch("app.services.ocean_service.settings") as mock_settings:
        mock_settings.USE_MOCK_LLM = True
        await process_user_ocean(db, user_id)

    # Old record should be deleted
    db.delete.assert_called_once_with(stale_score)
    # New record should be added
    db.add.assert_called_once()


@pytest.mark.asyncio
async def test_process_user_ocean_marks_ocean_scored():
    user_id = uuid.uuid4()
    user = _mock_user(user_id)
    nlp = _mock_nlp_features(user_id)
    db = _make_db(user, nlp)

    with patch("app.services.ocean_service.settings") as mock_settings:
        mock_settings.USE_MOCK_LLM = True
        await process_user_ocean(db, user_id)

    assert user.ocean_scored is True


@pytest.mark.asyncio
async def test_process_user_ocean_score_dimensions_valid():
    """All OCEAN dimensions must be in 0-100 range."""
    user_id = uuid.uuid4()
    user = _mock_user(user_id)
    nlp = _mock_nlp_features(user_id, empath={"art": 0.2, "negative_emotion": 0.15})
    db = _make_db(user, nlp)

    with patch("app.services.ocean_service.settings") as mock_settings:
        mock_settings.USE_MOCK_LLM = True
        await process_user_ocean(db, user_id)

    added: UserOceanScore = db.add.call_args[0][0]
    for dim in ("openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism"):
        val = getattr(added, dim)
        assert 0.0 <= val <= 100.0, f"{dim}={val} out of range"


@pytest.mark.asyncio
async def test_run_ocean_for_product_summary():
    """run_ocean_for_product processes all users and returns correct summary."""
    product_id = uuid.uuid4()
    user_ids = [uuid.uuid4() for _ in range(3)]

    db = AsyncMock()
    id_result = MagicMock()
    id_result.fetchall.return_value = [(uid,) for uid in user_ids]

    def make_user(uid: uuid.UUID) -> MagicMock:
        u = MagicMock(spec=DiscoveredUser)
        u.id = uid
        u.username = f"user_{uid.hex[:6]}"
        u.ocean_scored = False
        return u

    def make_nlp(uid: uuid.UUID) -> MagicMock:
        nlp = MagicMock(spec=UserNlpFeatures)
        nlp.user_id = uid
        nlp.total_tokens = 200
        nlp.empath_scores = {"intellectual": 0.15}
        nlp.vocabulary_richness = 0.65
        nlp.interest_tags = ["tech"]
        nlp.keyword_frequency = {"python": 3}
        nlp.avg_sentence_length = 12.0
        return nlp

    users = {uid: make_user(uid) for uid in user_ids}
    nlp_map = {uid: make_nlp(uid) for uid in user_ids}

    db.get.side_effect = lambda model, uid: users.get(uid)

    # Per-user calls: nlp_result + content_result + no_existing
    def make_nlp_result(uid):
        r = MagicMock()
        r.scalar_one_or_none.return_value = nlp_map[uid]
        return r

    content_result = MagicMock()
    content_result.scalars.return_value.all.return_value = []
    no_existing = MagicMock()
    no_existing.scalar_one_or_none.return_value = None

    # With USE_MOCK_LLM=True there is NO content query per user — sequence: [nlp, existing]
    side_effects = [id_result]
    for uid in user_ids:
        side_effects.extend([make_nlp_result(uid), no_existing])
    db.execute.side_effect = side_effects

    with patch("app.services.ocean_service.settings") as mock_settings:
        mock_settings.USE_MOCK_LLM = True
        summary = await run_ocean_for_product(db, product_id)

    assert summary["total"] == 3
    assert summary["processed"] == 3
    assert summary["failed"] == 0


@pytest.mark.asyncio
async def test_run_ocean_for_product_counts_failures():
    """Failed users are counted correctly."""
    product_id = uuid.uuid4()
    user_id = uuid.uuid4()

    db = AsyncMock()
    id_result = MagicMock()
    id_result.fetchall.return_value = [(user_id,)]
    db.execute.return_value = id_result

    # db.get raises an error
    db.get.side_effect = Exception("DB error")

    with patch("app.services.ocean_service.settings") as mock_settings:
        mock_settings.USE_MOCK_LLM = True
        summary = await run_ocean_for_product(db, product_id)

    assert summary["total"] == 1
    assert summary["failed"] == 1
    assert summary["processed"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 4. OCEAN CRUD — unit tests (mocked DB)
# ═══════════════════════════════════════════════════════════════════════════════

from app.crud.ocean import get_ocean_status, get_user_ocean_score


@pytest.mark.asyncio
async def test_get_ocean_status_returns_correct_counts():
    product_id = uuid.uuid4()
    db = AsyncMock()

    total_r = MagicMock()
    total_r.scalar_one.return_value = 10
    done_r = MagicMock()
    done_r.scalar_one.return_value = 7
    db.execute.side_effect = [total_r, done_r]

    result = await get_ocean_status(db, product_id)

    assert result["total_users"] == 10
    assert result["ocean_scored"] == 7
    assert result["ocean_pending"] == 3
    assert result["progress_pct"] == 70.0


@pytest.mark.asyncio
async def test_get_ocean_status_zero_total():
    product_id = uuid.uuid4()
    db = AsyncMock()

    total_r = MagicMock()
    total_r.scalar_one.return_value = 0
    done_r = MagicMock()
    done_r.scalar_one.return_value = 0
    db.execute.side_effect = [total_r, done_r]

    result = await get_ocean_status(db, product_id)

    assert result["progress_pct"] == 0.0


@pytest.mark.asyncio
async def test_get_user_ocean_score_found():
    user_id = uuid.uuid4()
    db = AsyncMock()

    mock_score = MagicMock(spec=UserOceanScore)
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = mock_score
    db.execute.return_value = result_mock

    score = await get_user_ocean_score(db, user_id)

    assert score is mock_score


@pytest.mark.asyncio
async def test_get_user_ocean_score_not_found():
    user_id = uuid.uuid4()
    db = AsyncMock()

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    db.execute.return_value = result_mock

    score = await get_user_ocean_score(db, user_id)

    assert score is None


# ═══════════════════════════════════════════════════════════════════════════════
# 5. OCEAN API — endpoint tests (mocked CRUD + auth)
# ═══════════════════════════════════════════════════════════════════════════════

import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.database import get_db
from app.dependencies import get_current_company
from app.models.company import Company


def _fake_company() -> MagicMock:
    co = MagicMock(spec=Company)
    co.id = uuid.uuid4()
    co.name = "Test Co"
    return co


def _fake_product(company_id: uuid.UUID, status: str = "nlp_processing") -> MagicMock:
    p = MagicMock(spec=Product)
    p.id = uuid.uuid4()
    p.company_id = company_id
    p.status = MagicMock()
    p.status.value = status
    return p


@pytest_asyncio.fixture
async def ocean_api_client():
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
async def test_ocean_status_endpoint_200(ocean_api_client):
    client, mock_db, company = ocean_api_client
    product = _fake_product(company.id)

    with patch("app.routers.ocean.get_product_by_id", return_value=product), \
         patch("app.routers.ocean.get_ocean_status", return_value={
             "total_users": 20,
             "ocean_scored": 15,
             "ocean_pending": 5,
             "progress_pct": 75.0,
         }):
        resp = await client.get(f"/api/v1/products/{product.id}/ocean/status")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_users"] == 20
    assert data["ocean_scored"] == 15
    assert data["progress_pct"] == 75.0
    assert data["product_id"] == str(product.id)


@pytest.mark.asyncio
async def test_ocean_status_404_product_not_found(ocean_api_client):
    client, mock_db, company = ocean_api_client

    with patch("app.routers.ocean.get_product_by_id", return_value=None):
        resp = await client.get(f"/api/v1/products/{uuid.uuid4()}/ocean/status")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_ocean_trigger_202_accepted(ocean_api_client):
    client, mock_db, company = ocean_api_client
    product = _fake_product(company.id, status="nlp_processing")

    with patch("app.routers.ocean.get_product_by_id", return_value=product), \
         patch("app.routers.ocean.start_ocean_background", new_callable=AsyncMock):
        resp = await client.post(f"/api/v1/products/{product.id}/ocean/trigger")

    assert resp.status_code == 202
    assert resp.json()["status"] == "queued"


@pytest.mark.asyncio
async def test_ocean_trigger_422_wrong_status(ocean_api_client):
    client, mock_db, company = ocean_api_client
    product = _fake_product(company.id, status="pending")

    with patch("app.routers.ocean.get_product_by_id", return_value=product):
        resp = await client.post(f"/api/v1/products/{product.id}/ocean/trigger")

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_ocean_trigger_404_product_not_found(ocean_api_client):
    client, mock_db, company = ocean_api_client

    with patch("app.routers.ocean.get_product_by_id", return_value=None):
        resp = await client.post(f"/api/v1/products/{uuid.uuid4()}/ocean/trigger")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_ocean_trigger_allowed_statuses(ocean_api_client):
    """All statuses that should allow OCEAN trigger."""
    client, mock_db, company = ocean_api_client
    allowed = ["nlp_processing", "ocean_scoring", "matching", "ranked", "completed"]

    for status_val in allowed:
        product = _fake_product(company.id, status=status_val)
        # Patch where it is USED (the router's local reference), not where it is defined
        with patch("app.routers.ocean.get_product_by_id", return_value=product), \
             patch("app.routers.ocean.start_ocean_background", new_callable=AsyncMock):
            resp = await client.post(f"/api/v1/products/{product.id}/ocean/trigger")
        assert resp.status_code == 202, f"Expected 202 for status={status_val}, got {resp.status_code}"


@pytest.mark.asyncio
async def test_get_user_ocean_score_endpoint_200(ocean_api_client):
    client, mock_db, company = ocean_api_client
    product = _fake_product(company.id)
    user_id = uuid.uuid4()
    score_id = uuid.uuid4()

    fake_score = MagicMock()
    fake_score.id = score_id
    fake_score.user_id = user_id
    fake_score.openness = 75.0
    fake_score.conscientiousness = 68.0
    fake_score.extraversion = 45.0
    fake_score.agreeableness = 72.0
    fake_score.neuroticism = 28.0
    fake_score.confidence = 74.0
    fake_score.scoring_method = "llm"
    fake_score.reasoning = {
        "openness": "Curious user",
        "conscientiousness": "Methodical",
        "extraversion": "Introverted",
        "agreeableness": "Empathetic",
        "neuroticism": "Stable",
    }
    fake_score.created_at = datetime.now(timezone.utc)
    fake_score.updated_at = datetime.now(timezone.utc)

    with patch("app.routers.ocean.get_product_by_id", return_value=product), \
         patch("app.routers.ocean.get_user_ocean_score", return_value=fake_score):
        resp = await client.get(
            f"/api/v1/products/{product.id}/discovery/users/{user_id}/ocean"
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["openness"] == 75.0
    assert data["neuroticism"] == 28.0
    assert data["scoring_method"] == "llm"
    assert data["reasoning"]["openness"] == "Curious user"


@pytest.mark.asyncio
async def test_get_user_ocean_score_404_not_computed(ocean_api_client):
    client, mock_db, company = ocean_api_client
    product = _fake_product(company.id)
    user_id = uuid.uuid4()

    with patch("app.routers.ocean.get_product_by_id", return_value=product), \
         patch("app.routers.ocean.get_user_ocean_score", return_value=None):
        resp = await client.get(
            f"/api/v1/products/{product.id}/discovery/users/{user_id}/ocean"
        )

    assert resp.status_code == 404
    assert "OCEAN scores not yet computed" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_get_user_ocean_score_404_product_not_found(ocean_api_client):
    client, mock_db, company = ocean_api_client
    user_id = uuid.uuid4()

    with patch("app.routers.ocean.get_product_by_id", return_value=None):
        resp = await client.get(
            f"/api/v1/products/{uuid.uuid4()}/discovery/users/{user_id}/ocean"
        )

    assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# 6. EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    def test_all_negative_emotion_user_high_neuroticism(self):
        """User who writes only about negative emotions → high neuroticism."""
        empath = {
            "negative_emotion": 0.25, "anxiety": 0.2, "anger": 0.18,
            "sadness": 0.15, "fear": 0.12,
        }
        result = compute_heuristic_scores(empath, total_tokens=300)
        assert result["neuroticism"] > 70

    def test_positive_user_low_neuroticism(self):
        """User who writes only about positive topics → neutral/low neuroticism."""
        empath = {"joy": 0.2, "positive_emotion": 0.18, "affection": 0.15}
        result = compute_heuristic_scores(empath, total_tokens=300)
        # No neuroticism signal → should stay at 50 (neutral baseline)
        assert result["neuroticism"] == 50.0

    def test_highly_creative_user_high_openness(self):
        empath = {"art": 0.22, "creativity": 0.18, "music": 0.15, "imagination": 0.12}
        result = compute_heuristic_scores(empath, total_tokens=300)
        assert result["openness"] > 70

    def test_prompt_handles_empty_inputs_gracefully(self):
        """build_ocean_prompt should not crash on empty inputs."""
        prompt = build_ocean_prompt(
            interest_tags=[],
            empath_scores={},
            keyword_frequency={},
            vocabulary_richness=0.0,
            avg_sentence_length=0.0,
            total_tokens=0,
        )
        assert isinstance(prompt, str)
        assert len(prompt) > 50

    def test_parse_response_handles_float_string_scores(self):
        """LLM sometimes returns "75.0" as string → should be parsed."""
        raw = '{"openness":"75.0","conscientiousness":60,"extraversion":45,"agreeableness":70,"neuroticism":30,"confidence":68,"reasoning":{}}'
        result = parse_ocean_response(raw)
        # "75.0" as string → _clamp("75.0") should handle float("75.0") = 75.0
        assert result is not None
        assert result["openness"] == 75.0

    def test_parse_response_handles_integer_confidence(self):
        raw = '{"openness":75,"conscientiousness":60,"extraversion":45,"agreeableness":70,"neuroticism":30,"confidence":72,"reasoning":{}}'
        result = parse_ocean_response(raw)
        assert result["confidence"] == 72.0

    def test_heuristic_score_unknown_empath_categories_ignored(self):
        """Unknown Empath categories should not affect scores."""
        empath = {"unknown_category_xyz": 0.9, "another_unknown": 0.8}
        result = compute_heuristic_scores(empath, total_tokens=100)
        for dim in ("openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism"):
            assert result[dim] == 50.0  # no known signals → neutral

    def test_migration_columns_match_model(self):
        """Verify UserOceanScore has all expected columns."""
        from app.models.ocean import UserOceanScore as OceanModel

        columns = {col.name for col in OceanModel.__table__.columns}
        expected = {
            "id", "user_id", "openness", "conscientiousness", "extraversion",
            "agreeableness", "neuroticism", "confidence", "scoring_method",
            "reasoning", "raw_llm_response", "created_at", "updated_at",
        }
        assert expected.issubset(columns), f"Missing columns: {expected - columns}"

    def test_model_unique_constraint_on_user_id(self):
        """user_ocean_scores must have a unique constraint on user_id."""
        from app.models.ocean import UserOceanScore as OceanModel
        constraint_names = {uc.name for uc in OceanModel.__table__.constraints}
        assert "uq_user_ocean_score" in constraint_names

    @pytest.mark.asyncio
    async def test_background_task_marks_product_failed_on_error(self):
        """start_ocean_background marks product as failed when run_ocean_for_product raises."""
        from app.services.ocean_service import start_ocean_background
        product_id = str(uuid.uuid4())
        mock_product = MagicMock(spec=Product)
        mock_product.status = ProductStatus.nlp_processing
        mock_product.pipeline_step = 5

        async def fake_session():
            db = AsyncMock()
            db.get.return_value = mock_product
            return db

        with patch("app.services.ocean_service.AsyncSessionLocal") as MockSession, \
             patch("app.services.ocean_service.run_ocean_for_product") as mock_run:
            mock_run.side_effect = RuntimeError("DB exploded")
            mock_db = AsyncMock()
            mock_db.get.return_value = mock_product
            MockSession.return_value.__aenter__.return_value = mock_db
            MockSession.return_value.__aexit__.return_value = False

            await start_ocean_background(product_id)

        assert mock_product.status == ProductStatus.failed
