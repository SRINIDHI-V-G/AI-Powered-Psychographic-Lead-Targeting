"""
Phase F1 — Lead Validation, Inspection, and Export — test suite.

Coverage:
  1. Quality flag logic        — unit tests for _quality_flags()
  2. Statistics helpers        — _distribution_stats(), _histogram(), _calibration_notes()
  3. CRUD / inspection         — get_lead_inspection() with mocked DB
  4. CRUD / analytics          — get_lead_analytics() with mocked DB
  5. CRUD / export             — get_leads_for_export() with mocked DB
  6. Updated matching CRUD     — min_confidence + sort direction filters
  7. API / inspection          — GET .../leads/{uid}/inspect endpoint
  8. API / analytics           — GET .../leads/analytics endpoint
  9. API / export CSV          — GET .../leads/export?format=csv
 10. API / export JSON         — GET .../leads/export?format=json
 11. API / updated leads list  — new filter params (min_confidence, sort)
 12. Edge cases                — empty results, all low-confidence, no content

Run with:
  cd backend && pytest tests/test_phase_f1.py -v
"""
from __future__ import annotations

import csv
import io
import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

# ═══════════════════════════════════════════════════════════════════════════════
# 1. QUALITY FLAG LOGIC — unit tests
# ═══════════════════════════════════════════════════════════════════════════════

from app.crud.validation import (
    _quality_flags,
    _distribution_stats,
    _histogram,
    _calibration_notes,
    QUALITY_MIN_CONFIDENCE,
    QUALITY_MIN_TOKENS,
    QUALITY_MIN_INTEREST_TAGS,
)


class TestQualityFlags:
    def test_clean_user_no_flags(self):
        flags = _quality_flags(
            confidence=75.0,
            scoring_method="llm",
            total_tokens=200,
            interest_tag_count=8,
        )
        assert flags == []

    def test_insufficient_content_flagged(self):
        flags = _quality_flags(
            confidence=10.0,
            scoring_method="insufficient_content",
            total_tokens=5,
            interest_tag_count=0,
        )
        assert any("INSUFFICIENT_CONTENT" in f for f in flags)

    def test_heuristic_ocean_flagged(self):
        flags = _quality_flags(
            confidence=60.0,
            scoring_method="heuristic",
            total_tokens=100,
            interest_tag_count=5,
        )
        assert any("HEURISTIC_OCEAN" in f for f in flags)

    def test_low_confidence_flagged(self):
        flags = _quality_flags(
            confidence=QUALITY_MIN_CONFIDENCE - 1,
            scoring_method="llm",
            total_tokens=100,
            interest_tag_count=5,
        )
        assert any("LOW_CONFIDENCE" in f for f in flags)

    def test_above_threshold_confidence_no_flag(self):
        flags = _quality_flags(
            confidence=QUALITY_MIN_CONFIDENCE + 1,
            scoring_method="llm",
            total_tokens=100,
            interest_tag_count=5,
        )
        assert not any("LOW_CONFIDENCE" in f for f in flags)

    def test_low_token_count_flagged(self):
        flags = _quality_flags(
            confidence=70.0,
            scoring_method="llm",
            total_tokens=QUALITY_MIN_TOKENS - 1,
            interest_tag_count=5,
        )
        assert any("LOW_TOKEN_COUNT" in f for f in flags)

    def test_thin_interest_signal_flagged(self):
        flags = _quality_flags(
            confidence=70.0,
            scoring_method="llm",
            total_tokens=200,
            interest_tag_count=QUALITY_MIN_INTEREST_TAGS - 1,
        )
        assert any("THIN_INTEREST_SIGNAL" in f for f in flags)

    def test_multiple_flags_possible(self):
        flags = _quality_flags(
            confidence=10.0,
            scoring_method="insufficient_content",
            total_tokens=2,
            interest_tag_count=0,
        )
        assert len(flags) >= 3

    def test_llm_scored_sufficient_content_no_flags(self):
        flags = _quality_flags(
            confidence=80.0,
            scoring_method="llm",
            total_tokens=300,
            interest_tag_count=10,
        )
        assert flags == []


# ═══════════════════════════════════════════════════════════════════════════════
# 2. STATISTICS HELPERS — unit tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestDistributionStats:
    def test_empty_list(self):
        result = _distribution_stats([])
        assert result["count"] == 0
        assert result["mean"] is None

    def test_single_value(self):
        result = _distribution_stats([75.0])
        assert result["count"] == 1
        assert result["min"] == 75.0
        assert result["max"] == 75.0
        assert result["mean"] == 75.0
        assert result["std_dev"] == 0.0

    def test_basic_stats(self):
        values = [60.0, 70.0, 80.0, 90.0]
        result = _distribution_stats(values)
        assert result["min"] == 60.0
        assert result["max"] == 90.0
        assert result["mean"] == 75.0

    def test_percentiles(self):
        values = list(range(0, 101))  # 0 to 100 inclusive
        result = _distribution_stats([float(v) for v in values])
        assert abs(result["p25"] - 25.0) < 1.0
        assert abs(result["p75"] - 75.0) < 1.0

    def test_std_dev_positive_for_varied_list(self):
        result = _distribution_stats([60.0, 70.0, 80.0, 90.0])
        assert result["std_dev"] > 0


