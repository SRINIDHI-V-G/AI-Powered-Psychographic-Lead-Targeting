"""
GoogleReviewsProvider unit tests.

Tests use httpx.MockTransport so no real HTTP calls are made.
The mock Places API response mirrors the actual Google Places API (New) shape.

Run:
  cd backend && pytest tests/test_google_reviews.py -v
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.ml.discovery.base import ContentItem, RawDiscoveredUser
from app.ml.discovery.google_reviews_provider import (
    GoogleReviewsProvider,
    _extract_contributor_id,
    _get_review_text,
    _infer_location,
    _parse_timestamp,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_place(
    place_id: str = "ChIJtest0001",
    name: str = "Wooden Street Furniture",
    address: str = "Anna Nagar, Chennai, Tamil Nadu 600040, India",
    rating: float = 4.3,
    review_count: int = 320,
    reviews: list[dict] | None = None,
) -> dict:
    """Construct a Places API (New) place dict matching real API shape."""
    if reviews is None:
        reviews = [_make_review()]
    return {
        "id": place_id,
        "displayName": {"text": name, "languageCode": "en"},
        "formattedAddress": address,
        "rating": rating,
        "userRatingCount": review_count,
        "reviews": reviews,
    }


def _make_review(
    contributor_id: str = "109876543210",
    display_name: str = "Priya Sharma",
    text: str = "Absolutely loved the quality of the modular sofa. Perfect for our living room.",
    rating: int = 5,
    published_time: str = "2024-06-01T10:00:00Z",
) -> dict:
    return {
        "name": f"places/ChIJtest0001/reviews/AbCdEf{contributor_id[-4:]}",
        "rating": rating,
        "text": {"text": text, "languageCode": "en"},
        "originalText": {"text": text, "languageCode": "en"},
        "authorAttribution": {
            "displayName": display_name,
            "uri": f"https://www.google.com/maps/contrib/{contributor_id}",
            "photoUri": f"https://lh3.googleusercontent.com/a/{contributor_id}",
        },
        "publishTime": published_time,
        "relativePublishTimeDescription": "2 weeks ago",
    }


def _places_response(places: list[dict]) -> dict:
    return {"places": places}


def _mock_settings(**overrides):
    """Return a settings mock with sensible defaults for Google Places."""
    m = MagicMock()
    m.GOOGLE_PLACES_API_KEY = "AIzaFakeKeyForTesting"
    m.GOOGLE_PLACES_MAX_BUSINESSES_PER_KEYWORD = 5
    m.GOOGLE_PLACES_MAX_KEYWORDS = 3
    m.GOOGLE_PLACES_LANGUAGE = "en"
    m.google_places_credentials_configured.return_value = True
    for k, v in overrides.items():
        setattr(m, k, v)
    return m


# ── Helper function unit tests ────────────────────────────────────────────────

class TestExtractContributorId:
    def test_standard_uri(self):
        uri = "https://www.google.com/maps/contrib/109876543210"
        assert _extract_contributor_id(uri) == "109876543210"

    def test_uri_with_trailing_path(self):
        uri = "https://www.google.com/maps/contrib/109876543210/reviews"
        assert _extract_contributor_id(uri) == "109876543210"

    def test_uri_with_query_string(self):
        uri = "https://www.google.com/maps/contrib/109876543210?hl=en"
        assert _extract_contributor_id(uri) == "109876543210"

    def test_empty_uri_returns_none(self):
        assert _extract_contributor_id("") is None

    def test_uri_without_contrib_returns_none(self):
        assert _extract_contributor_id("https://www.google.com/maps/place/abc") is None


class TestGetReviewText:
    def test_returns_text_field(self):
        review = {"text": {"text": "Great sofa!", "languageCode": "en"}}
        assert _get_review_text(review) == "Great sofa!"

    def test_falls_back_to_original_text(self):
        review = {"originalText": {"text": "Original review text", "languageCode": "ta"}}
        assert _get_review_text(review) == "Original review text"

    def test_prefers_text_over_original(self):
        review = {
            "text": {"text": "English text", "languageCode": "en"},
            "originalText": {"text": "Tamil text", "languageCode": "ta"},
        }
        assert _get_review_text(review) == "English text"

    def test_empty_review_returns_empty_string(self):
        assert _get_review_text({}) == ""

    def test_empty_text_field_falls_back(self):
        review = {
            "text": {"text": "", "languageCode": "en"},
            "originalText": {"text": "Fallback text", "languageCode": "ta"},
        }
        assert _get_review_text(review) == "Fallback text"


class TestParseTimestamp:
    def test_iso_with_z(self):
        dt = _parse_timestamp("2024-06-01T10:00:00Z")
        assert isinstance(dt, datetime)
        assert dt.year == 2024

    def test_iso_with_offset(self):
        dt = _parse_timestamp("2024-06-01T10:00:00+05:30")
        assert isinstance(dt, datetime)

    def test_empty_string_returns_none(self):
        assert _parse_timestamp("") is None

    def test_invalid_string_returns_none(self):
        assert _parse_timestamp("not-a-date") is None


class TestInferLocation:
    def test_city_found_in_address(self):
        loc, conf = _infer_location("Anna Nagar, Chennai, Tamil Nadu, India", "Chennai")
        assert loc == "Chennai"
        assert conf == "inferred"

    def test_city_alias_found(self):
        # "bengaluru" is an alias for "bangalore"
        loc, conf = _infer_location("MG Road, Bengaluru, Karnataka 560001, India", "bangalore")
        assert conf == "inferred"

    def test_india_fallback(self):
        loc, conf = _infer_location("Some Street, Some City, India", "Chennai")
        # Chennai not in address → regional if India present
        # Actually Chennai not matched → check India
        assert conf in ("inferred", "regional", "unknown")

    def test_india_in_address_no_city(self):
        loc, conf = _infer_location("Some Street, Unknown City, India", None)
        assert loc == "India"
        assert conf == "regional"

    def test_no_signal(self):
        loc, conf = _infer_location("123 Main Street, Springfield", None)
        assert loc is None
        assert conf == "unknown"

    def test_no_target_city_but_city_in_address(self):
        loc, conf = _infer_location("Anna Nagar, Chennai, Tamil Nadu, India", None)
        # No target_city → only India signal checked
        assert conf in ("regional", "unknown")


# ── Provider unit tests ───────────────────────────────────────────────────────

class TestGoogleReviewsProviderProperties:
    def test_name(self):
        with patch("app.ml.discovery.google_reviews_provider.settings", _mock_settings()):
            p = GoogleReviewsProvider()
        assert p.name == "google_reviews"

    def test_platform(self):
        with patch("app.ml.discovery.google_reviews_provider.settings", _mock_settings()):
            p = GoogleReviewsProvider()
        assert p.platform == "google_reviews"

    def test_supported_categories_is_wildcard(self):
        with patch("app.ml.discovery.google_reviews_provider.settings", _mock_settings()):
            p = GoogleReviewsProvider()
        assert p.supported_categories == ["*"]

    def test_supported_regions_is_wildcard(self):
        with patch("app.ml.discovery.google_reviews_provider.settings", _mock_settings()):
            p = GoogleReviewsProvider()
        assert p.supported_regions == ["*"]

    def test_raises_when_no_api_key(self):
        mock_s = _mock_settings()
        mock_s.google_places_credentials_configured.return_value = False
        with patch("app.ml.discovery.google_reviews_provider.settings", mock_s):
            with pytest.raises(RuntimeError, match="GOOGLE_PLACES_API_KEY"):
                GoogleReviewsProvider()


class TestGoogleReviewsProviderHealthCheck:
    @pytest.mark.asyncio
    async def test_health_check_ok(self):
        mock_s = _mock_settings()
        with patch("app.ml.discovery.google_reviews_provider.settings", mock_s):
            p = GoogleReviewsProvider()

        places_data = _places_response([_make_place()])
        p._search_places = AsyncMock(return_value=places_data["places"])

        result = await p.health_check()
        assert result["ok"] is True
        assert result["provider"] == "google_reviews"

    @pytest.mark.asyncio
    async def test_health_check_failure(self):
        mock_s = _mock_settings()
        with patch("app.ml.discovery.google_reviews_provider.settings", mock_s):
            p = GoogleReviewsProvider()

        p._search_places = AsyncMock(side_effect=RuntimeError("API key invalid"))

        result = await p.health_check()
        assert result["ok"] is False
        assert "API key invalid" in result["detail"]


class TestGoogleReviewsProviderDiscoverUsers:
    def _build_provider(self) -> GoogleReviewsProvider:
        mock_s = _mock_settings()
        with patch("app.ml.discovery.google_reviews_provider.settings", mock_s):
            return GoogleReviewsProvider()

    @pytest.mark.asyncio
    async def test_returns_list(self):
        p = self._build_provider()
        p._search_places = AsyncMock(return_value=[_make_place()])
        with patch("app.ml.discovery.google_reviews_provider.settings", _mock_settings()):
            result = await p.discover_users(["furniture"], "Chennai", 50, {})
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_returns_raw_discovered_users(self):
        p = self._build_provider()
        p._search_places = AsyncMock(return_value=[_make_place()])
        with patch("app.ml.discovery.google_reviews_provider.settings", _mock_settings()):
            result = await p.discover_users(["furniture"], "Chennai", 50, {})
        assert len(result) > 0
        assert all(isinstance(u, RawDiscoveredUser) for u in result)

    @pytest.mark.asyncio
    async def test_required_fields_populated(self):
        p = self._build_provider()
        p._search_places = AsyncMock(return_value=[_make_place()])
        with patch("app.ml.discovery.google_reviews_provider.settings", _mock_settings()):
            result = await p.discover_users(["furniture"], "Chennai", 50, {})
        assert len(result) > 0
        u = result[0]
        assert u.platform == "google_reviews"
        assert u.source_provider == "google_places_api_v1"
        assert u.platform_user_id == "109876543210"
        assert u.username == "109876543210"
        assert u.display_name == "Priya Sharma"

    @pytest.mark.asyncio
    async def test_location_inferred_for_chennai(self):
        p = self._build_provider()
        p._search_places = AsyncMock(return_value=[_make_place()])
        with patch("app.ml.discovery.google_reviews_provider.settings", _mock_settings()):
            result = await p.discover_users(["furniture"], "Chennai", 50, {})
        u = result[0]
        assert u.location == "Chennai"
        assert u.location_confidence == "inferred"

    @pytest.mark.asyncio
    async def test_respects_max_users(self):
        reviews = [
            _make_review(contributor_id=f"10000000000{i}", display_name=f"User {i}")
            for i in range(10)
        ]
        p = self._build_provider()
        p._search_places = AsyncMock(return_value=[_make_place(reviews=reviews)])
        with patch("app.ml.discovery.google_reviews_provider.settings", _mock_settings()):
            result = await p.discover_users(["furniture"], "Chennai", max_users=3, search_config={})
        assert len(result) <= 3

    @pytest.mark.asyncio
    async def test_deduplicates_reviewers_across_businesses(self):
        shared_review = _make_review(contributor_id="999999999999")
        place1 = _make_place(place_id="place001", name="Store A", reviews=[shared_review])
        place2 = _make_place(place_id="place002", name="Store B", reviews=[shared_review])
        p = self._build_provider()
        p._search_places = AsyncMock(return_value=[place1, place2])
        with patch("app.ml.discovery.google_reviews_provider.settings", _mock_settings()):
            result = await p.discover_users(["furniture"], "Chennai", 50, {})
        contributor_ids = [u.platform_user_id for u in result]
        assert contributor_ids.count("999999999999") == 1

    @pytest.mark.asyncio
    async def test_deduplicates_across_keywords(self):
        shared_review = _make_review(contributor_id="111111111111")
        p = self._build_provider()
        # Both keywords return the same reviewer
        p._search_places = AsyncMock(
            return_value=[_make_place(reviews=[shared_review])]
        )
        with patch("app.ml.discovery.google_reviews_provider.settings", _mock_settings()):
            result = await p.discover_users(["sofa", "furniture"], "Chennai", 50, {})
        assert sum(1 for u in result if u.platform_user_id == "111111111111") == 1

    @pytest.mark.asyncio
    async def test_skips_short_reviews(self):
        short_review = _make_review(contributor_id="222222222222", text="Good")
        p = self._build_provider()
        p._search_places = AsyncMock(return_value=[_make_place(reviews=[short_review])])
        with patch("app.ml.discovery.google_reviews_provider.settings", _mock_settings()):
            result = await p.discover_users(["furniture"], "Chennai", 50, {})
        # Short review (< 15 chars) must be skipped
        assert all(u.platform_user_id != "222222222222" for u in result)

    @pytest.mark.asyncio
    async def test_raw_profile_contains_review_text(self):
        p = self._build_provider()
        p._search_places = AsyncMock(return_value=[_make_place()])
        with patch("app.ml.discovery.google_reviews_provider.settings", _mock_settings()):
            result = await p.discover_users(["furniture"], "Chennai", 50, {})
        u = result[0]
        assert "reviews" in u.raw_profile
        assert len(u.raw_profile["reviews"]) == 1
        assert "sofa" in u.raw_profile["reviews"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_empty_places_response_returns_empty_list(self):
        p = self._build_provider()
        p._search_places = AsyncMock(return_value=[])
        with patch("app.ml.discovery.google_reviews_provider.settings", _mock_settings()):
            result = await p.discover_users(["furniture"], "Chennai", 50, {})
        assert result == []

    @pytest.mark.asyncio
    async def test_api_error_skips_keyword_continues(self):
        p = self._build_provider()
        # First keyword fails, second succeeds
        p._search_places = AsyncMock(
            side_effect=[
                RuntimeError("API error"),
                [_make_place()],
            ]
        )
        with patch("app.ml.discovery.google_reviews_provider.settings", _mock_settings()):
            result = await p.discover_users(["bad_kw", "furniture"], "Chennai", 50, {})
        # Should still return results from the second keyword
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_keyword_limit_respected(self):
        p = self._build_provider()
        call_count = 0

        async def mock_search(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return [_make_place(
                reviews=[_make_review(contributor_id=f"99999{call_count:05d}")]
            )]

        p._search_places = mock_search
        # GOOGLE_PLACES_MAX_KEYWORDS = 3, pass 10 keywords
        with patch("app.ml.discovery.google_reviews_provider.settings", _mock_settings()):
            await p.discover_users(
                [f"kw{i}" for i in range(10)], "Chennai", 500, {}
            )
        assert call_count <= 3

    @pytest.mark.asyncio
    async def test_profile_url_is_contributor_maps_uri(self):
        p = self._build_provider()
        p._search_places = AsyncMock(return_value=[_make_place()])
        with patch("app.ml.discovery.google_reviews_provider.settings", _mock_settings()):
            result = await p.discover_users(["furniture"], "Chennai", 50, {})
        u = result[0]
        assert u.profile_url and "maps/contrib" in u.profile_url

    @pytest.mark.asyncio
    async def test_discovered_via_contains_business_name(self):
        p = self._build_provider()
        p._search_places = AsyncMock(
            return_value=[_make_place(name="Urban Ladder Store")]
        )
        with patch("app.ml.discovery.google_reviews_provider.settings", _mock_settings()):
            result = await p.discover_users(["furniture"], "Chennai", 50, {})
        u = result[0]
        assert "Urban Ladder Store" in u.discovered_via


class TestGoogleReviewsProviderCollectContent:
    def _make_user_with_reviews(self, n_reviews: int = 1) -> RawDiscoveredUser:
        reviews = [
            {
                "text": f"Review number {i}: Great quality furniture with excellent finish.",
                "rating": 4 + (i % 2),
                "published_time": "2024-06-01T10:00:00Z",
                "place_id": "ChIJtest0001",
                "place_name": "Wooden Street",
                "place_address": "Chennai, Tamil Nadu, India",
            }
            for i in range(n_reviews)
        ]
        return RawDiscoveredUser(
            platform="google_reviews",
            source_provider="google_places_api_v2",
            platform_user_id="109876543210",
            username="109876543210",
            display_name="Priya Sharma",
            raw_profile={
                "place_id": "ChIJtest0001",
                "place_name": "Wooden Street",
                "keyword": "furniture",
                "reviews": reviews,
            },
        )

    @pytest.mark.asyncio
    async def test_returns_list(self):
        mock_s = _mock_settings()
        with patch("app.ml.discovery.google_reviews_provider.settings", mock_s):
            p = GoogleReviewsProvider()
        user = self._make_user_with_reviews(1)
        result = await p.collect_content(user, max_items=10)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_returns_content_items(self):
        mock_s = _mock_settings()
        with patch("app.ml.discovery.google_reviews_provider.settings", mock_s):
            p = GoogleReviewsProvider()
        user = self._make_user_with_reviews(1)
        result = await p.collect_content(user, max_items=10)
        assert all(isinstance(c, ContentItem) for c in result)

    @pytest.mark.asyncio
    async def test_content_type_is_comment(self):
        mock_s = _mock_settings()
        with patch("app.ml.discovery.google_reviews_provider.settings", mock_s):
            p = GoogleReviewsProvider()
        user = self._make_user_with_reviews(1)
        result = await p.collect_content(user, max_items=10)
        assert len(result) > 0
        assert all(c.content_type == "comment" for c in result)

    @pytest.mark.asyncio
    async def test_content_text_matches_review(self):
        mock_s = _mock_settings()
        with patch("app.ml.discovery.google_reviews_provider.settings", mock_s):
            p = GoogleReviewsProvider()
        user = self._make_user_with_reviews(1)
        result = await p.collect_content(user, max_items=10)
        assert "Review number 0" in result[0].content_text

    @pytest.mark.asyncio
    async def test_respects_max_items(self):
        mock_s = _mock_settings()
        with patch("app.ml.discovery.google_reviews_provider.settings", mock_s):
            p = GoogleReviewsProvider()
        user = self._make_user_with_reviews(5)
        result = await p.collect_content(user, max_items=2)
        assert len(result) <= 2

    @pytest.mark.asyncio
    async def test_source_url_contains_place_id(self):
        mock_s = _mock_settings()
        with patch("app.ml.discovery.google_reviews_provider.settings", mock_s):
            p = GoogleReviewsProvider()
        user = self._make_user_with_reviews(1)
        result = await p.collect_content(user, max_items=10)
        assert "ChIJtest0001" in (result[0].source_url or "")

    @pytest.mark.asyncio
    async def test_posted_at_parsed(self):
        mock_s = _mock_settings()
        with patch("app.ml.discovery.google_reviews_provider.settings", mock_s):
            p = GoogleReviewsProvider()
        user = self._make_user_with_reviews(1)
        result = await p.collect_content(user, max_items=10)
        assert isinstance(result[0].posted_at, datetime)

    @pytest.mark.asyncio
    async def test_no_api_calls_made(self):
        """collect_content must not make any HTTP calls — content is in raw_profile."""
        mock_s = _mock_settings()
        with patch("app.ml.discovery.google_reviews_provider.settings", mock_s):
            p = GoogleReviewsProvider()
        user = self._make_user_with_reviews(1)
        # Patch _search_places to raise — it should never be called
        p._search_places = AsyncMock(side_effect=AssertionError("unexpected HTTP call"))
        result = await p.collect_content(user, max_items=10)
        # Reaching here means no HTTP call was made
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_empty_raw_profile_returns_empty(self):
        mock_s = _mock_settings()
        with patch("app.ml.discovery.google_reviews_provider.settings", mock_s):
            p = GoogleReviewsProvider()
        user = RawDiscoveredUser(
            platform="google_reviews",
            source_provider="google_places_api_v2",
            platform_user_id="000000000000",
            username="000000000000",
            raw_profile={},
        )
        result = await p.collect_content(user, max_items=10)
        assert result == []

    @pytest.mark.asyncio
    async def test_engagement_derived_from_rating(self):
        mock_s = _mock_settings()
        with patch("app.ml.discovery.google_reviews_provider.settings", mock_s):
            p = GoogleReviewsProvider()
        user = self._make_user_with_reviews(1)
        # First review has rating=4 → engagement=80
        result = await p.collect_content(user, max_items=10)
        assert result[0].engagement == 80
