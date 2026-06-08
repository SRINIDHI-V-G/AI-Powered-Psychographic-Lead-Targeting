"""
GoogleReviewsProvider — discovers leads from Google Maps business reviews.

Authentication: Google Places API (New) with an API key.
  - No OAuth or business ownership required.
  - Obtain a key at https://console.cloud.google.com → enable "Places API (New)".
  - Set GOOGLE_PLACES_API_KEY in .env.

Discovery flow:
  1. For each motivation keyword, build a query: "{keyword} near {city}".
  2. POST /v2/places:searchText with reviews in the FieldMask.
  3. Each business returns up to 5 reviewer entries (Google's hard limit).
  4. Extract reviewers by contributor ID (stable across businesses).
  5. Deduplicate globally — one RawDiscoveredUser per Google Maps contributor.
  6. collect_content: review texts already stored in raw_profile are returned
     as ContentItems — no additional API calls needed.

Location advantage vs Reddit/YouTube:
  Every reviewer is a verified customer of a real business located in the
  target city. Their location_confidence is "inferred" by default — a
  significant improvement over comment-based providers.

Quota management:
  - Text Search (Basic tier): $0.032 / request
  - + Atmosphere data (reviews field): $0.005 / request
  - 10 keywords × 1 page = 10 requests ≈ $0.37 per full discovery run
  - Google gives $200/month free credit — effectively free in development.
  - Tune GOOGLE_PLACES_MAX_BUSINESSES_PER_KEYWORD and GOOGLE_PLACES_MAX_KEYWORDS
    in .env to adjust cost and coverage.

Rate limiting: sleep 0.2 s between API calls (conservative).

Credentials required:
  GOOGLE_PLACES_API_KEY — from Google Cloud Console with Places API (New) enabled.

Falls back to MockDiscoveryProvider if credentials are absent.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

import httpx

from app.config import settings
from app.ml.discovery.base import BaseDiscoveryProvider, ContentItem, RawDiscoveredUser

logger = logging.getLogger(__name__)

_PLACES_BASE = "https://places.googleapis.com/v2"
_REQUEST_SLEEP = 0.2  # seconds between API calls

# Fields requested from Places API — only what the provider needs.
# reviews is "Atmosphere" tier; everything else is "Basic".
_FIELD_MASK = (
    "places.id,"
    "places.displayName,"
    "places.formattedAddress,"
    "places.reviews,"
    "places.rating,"
    "places.userRatingCount"
)

# City → list of address signals used to confirm location from business address.
_CITY_SIGNALS: dict[str, list[str]] = {
    "chennai":   ["chennai", "madras", "tamil nadu", "tn"],
    "bangalore": ["bangalore", "bengaluru", "blr", "karnataka"],
    "mumbai":    ["mumbai", "bombay", "maharashtra"],
    "delhi":     ["delhi", "new delhi", "ncr", "gurugram", "noida", "gurgaon"],
    "hyderabad": ["hyderabad", "hyd", "telangana"],
    "kolkata":   ["kolkata", "calcutta", "west bengal"],
    "pune":      ["pune", "pimpri", "maharashtra"],
    "ahmedabad": ["ahmedabad", "gujarat"],
}

_INDIA_SIGNALS = ["india"]


class GoogleReviewsProvider(BaseDiscoveryProvider):
    """
    Discovers leads from Google Maps business reviews via the Places API (New).

    Instantiation raises RuntimeError if GOOGLE_PLACES_API_KEY is not set.
    The orchestrator checks settings.google_places_credentials_configured()
    before instantiating; absent credentials fall back to MockProvider.
    """

    def __init__(self) -> None:
        if not settings.google_places_credentials_configured():
            raise RuntimeError(
                "Google Places API key not configured. "
                "Set GOOGLE_PLACES_API_KEY in .env. "
                "Enable 'Places API (New)' at https://console.cloud.google.com."
            )
        self._api_key = settings.GOOGLE_PLACES_API_KEY
        logger.info(
            "GoogleReviewsProvider initialised (key=...%s)", self._api_key[-6:]
        )

    # ── BaseDiscoveryProvider interface ───────────────────────────────────────

    @property
    def name(self) -> str:
        return "google_reviews"

    @property
    def platform(self) -> str:
        return "google_reviews"

    @property
    def supported_categories(self) -> list[str]:
        return ["*"]

    @property
    def supported_regions(self) -> list[str]:
        return ["*"]

    async def health_check(self) -> dict:
        try:
            places = await self._search_places("coffee shop", max_results=1, city=None)
            return {
                "ok": True,
                "provider": self.name,
                "detail": f"Places API reachable (places_returned={len(places)})",
            }
        except Exception as exc:
            return {"ok": False, "provider": self.name, "detail": str(exc)}

    async def discover_users(
        self,
        keywords: list[str],
        target_city: str | None,
        max_users: int,
        search_config: dict,
    ) -> list[RawDiscoveredUser]:
        """
        For each keyword, search Google Maps for matching businesses in the
        target city, then extract reviewers as candidate leads.

        Each unique Google Maps contributor becomes one RawDiscoveredUser.
        Reviews are stored in raw_profile for zero-cost content collection.
        """
        max_kw = settings.GOOGLE_PLACES_MAX_KEYWORDS
        max_biz = settings.GOOGLE_PLACES_MAX_BUSINESSES_PER_KEYWORD

        seen_contributor_ids: set[str] = set()
        result: list[RawDiscoveredUser] = []

        active_keywords = keywords[:max_kw]

        for keyword in active_keywords:
            if len(result) >= max_users:
                break

            try:
                places = await self._search_places(
                    keyword, max_results=max_biz, city=target_city
                )
            except Exception as exc:
                logger.warning(
                    "GoogleReviewsProvider: search failed for %r: %s", keyword, exc
                )
                continue

            for place in places:
                if len(result) >= max_users:
                    break

                place_id = place.get("id", "")
                place_name = (
                    place.get("displayName", {}).get("text", "")
                    or "Unknown Business"
                )
                place_address = place.get("formattedAddress", "")
                place_rating = place.get("rating", 0)
                place_review_count = place.get("userRatingCount", 0)

                reviews: list[dict] = place.get("reviews", [])
                if not reviews:
                    continue

                for review in reviews:
                    if len(result) >= max_users:
                        break

                    author = review.get("authorAttribution", {})
                    contributor_uri = author.get("uri", "")
                    contributor_id = _extract_contributor_id(contributor_uri)

                    if not contributor_id or contributor_id in seen_contributor_ids:
                        continue

                    review_text = _get_review_text(review)
                    if not review_text or len(review_text) < 15:
                        continue

                    seen_contributor_ids.add(contributor_id)

                    display_name = (
                        author.get("displayName", "")
                        or f"Reviewer {contributor_id[-6:]}"
                    )

                    location, confidence = _infer_location(place_address, target_city)

                    user = RawDiscoveredUser(
                        platform="google_reviews",
                        source_provider="google_places_api_v2",
                        platform_user_id=contributor_id,
                        username=contributor_id,
                        display_name=display_name,
                        bio=None,
                        location=location,
                        location_confidence=confidence,
                        follower_count=0,
                        post_count=None,
                        profile_url=contributor_uri or None,
                        discovered_via=f"business:{place_name}",
                        raw_profile={
                            "place_id": place_id,
                            "place_name": place_name,
                            "place_address": place_address,
                            "place_rating": place_rating,
                            "place_review_count": place_review_count,
                            "keyword": keyword,
                            "photo_uri": author.get("photoUri", ""),
                            # Stored for collect_content — avoids extra API calls.
                            "reviews": [
                                {
                                    "text": review_text,
                                    "rating": review.get("rating", 0),
                                    "published_time": review.get("publishTime", ""),
                                    "place_id": place_id,
                                    "place_name": place_name,
                                    "place_address": place_address,
                                }
                            ],
                        },
                    )
                    result.append(user)

        logger.info("GoogleReviewsProvider: discovered %d users", len(result))
        return result

    async def collect_content(
        self,
        user: RawDiscoveredUser,
        max_items: int,
    ) -> list[ContentItem]:
        """
        Return review texts collected during discover_users as ContentItems.

        No additional API calls are made — review text is already stored in
        raw_profile["reviews"] from the discovery phase.
        """
        items: list[ContentItem] = []
        raw = user.raw_profile or {}
        reviews: list[dict] = raw.get("reviews", [])

        for review in reviews:
            if len(items) >= max_items:
                break

            text = review.get("text", "")
            if not text:
                continue

            place_id = review.get("place_id", "")
            posted_at = _parse_timestamp(review.get("published_time", ""))

            # Use rating (1-5) × 20 as an engagement proxy (0-100 range).
            engagement = int(review.get("rating", 0)) * 20

            items.append(ContentItem(
                content_type="comment",
                content_text=text,
                source_url=(
                    f"https://www.google.com/maps/place/?q=place_id:{place_id}"
                    if place_id else user.profile_url
                ),
                engagement=engagement,
                posted_at=posted_at,
            ))

        return items[:max_items]

    # ── Places API helpers ────────────────────────────────────────────────────

    async def _search_places(
        self,
        keyword: str,
        max_results: int,
        city: str | None,
    ) -> list[dict[str, Any]]:
        """
        POST to Places API Text Search and return the places list.

        Appends the city to the query when provided so Google's ranking
        prioritises businesses in that location.
        """
        query = f"{keyword} near {city}" if city else keyword

        await asyncio.sleep(_REQUEST_SLEEP)

        headers = {
            "X-Goog-Api-Key": self._api_key,
            "X-Goog-FieldMask": _FIELD_MASK,
            "Content-Type": "application/json",
        }
        body: dict[str, Any] = {
            "textQuery": query,
            "languageCode": settings.GOOGLE_PLACES_LANGUAGE,
            "pageSize": min(max(1, max_results), 20),  # API maximum is 20
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{_PLACES_BASE}/places:searchText",
                headers=headers,
                json=body,
            )

        if resp.status_code == 400:
            raise RuntimeError(
                f"Google Places API 400 Bad Request: {resp.text[:300]}"
            )
        if resp.status_code == 403:
            data = resp.json()
            reason = (
                data.get("error", {}).get("message", "")
                or resp.text[:200]
            )
            raise RuntimeError(f"Google Places API 403 (key issue or quota): {reason}")
        if resp.status_code == 429:
            raise RuntimeError(
                "Google Places API rate limit exceeded (429). "
                "Wait and retry, or reduce GOOGLE_PLACES_MAX_KEYWORDS."
            )
        resp.raise_for_status()

        data = resp.json()
        places: list[dict] = data.get("places", [])
        logger.debug(
            "GoogleReviewsProvider: query=%r returned %d places", query, len(places)
        )
        return places


# ── Module-level helpers ──────────────────────────────────────────────────────

def _extract_contributor_id(uri: str) -> str | None:
    """
    Extract numeric contributor ID from a Google Maps contributor URI.

    URI format: https://www.google.com/maps/contrib/109876543210[/reviews?...]
    Returns the numeric portion, or None if the URI is empty/unrecognised.
    """
    if not uri or "/contrib/" not in uri:
        return None
    after = uri.split("/contrib/")[-1]
    # Strip query strings or trailing path segments
    contributor_id = after.split("?")[0].split("/")[0].strip()
    return contributor_id or None


def _get_review_text(review: dict) -> str:
    """
    Return the English review text, preferring originalText over text.
    Both fields have the same structure: {"text": str, "languageCode": str}.
    """
    for field in ("text", "originalText"):
        val = review.get(field, {})
        if isinstance(val, dict):
            text = (val.get("text") or "").strip()
            if text:
                return text
    return ""


def _parse_timestamp(ts: str) -> datetime | None:
    """Parse an ISO-8601 / RFC-3339 timestamp string into a datetime."""
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _infer_location(
    business_address: str,
    target_city: str | None,
) -> tuple[str | None, str]:
    """
    Infer reviewer location from the business address.

    Logic:
      - confirmed  → never: we cannot confirm the reviewer lives there, only
                     that they visited a business there.
      - inferred   → target city name (or alias) found in the business address.
      - regional   → "India" found in the address but no city match.
      - unknown    → no geographic signal detected.

    Every reviewer is at minimum a customer of the searched business, so
    inferred confidence is the expected outcome for well-formed queries.
    """
    addr_lower = business_address.lower()
    city_lower = (target_city or "").lower()

    if city_lower:
        signals = _CITY_SIGNALS.get(city_lower, [city_lower])
        if any(sig in addr_lower for sig in signals):
            return target_city, "inferred"

    for sig in _INDIA_SIGNALS:
        if sig in addr_lower:
            return "India", "regional"

    return None, "unknown"