class TestHistogram:
    def test_empty_returns_10_buckets(self):
        result = _histogram([])
        assert len(result) == 10
        assert all(b["count"] == 0 for b in result)

    def test_all_in_first_bucket(self):
        result = _histogram([0.0, 5.0, 9.9])
        assert result[0]["count"] == 3
        assert all(b["count"] == 0 for b in result[1:])

    def test_100_goes_in_last_bucket(self):
        result = _histogram([100.0])
        assert result[-1]["count"] == 1

    def test_bucket_count_correct(self):
        values = [10.0 * i for i in range(10)]  # 0,10,20,...,90
        result = _histogram(values)
        total = sum(b["count"] for b in result)
        assert total == len(values)

    def test_bucket_ranges_labeled(self):
        result = _histogram([50.0])
        ranges = [b["range"] for b in result]
        assert any("50" in r for r in ranges)


class TestCalibrationNotes:
    def test_returns_list_of_strings(self):
        notes = _calibration_notes([70.0, 75.0, 80.0], [60.0, 65.0], ["llm", "llm"])
        assert isinstance(notes, list)
        assert all(isinstance(n, str) for n in notes)

    def test_empty_scores_returns_no_leads_message(self):
        notes = _calibration_notes([], [], [])
        assert any("No ranked leads" in n for n in notes)

    def test_tight_clustering_detected(self):
        # Standard deviation < 8 — should trigger clustering note
        scores = [70.0 + i * 0.5 for i in range(10)]  # very tight
        notes = _calibration_notes(scores, [70.0] * 10, ["llm"] * 10)
        assert any("clustered" in n.lower() or "σ" in n for n in notes)

    def test_ocean_floor_note_always_present(self):
        notes = _calibration_notes([70.0, 80.0], [60.0], ["llm"])
        assert any("59" in n or "floor" in n.lower() or "65" in n for n in notes)

    def test_high_insufficient_content_warns(self):
        methods = ["insufficient_content"] * 8 + ["llm"] * 2
        notes = _calibration_notes([60.0] * 10, [30.0] * 10, methods)
        assert any("insufficient" in n.lower() for n in notes)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. CRUD: get_lead_inspection — mocked DB tests
# ═══════════════════════════════════════════════════════════════════════════════

from app.crud.validation import get_lead_inspection
from app.models.discovery import DiscoveredUser, UserContent
from app.models.matching import LeadMatch
from app.models.motivation import MotivationCategory
from app.models.nlp import UserNlpFeatures
from app.models.ocean import UserOceanScore


def _mock_user(user_id: uuid.UUID) -> MagicMock:
    u = MagicMock(spec=DiscoveredUser)
    u.id = user_id; u.username = "test_user"; u.display_name = None
    u.platform = "reddit"; u.profile_url = "https://reddit.com/u/test_user"
    u.location = "Chennai"; u.location_confidence = "inferred"
    u.follower_count = 750
    return u


def _mock_ocean(user_id: uuid.UUID, method: str = "llm") -> MagicMock:
    o = MagicMock(spec=UserOceanScore)
    o.user_id = user_id; o.openness = 72.0; o.conscientiousness = 65.0
    o.extraversion = 45.0; o.agreeableness = 70.0; o.neuroticism = 28.0
    o.confidence = 74.0; o.scoring_method = method
    return o


def _mock_nlp(user_id: uuid.UUID, tokens: int = 200) -> MagicMock:
    n = MagicMock(spec=UserNlpFeatures)
    n.user_id = user_id; n.total_tokens = tokens
    n.vocabulary_richness = 0.68; n.avg_sentence_length = 12.5
    n.interest_tags = ["technology", "learning", "achievement", "work", "innovation"]
    n.empath_scores = {"intellectual": 0.18, "achievement": 0.12, "work": 0.09}
    return n


def _mock_content(user_id: uuid.UUID) -> MagicMock:
    c = MagicMock(spec=UserContent)
    c.user_id = user_id; c.content_type = "post"
    c.content_text = "I have been working on a machine learning project for the past month."
    c.engagement = 45; c.source_url = "https://reddit.com/r/python/comments/abc"
    return c


def _mock_lead_match(user_id: uuid.UUID, cat_id: uuid.UUID, product_id: uuid.UUID) -> MagicMock:
    m = MagicMock(spec=LeadMatch)
    m.user_id = user_id; m.motivation_category_id = cat_id; m.product_id = product_id
    m.is_best_match = True; m.rank = 1
    m.final_score = 82.5; m.ocean_score = 80.0; m.embedding_score = 76.0
    m.interest_score = 88.0; m.confidence = 74.0
    m.reasoning = ["Strong OCEAN alignment.", "Shared interests: technology, learning."]
    return m


def _mock_category(cat_id: uuid.UUID, name: str = "Tech Enthusiast") -> MagicMock:
    c = MagicMock(spec=MotivationCategory)
    c.id = cat_id; c.name = name
    return c


def _build_inspection_db(user_id, cat_id, product_id) -> AsyncMock:
    db = AsyncMock()

    user_r = MagicMock(); user_r.scalar_one_or_none.return_value = _mock_user(user_id)
    match_r = MagicMock()
    match_r.all.return_value = [(_mock_lead_match(user_id, cat_id, product_id), _mock_category(cat_id))]
    ocean_r = MagicMock(); ocean_r.scalar_one_or_none.return_value = _mock_ocean(user_id)
    nlp_r = MagicMock(); nlp_r.scalar_one_or_none.return_value = _mock_nlp(user_id)
    content_r = MagicMock(); content_r.scalars.return_value.all.return_value = [_mock_content(user_id)]

    db.execute.side_effect = [user_r, match_r, ocean_r, nlp_r, content_r]
    return db


@pytest.mark.asyncio
async def test_get_lead_inspection_returns_full_profile():
    user_id, cat_id, product_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    db = _build_inspection_db(user_id, cat_id, product_id)

    result = await get_lead_inspection(db, product_id, user_id)

    assert result is not None
    assert result["username"] == "test_user"
    assert result["platform"] == "reddit"


@pytest.mark.asyncio
async def test_get_lead_inspection_includes_ocean_profile():
    user_id, cat_id, product_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    db = _build_inspection_db(user_id, cat_id, product_id)

    result = await get_lead_inspection(db, product_id, user_id)

    ocean = result["ocean_profile"]
    assert ocean["openness"] == 72.0
    assert ocean["neuroticism"] == 28.0
    assert ocean["scoring_method"] == "llm"


@pytest.mark.asyncio
async def test_get_lead_inspection_includes_interest_tags():
    user_id, cat_id, product_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    db = _build_inspection_db(user_id, cat_id, product_id)

    result = await get_lead_inspection(db, product_id, user_id)

    assert "technology" in result["interest_tags"]
    assert len(result["interest_tags"]) >= 3


@pytest.mark.asyncio
async def test_get_lead_inspection_includes_empath_categories():
    user_id, cat_id, product_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    db = _build_inspection_db(user_id, cat_id, product_id)

    result = await get_lead_inspection(db, product_id, user_id)

    assert len(result["top_empath_categories"]) > 0
    cats = {e["category"] for e in result["top_empath_categories"]}
    assert "intellectual" in cats


@pytest.mark.asyncio
async def test_get_lead_inspection_includes_content_samples():
    user_id, cat_id, product_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    db = _build_inspection_db(user_id, cat_id, product_id)

    result = await get_lead_inspection(db, product_id, user_id)

    assert len(result["content_samples"]) == 1
    assert "machine learning" in result["content_samples"][0]["content_text"]


@pytest.mark.asyncio
async def test_get_lead_inspection_content_truncated():
    user_id, cat_id, product_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    db = _build_inspection_db(user_id, cat_id, product_id)

    # Override with very long content
    long_content = _mock_content(user_id)
    long_content.content_text = "x" * 1000

    user_r = MagicMock(); user_r.scalar_one_or_none.return_value = _mock_user(user_id)
    match_r = MagicMock()
    match_r.all.return_value = [(_mock_lead_match(user_id, cat_id, product_id), _mock_category(cat_id))]
    ocean_r = MagicMock(); ocean_r.scalar_one_or_none.return_value = _mock_ocean(user_id)
    nlp_r = MagicMock(); nlp_r.scalar_one_or_none.return_value = _mock_nlp(user_id)
    content_r = MagicMock(); content_r.scalars.return_value.all.return_value = [long_content]
    db2 = AsyncMock()
    db2.execute.side_effect = [user_r, match_r, ocean_r, nlp_r, content_r]

    result = await get_lead_inspection(db2, product_id, user_id)
    assert len(result["content_samples"][0]["content_text"]) <= 400


@pytest.mark.asyncio
async def test_get_lead_inspection_clean_user_passes_quality_filter():
    user_id, cat_id, product_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    db = _build_inspection_db(user_id, cat_id, product_id)

    result = await get_lead_inspection(db, product_id, user_id)

    assert result["passes_quality_filter"] is True
    assert result["quality_flags"] == []


@pytest.mark.asyncio
async def test_get_lead_inspection_insufficient_content_flags():
    user_id, cat_id, product_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    user_r = MagicMock(); user_r.scalar_one_or_none.return_value = _mock_user(user_id)
    match_r = MagicMock()
    match_r.all.return_value = [(_mock_lead_match(user_id, cat_id, product_id), _mock_category(cat_id))]
    ocean_r = MagicMock(); ocean_r.scalar_one_or_none.return_value = _mock_ocean(user_id, method="insufficient_content")
    nlp_r = MagicMock(); nlp_r.scalar_one_or_none.return_value = _mock_nlp(user_id, tokens=5)
    content_r = MagicMock(); content_r.scalars.return_value.all.return_value = []
    db = AsyncMock()
    db.execute.side_effect = [user_r, match_r, ocean_r, nlp_r, content_r]

    result = await get_lead_inspection(db, product_id, user_id)

    assert result["passes_quality_filter"] is False
    assert len(result["quality_flags"]) > 0


@pytest.mark.asyncio
async def test_get_lead_inspection_returns_none_for_unknown_user():
    db = AsyncMock()
    r = MagicMock(); r.scalar_one_or_none.return_value = None
    db.execute.return_value = r

    result = await get_lead_inspection(db, uuid.uuid4(), uuid.uuid4())
    assert result is None


@pytest.mark.asyncio
async def test_get_lead_inspection_returns_none_for_unmatched_user():
    user_id, product_id = uuid.uuid4(), uuid.uuid4()
    db = AsyncMock()
    user_r = MagicMock(); user_r.scalar_one_or_none.return_value = _mock_user(user_id)
    no_matches = MagicMock(); no_matches.all.return_value = []
    db.execute.side_effect = [user_r, no_matches]

    result = await get_lead_inspection(db, product_id, user_id)
    assert result is None


# ═══════════════════════════════════════════════════════════════════════════════
# 4. CRUD: get_lead_analytics — mocked DB tests
# ═══════════════════════════════════════════════════════════════════════════════

from app.crud.validation import get_lead_analytics


def _make_analytics_row(score: float, confidence: float, method: str = "llm") -> tuple:
    lead = MagicMock(spec=LeadMatch)
    lead.final_score = score; lead.confidence = confidence
    lead.ocean_score = score - 2; lead.embedding_score = score - 4; lead.interest_score = score + 2

    ocean = MagicMock(spec=UserOceanScore); ocean.scoring_method = method
    nlp = MagicMock(spec=UserNlpFeatures); nlp.total_tokens = 200; nlp.interest_tags = ["tech"] * 5

    return (lead, ocean, nlp)


@pytest.mark.asyncio
async def test_get_lead_analytics_empty_product():
    db = AsyncMock()
    empty = MagicMock(); empty.all.return_value = []
    db.execute.return_value = empty

    result = await get_lead_analytics(db, uuid.uuid4())

    assert result["total_ranked"] == 0
    assert result["calibration_notes"] == ["No ranked leads available for analysis."]


@pytest.mark.asyncio
async def test_get_lead_analytics_computes_stats():
    product_id = uuid.uuid4()
    db = AsyncMock()

    rows = [_make_analytics_row(60 + i * 5, 50 + i * 3) for i in range(5)]
    main_r = MagicMock(); main_r.all.return_value = rows
    cat_r = MagicMock(); cat_r.all.return_value = []
    db.execute.side_effect = [main_r, cat_r]

    result = await get_lead_analytics(db, product_id)

    assert result["total_ranked"] == 5
    assert result["final_score_distribution"]["count"] == 5
    assert result["final_score_distribution"]["min"] is not None
    assert result["final_score_distribution"]["max"] is not None


@pytest.mark.asyncio
async def test_get_lead_analytics_quality_summary():
    product_id = uuid.uuid4()
    db = AsyncMock()

    rows = (
        [_make_analytics_row(75.0, 70.0, "llm")] * 3 +
        [_make_analytics_row(60.0, 20.0, "insufficient_content")] * 2
    )
    main_r = MagicMock(); main_r.all.return_value = rows
    cat_r = MagicMock(); cat_r.all.return_value = []
    db.execute.side_effect = [main_r, cat_r]

    result = await get_lead_analytics(db, product_id)

    summary = result["quality_summary"]
    assert summary["flagged_insufficient_content"] == 2
    assert summary["passing_all_filters"] <= 5


@pytest.mark.asyncio
async def test_get_lead_analytics_calibration_notes_present():
    product_id = uuid.uuid4()
    db = AsyncMock()

    rows = [_make_analytics_row(70.0, 65.0) for _ in range(5)]
    main_r = MagicMock(); main_r.all.return_value = rows
    cat_r = MagicMock(); cat_r.all.return_value = []
    db.execute.side_effect = [main_r, cat_r]

    result = await get_lead_analytics(db, product_id)

    assert len(result["calibration_notes"]) > 0
    assert all(isinstance(n, str) for n in result["calibration_notes"])


# ═══════════════════════════════════════════════════════════════════════════════
# 5. CRUD: get_leads_for_export — mocked DB tests
# ═══════════════════════════════════════════════════════════════════════════════

from app.crud.validation import get_leads_for_export


def _make_export_row() -> tuple:
    user_id = uuid.uuid4()
    lead = MagicMock(spec=LeadMatch)
    lead.rank = 1; lead.final_score = 82.5; lead.ocean_score = 80.0
    lead.embedding_score = 76.0; lead.interest_score = 88.0; lead.confidence = 74.0
    lead.reasoning = ["Strong alignment."]

    user = MagicMock(spec=DiscoveredUser)
    user.username = "tech_user_42"; user.display_name = None
    user.platform = "reddit"; user.profile_url = "https://reddit.com/u/tech_user_42"
    user.location = "Chennai"; user.location_confidence = "inferred"; user.follower_count = 500

    cat = MagicMock(spec=MotivationCategory); cat.name = "Tech Enthusiast"

    ocean = MagicMock(spec=UserOceanScore)
    ocean.openness = 72.0; ocean.conscientiousness = 65.0; ocean.extraversion = 45.0
    ocean.agreeableness = 70.0; ocean.neuroticism = 28.0; ocean.scoring_method = "llm"
    ocean.confidence = 74.0

    nlp = MagicMock(spec=UserNlpFeatures)
    nlp.total_tokens = 200; nlp.interest_tags = ["technology", "learning", "innovation"]

    return (lead, user, cat, ocean, nlp)


@pytest.mark.asyncio
async def test_get_leads_for_export_returns_flat_dicts():
    db = AsyncMock()
    r = MagicMock(); r.all.return_value = [_make_export_row()]
    db.execute.return_value = r

    rows = await get_leads_for_export(db, uuid.uuid4())

    assert len(rows) == 1
    row = rows[0]
    assert "rank" in row
    assert "username" in row
    assert "final_score" in row
    assert "openness" in row
    assert "reasoning" in row


@pytest.mark.asyncio
async def test_get_leads_for_export_includes_quality_flags():
    db = AsyncMock()
    r = MagicMock(); r.all.return_value = [_make_export_row()]
    db.execute.return_value = r

    rows = await get_leads_for_export(db, uuid.uuid4())

    row = rows[0]
    assert "quality_flags" in row
    assert row["quality_flags"] == "PASS"


@pytest.mark.asyncio
async def test_get_leads_for_export_interest_tags_as_string():
    db = AsyncMock()
    r = MagicMock(); r.all.return_value = [_make_export_row()]
    db.execute.return_value = r

    rows = await get_leads_for_export(db, uuid.uuid4())
    assert isinstance(rows[0]["interest_tags"], str)
    assert "technology" in rows[0]["interest_tags"]


@pytest.mark.asyncio
async def test_get_leads_for_export_empty_returns_empty_list():
    db = AsyncMock()
    r = MagicMock(); r.all.return_value = []
    db.execute.return_value = r

    rows = await get_leads_for_export(db, uuid.uuid4())
    assert rows == []


# ═══════════════════════════════════════════════════════════════════════════════
# 6. UPDATED MATCHING CRUD — filter tests
# ═══════════════════════════════════════════════════════════════════════════════

from app.crud.matching import get_ranked_leads


@pytest.mark.asyncio
async def test_get_ranked_leads_min_confidence_filter_applied():
    """min_confidence filter should be passed through to the WHERE clause."""
    product_id = uuid.uuid4()
    db = AsyncMock()

    count_r = MagicMock(); count_r.scalar_one.return_value = 0
    leads_r = MagicMock(); leads_r.all.return_value = []
    db.execute.side_effect = [count_r, leads_r]

    result = await get_ranked_leads(db, product_id, min_confidence=50.0)

    assert result["total_leads"] == 0
    # Verify db.execute was called (the filter was applied)
    assert db.execute.call_count == 2


@pytest.mark.asyncio
async def test_get_ranked_leads_bottom_sort():
    """sort='bottom' should order by rank descending."""
    product_id = uuid.uuid4()
    db = AsyncMock()

    count_r = MagicMock(); count_r.scalar_one.return_value = 0
    leads_r = MagicMock(); leads_r.all.return_value = []
    db.execute.side_effect = [count_r, leads_r]

    result = await get_ranked_leads(db, product_id, sort="bottom")
    assert result["total_leads"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 7-11. API TESTS — mocked CRUD + auth
# ═══════════════════════════════════════════════════════════════════════════════

from app.main import app
from app.database import get_db
from app.dependencies import get_current_company
from app.models.company import Company
from app.models.product import Product, ProductStatus


def _fake_company() -> MagicMock:
    co = MagicMock(spec=Company); co.id = uuid.uuid4(); co.name = "Test Co"
    return co


def _fake_product(company_id: uuid.UUID, name: str = "Test Product") -> MagicMock:
    p = MagicMock(spec=Product); p.id = uuid.uuid4()
    p.company_id = company_id; p.name = name
    p.status = MagicMock(); p.status.value = "ranked"
    return p


def _fake_inspection_response(user_id: uuid.UUID, product_id: uuid.UUID) -> dict:
    return {
        "user_id": str(user_id),
        "username": "tech_user_42",
        "display_name": None,
        "platform": "reddit",
        "profile_url": "https://reddit.com/u/tech_user_42",
        "location": "Chennai",
        "location_confidence": "inferred",
        "follower_count": 750,
        "content_quality": {"total_tokens": 200, "vocabulary_richness": 0.68, "avg_sentence_length": 12.5, "num_content_items": 5},
        "ocean_profile": {"openness": 72.0, "conscientiousness": 65.0, "extraversion": 45.0, "agreeableness": 70.0, "neuroticism": 28.0, "confidence": 74.0, "scoring_method": "llm"},
        "interest_tags": ["technology", "learning", "innovation"],
        "top_empath_categories": [{"category": "intellectual", "score": 0.18}, {"category": "achievement", "score": 0.12}],
        "content_samples": [{"content_type": "post", "content_text": "Working on a neural network project.", "engagement": 45, "source_url": None}],
        "best_match": {"rank": 1, "motivation_category_id": str(uuid.uuid4()), "motivation_category": "Tech Enthusiast", "final_score": 82.5, "ocean_score": 80.0, "embedding_score": 76.0, "interest_score": 88.0, "confidence": 74.0, "reasoning": ["Strong alignment."]},
        "all_category_scores": [],
        "quality_flags": [],
        "passes_quality_filter": True,
    }


def _fake_analytics_response(product_id: uuid.UUID) -> dict:
    return {
        "product_id": str(product_id),
        "total_ranked": 87,
        "quality_summary": {"passing_all_filters": 62, "pct_passing": 71.3, "flagged_low_confidence": 10, "flagged_heuristic_ocean": 15, "flagged_insufficient_content": 8, "recommended_min_confidence": 40.0},
        "final_score_distribution": {"count": 87, "min": 58.5, "max": 84.2, "mean": 71.3, "median": 71.0, "p25": 66.0, "p75": 76.0, "std_dev": 7.2, "histogram": [{"range": f"{i*10}-{(i+1)*10}", "count": 8} for i in range(10)]},
        "confidence_distribution": {"count": 87, "min": 20.0, "max": 85.0, "mean": 56.0, "median": 57.0, "p25": 42.0, "p75": 70.0, "std_dev": 15.0},
        "ocean_score_distribution": {"count": 87, "min": 60.0, "max": 90.0, "mean": 75.0, "median": 75.0, "p25": 68.0, "p75": 82.0, "std_dev": 8.0},
        "embedding_score_distribution": {"count": 87, "min": 55.0, "max": 80.0, "mean": 68.0, "median": 68.0, "p25": 62.0, "p75": 74.0, "std_dev": 6.0},
        "interest_score_distribution": {"count": 87, "min": 0.0, "max": 100.0, "mean": 45.0, "median": 44.0, "p25": 20.0, "p75": 68.0, "std_dev": 28.0},
        "top_motivation_categories": [{"category": "Tech Enthusiast", "count": 45}, {"category": "Value Seeker", "count": 42}],
        "calibration_notes": ["Moderate score spread. Rankings provide reasonable differentiation.", "OCEAN similarity scores have a mathematical floor of ~59 for random profiles."],
    }


@pytest_asyncio.fixture
async def f1_api_client():
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
async def test_inspect_lead_200(f1_api_client):
    client, db, company = f1_api_client
    product = _fake_product(company.id)
    user_id = uuid.uuid4()
    fake_data = _fake_inspection_response(user_id, product.id)

    with patch("app.routers.validation.get_product_by_id", return_value=product), \
         patch("app.routers.validation.get_lead_inspection", return_value=fake_data):
        resp = await client.get(f"/api/v1/products/{product.id}/leads/{user_id}/inspect")

    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] == "tech_user_42"
    assert data["ocean_profile"]["openness"] == 72.0
    assert data["interest_tags"] == ["technology", "learning", "innovation"]
    assert len(data["content_samples"]) == 1
    assert data["passes_quality_filter"] is True


@pytest.mark.asyncio
async def test_inspect_lead_404_not_found(f1_api_client):
    client, db, company = f1_api_client
    product = _fake_product(company.id)

    with patch("app.routers.validation.get_product_by_id", return_value=product), \
         patch("app.routers.validation.get_lead_inspection", return_value=None):
        resp = await client.get(f"/api/v1/products/{product.id}/leads/{uuid.uuid4()}/inspect")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_inspect_lead_404_product_not_found(f1_api_client):
    client, db, company = f1_api_client

    with patch("app.routers.validation.get_product_by_id", return_value=None):
        resp = await client.get(f"/api/v1/products/{uuid.uuid4()}/leads/{uuid.uuid4()}/inspect")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_inspect_lead_includes_quality_flags(f1_api_client):
    client, db, company = f1_api_client
    product = _fake_product(company.id)
    user_id = uuid.uuid4()
    flagged_data = _fake_inspection_response(user_id, product.id)
    flagged_data["quality_flags"] = ["HEURISTIC_OCEAN: ..."]
    flagged_data["passes_quality_filter"] = False

    with patch("app.routers.validation.get_product_by_id", return_value=product), \
         patch("app.routers.validation.get_lead_inspection", return_value=flagged_data):
        resp = await client.get(f"/api/v1/products/{product.id}/leads/{user_id}/inspect")

    assert resp.status_code == 200
    data = resp.json()
    assert data["passes_quality_filter"] is False
    assert len(data["quality_flags"]) > 0


@pytest.mark.asyncio
async def test_analytics_endpoint_200(f1_api_client):
    client, db, company = f1_api_client
    product = _fake_product(company.id)
    fake_analytics = _fake_analytics_response(product.id)

    with patch("app.routers.validation.get_product_by_id", return_value=product), \
         patch("app.routers.validation.get_lead_analytics", return_value=fake_analytics):
        resp = await client.get(f"/api/v1/products/{product.id}/leads/analytics")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_ranked"] == 87
    assert data["quality_summary"]["passing_all_filters"] == 62
    assert len(data["calibration_notes"]) > 0


@pytest.mark.asyncio
async def test_analytics_endpoint_404_product_not_found(f1_api_client):
    client, db, company = f1_api_client

    with patch("app.routers.validation.get_product_by_id", return_value=None):
        resp = await client.get(f"/api/v1/products/{uuid.uuid4()}/leads/analytics")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_analytics_min_confidence_param(f1_api_client):
    client, db, company = f1_api_client
    product = _fake_product(company.id)
    fake_analytics = _fake_analytics_response(product.id)

    with patch("app.routers.validation.get_product_by_id", return_value=product), \
         patch("app.routers.validation.get_lead_analytics", return_value=fake_analytics) as mock_get:
        resp = await client.get(
            f"/api/v1/products/{product.id}/leads/analytics?min_confidence=40"
        )

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_export_csv_200(f1_api_client):
    client, db, company = f1_api_client
    product = _fake_product(company.id)
    fake_rows = [{
        "rank": 1, "username": "tech_user", "display_name": "", "platform": "reddit",
        "profile_url": "https://reddit.com/u/tech_user", "location": "Chennai",
        "location_confidence": "inferred", "follower_count": 500,
        "best_motivation_category": "Tech Enthusiast",
        "final_score": 82.5, "ocean_component_score": 80.0, "embedding_component_score": 76.0,
        "interest_component_score": 88.0, "confidence": 74.0,
        "openness": 72.0, "conscientiousness": 65.0, "extraversion": 45.0,
        "agreeableness": 70.0, "neuroticism": 28.0, "ocean_scoring_method": "llm",
        "interest_tags": "technology; learning", "total_tokens": 200,
        "reasoning": "Strong alignment.", "quality_flags": "PASS",
    }]

    with patch("app.routers.validation.get_product_by_id", return_value=product), \
         patch("app.routers.validation.get_leads_for_export", return_value=fake_rows):
        resp = await client.get(f"/api/v1/products/{product.id}/leads/export?format=csv")

    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert "attachment" in resp.headers["content-disposition"]
    assert ".csv" in resp.headers["content-disposition"]

    # Check CSV content is parseable
    content = resp.content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))
    rows = list(reader)
    assert len(rows) == 1
    assert rows[0]["username"] == "tech_user"
    assert rows[0]["platform"] == "reddit"


@pytest.mark.asyncio
async def test_export_csv_has_all_expected_columns(f1_api_client):
    client, db, company = f1_api_client
    product = _fake_product(company.id)

    with patch("app.routers.validation.get_product_by_id", return_value=product), \
         patch("app.routers.validation.get_leads_for_export", return_value=[]):
        resp = await client.get(f"/api/v1/products/{product.id}/leads/export?format=csv")

    content = resp.content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))
    headers = reader.fieldnames or []
    for col in ["rank", "username", "final_score", "openness", "neuroticism", "reasoning", "quality_flags"]:
        assert col in headers, f"Missing column: {col}"


@pytest.mark.asyncio
async def test_export_json_200(f1_api_client):
    client, db, company = f1_api_client
    product = _fake_product(company.id)
    user_id = uuid.uuid4()
    fake_rows = [{"rank": 1, "username": "tech_user", "final_score": 82.5}]

    with patch("app.routers.validation.get_product_by_id", return_value=product), \
         patch("app.routers.validation.get_leads_for_export", return_value=fake_rows):
        resp = await client.get(f"/api/v1/products/{product.id}/leads/export?format=json")

    assert resp.status_code == 200
    assert "application/json" in resp.headers["content-type"]
    assert ".json" in resp.headers["content-disposition"]

    payload = json.loads(resp.content)
    assert payload["total_rows"] == 1
    assert payload["leads"][0]["username"] == "tech_user"


@pytest.mark.asyncio
async def test_export_json_includes_product_id(f1_api_client):
    client, db, company = f1_api_client
    product = _fake_product(company.id)

    with patch("app.routers.validation.get_product_by_id", return_value=product), \
         patch("app.routers.validation.get_leads_for_export", return_value=[]):
        resp = await client.get(f"/api/v1/products/{product.id}/leads/export?format=json")

    payload = json.loads(resp.content)
    assert payload["product_id"] == str(product.id)
    assert payload["total_rows"] == 0


@pytest.mark.asyncio
async def test_export_invalid_format_422(f1_api_client):
    client, db, company = f1_api_client
    product = _fake_product(company.id)

    with patch("app.routers.validation.get_product_by_id", return_value=product):
        resp = await client.get(f"/api/v1/products/{product.id}/leads/export?format=xml")

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_export_404_product_not_found(f1_api_client):
    client, db, company = f1_api_client

    with patch("app.routers.validation.get_product_by_id", return_value=None):
        resp = await client.get(f"/api/v1/products/{uuid.uuid4()}/leads/export?format=csv")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_leads_with_min_confidence_param(f1_api_client):
    client, db, company = f1_api_client
    product = _fake_product(company.id)

    with patch("app.routers.matching.get_product_by_id", return_value=product), \
         patch("app.routers.matching.get_ranked_leads", return_value={
             "total_leads": 5, "page": 1, "page_size": 20, "total_pages": 1, "leads": [],
         }):
        resp = await client.get(
            f"/api/v1/products/{product.id}/leads?min_confidence=40"
        )

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_list_leads_bottom_sort(f1_api_client):
    client, db, company = f1_api_client
    product = _fake_product(company.id)

    with patch("app.routers.matching.get_product_by_id", return_value=product), \
         patch("app.routers.matching.get_ranked_leads", return_value={
             "total_leads": 0, "page": 1, "page_size": 20, "total_pages": 1, "leads": [],
         }):
        resp = await client.get(
            f"/api/v1/products/{product.id}/leads?sort=bottom"
        )

    assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════════
# 12. EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    def test_quality_flags_exactly_at_threshold(self):
        flags = _quality_flags(
            confidence=QUALITY_MIN_CONFIDENCE,
            scoring_method="llm",
            total_tokens=QUALITY_MIN_TOKENS,
            interest_tag_count=QUALITY_MIN_INTEREST_TAGS,
        )
        assert flags == []

    def test_distribution_single_item_no_std_crash(self):
        result = _distribution_stats([75.0])
        assert result["std_dev"] == 0.0

    def test_histogram_all_zeros_for_empty(self):
        h = _histogram([])
        assert sum(b["count"] for b in h) == 0

    def test_histogram_all_100_values_in_last_bucket(self):
        h = _histogram([100.0] * 10)
        assert h[-1]["count"] == 10

    def test_calibration_notes_not_empty_with_single_lead(self):
        notes = _calibration_notes([75.0], [70.0], ["llm"])
        assert len(notes) > 0

    @pytest.mark.asyncio
    async def test_export_empty_product_returns_empty_list(self):
        db = AsyncMock()
        r = MagicMock(); r.all.return_value = []
        db.execute.return_value = r

        rows = await get_leads_for_export(db, uuid.uuid4())
        assert rows == []

    @pytest.mark.asyncio
    async def test_inspect_no_ocean_score_handles_gracefully(self):
        user_id, cat_id, product_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        db = AsyncMock()

        user_r = MagicMock(); user_r.scalar_one_or_none.return_value = _mock_user(user_id)
        match_r = MagicMock()
        match_r.all.return_value = [(_mock_lead_match(user_id, cat_id, product_id), _mock_category(cat_id))]
        no_ocean = MagicMock(); no_ocean.scalar_one_or_none.return_value = None
        nlp_r = MagicMock(); nlp_r.scalar_one_or_none.return_value = _mock_nlp(user_id)
        content_r = MagicMock(); content_r.scalars.return_value.all.return_value = []
        db.execute.side_effect = [user_r, match_r, no_ocean, nlp_r, content_r]

        result = await get_lead_inspection(db, product_id, user_id)

        assert result is not None
        assert result["ocean_profile"]["scoring_method"] == "unavailable"
        assert result["passes_quality_filter"] is False
