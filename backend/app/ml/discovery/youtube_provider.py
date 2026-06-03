"""
YouTubeProvider — discovers users from YouTube video comments.

Authentication: YouTube Data API v3 with an API key.
  - No OAuth / user consent required for public data.
  - API key is obtained from Google Cloud Console.
  - Set YOUTUBE_API_KEY in .env.

Discovery flow:
  1. Map motivation keywords to YouTube search queries.
  2. Search for videos (100 units / request, max 50 results).
  3. Fetch top comments for each video (1 unit / request).
  4. Each unique comment author becomes a RawDiscoveredUser.
  5. collect_content: the comments already collected during discovery
     are returned as ContentItems directly.

Quota management:
  - Default daily quota: 10,000 units.
  - One full discovery run (10 keywords × 10 videos × 50 comments):
      search calls:   10 × 100  = 1,000 units
      comment calls:  100 × 1   =   100 units
      total:                     ~1,100 units (11% of daily quota)
  - Tune YOUTUBE_MAX_VIDEOS_PER_KEYWORD and YOUTUBE_MAX_COMMENTS_PER_VIDEO
    in .env to adjust quota consumption.

Rate limiting: Google enforces 100 requests/second per project. The provider
sleeps 0.1s between API calls to stay safely below this limit.

Credentials required:
  YOUTUBE_API_KEY — from Google Cloud Console → APIs & Services → Credentials

Falls back to MockDiscoveryProvider if credentials are absent.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import settings
from app.ml.discovery.base import BaseDiscoveryProvider, ContentItem, RawDiscoveredUser

logger = logging.getLogger(__name__)

_YT_BASE = "https://www.googleapis.com/youtube/v3"
_REQUEST_SLEEP = 0.1       # seconds between API calls to stay under rate limit


class YouTubeProvider(BaseDiscoveryProvider):
    """
    Discovers users from YouTube comment sections for videos matching
    the product's motivation keywords.

    Instantiation raises RuntimeError if YOUTUBE_API_KEY is not configured.
    The orchestrator checks settings.youtube_credentials_configured() before
    instantiating; if credentials are absent it falls back to MockProvider.
    """

    def __init__(self) -> None:
        if not settings.youtube_credentials_configured():
            raise RuntimeError(
                "YouTube API key not configured. "
                "Set YOUTUBE_API_KEY in .env. "
                "See https://console.cloud.google.com."
            )
        self._api_key = settings.YOUTUBE_API_KEY
        self._client: httpx.AsyncClient | None = None
        logger.info("YouTubeProvider initialised (key=...%s)", self._api_key[-6:])

    # ── BaseDiscoveryProvider interface ───────────────────────────────────────

    @property
    def name(self) -> str:
        return "youtube"

    @property
    def platform(self) -> str:
        return "youtube"

    @property
    def supported_categories(self) -> list[str]:
        return ["*"]

    @property
    def supported_regions(self) -> list[str]:
        return ["*"]

    async def health_check(self) -> dict:
        try:
            # Make a cheap, 1-unit request (channel lookup by ID)
            resp = await self._get("/channels", {
                "part": "id",
                "id": "UCVHFbw7woebKtHUDsDQfglA",   # YouTube Help channel — always exists
                "maxResults": 1,
            })
            return {
                "ok": True,
                "provider": self.name,
                "detail": f"YouTube API reachable (items={len(resp.get('items', []))})",
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
        Search YouTube for videos matching each keyword, then collect commenters
        from those videos as candidate leads.
        """
        max_videos_per_kw = settings.YOUTUBE_MAX_VIDEOS_PER_KEYWORD
        max_comments_per_video = settings.YOUTUBE_MAX_COMMENTS_PER_VIDEO

        seen_channel_ids: set[str] = set()
        result: list[RawDiscoveredUser] = []

        # Use at most 15 keywords to keep quota consumption reasonable
        active_keywords = keywords[:15]

        for keyword in active_keywords:
            if len(result) >= max_users:
                break

            try:
                video_ids = await self._search_videos(keyword, max_results=max_videos_per_kw)
            except Exception as exc:
                logger.warning("YouTubeProvider: search failed for %r: %s", keyword, exc)
                continue

            for video_id in video_ids:
                if len(result) >= max_users:
                    break

                try:
                    comments = await self._get_comments(
                        video_id, max_results=max_comments_per_video
                    )
                except Exception as exc:
                    logger.warning("YouTubeProvider: comments failed for video %s: %s", video_id, exc)
                    continue

                for comment in comments:
                    if len(result) >= max_users:
                        break

                    channel_id = comment.get("author_channel_id")
                    if not channel_id or channel_id in seen_channel_ids:
                        continue
                    seen_channel_ids.add(channel_id)

                    location, confidence = _infer_location(
                        comment.get("author_name", ""),
                        comment.get("text", ""),
                        target_city,
                    )

                    user = RawDiscoveredUser(
                        platform="youtube",
                        source_provider="youtube",
                        platform_user_id=channel_id,
                        username=channel_id,           # channel ID as stable identifier
                        display_name=comment.get("author_name"),
                        bio=None,                      # bio requires extra API call; skip for now
                        location=location,
                        location_confidence=confidence,
                        follower_count=0,              # subscriber count requires extra call
                        post_count=None,
                        profile_url=f"https://www.youtube.com/channel/{channel_id}",
                        discovered_via=f"video:{video_id}",
                        raw_profile={
                            "video_id": video_id,
                            "keyword": keyword,
                            # Store the discovery comment for use in collect_content
                            "discovery_comment": comment.get("text", ""),
                            "comment_like_count": comment.get("like_count", 0),
                            "comment_published_at": comment.get("published_at", ""),
                        },
                    )
                    result.append(user)

        logger.info("YouTubeProvider: discovered %d users", len(result))
        return result

    async def collect_content(
        self,
        user: RawDiscoveredUser,
        max_items: int,
    ) -> list[ContentItem]:
        """
        Return content items for a YouTube user.

        Primary source: the comment captured during discovery (already in raw_profile).
        Secondary source: attempt to fetch up to (max_items - 1) additional comments
        by this author across the videos we know about — limited to avoid quota burn.
        """
        items: list[ContentItem] = []

        discovery_comment = (user.raw_profile or {}).get("discovery_comment", "")
        video_id = (user.raw_profile or {}).get("video_id", "")
        like_count = int((user.raw_profile or {}).get("comment_like_count", 0))

        if discovery_comment:
            published_str = (user.raw_profile or {}).get("comment_published_at", "")
            posted = None
            if published_str:
                try:
                    posted = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
                except ValueError:
                    posted = None

            items.append(ContentItem(
                content_type="comment",
                content_text=discovery_comment,
                source_url=(
                    f"https://www.youtube.com/watch?v={video_id}"
                    if video_id else user.profile_url
                ),
                engagement=like_count,
                posted_at=posted,
            ))

        # Try to fetch additional comments by this author from the same video
        # (quota cost: 1 unit per call; limit to 1 call to stay frugal)
        if len(items) < max_items and video_id and user.platform_user_id:
            try:
                extra = await self._get_comments_by_author(
                    video_id=video_id,
                    author_channel_id=user.platform_user_id,
                    max_results=min(max_items - len(items), 10),
                )
                for c in extra:
                    if c.get("text") and c.get("text") != discovery_comment:
                        items.append(ContentItem(
                            content_type="comment",
                            content_text=c["text"],
                            source_url=f"https://www.youtube.com/watch?v={video_id}",
                            engagement=int(c.get("like_count", 0)),
                        ))
            except Exception as exc:
                logger.debug("collect_content extra fetch failed for %s: %s", user.username, exc)

        return items[:max_items]

    # ── YouTube API helpers ────────────────────────────────────────────────────

    async def _get(self, path: str, params: dict) -> dict:
        """Make a GET request to the YouTube Data API v3."""
        await asyncio.sleep(_REQUEST_SLEEP)
        url = f"{_YT_BASE}{path}"
        params["key"] = self._api_key

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, params=params)

        if resp.status_code == 403:
            data = resp.json()
            reason = data.get("error", {}).get("message", "quota or auth error")
            raise RuntimeError(f"YouTube API 403: {reason}")
        if resp.status_code == 429:
            raise RuntimeError("YouTube API rate limit exceeded (429). Retry later.")
        resp.raise_for_status()
        return resp.json()

    async def _search_videos(self, keyword: str, max_results: int = 10) -> list[str]:
        """Search YouTube for videos matching `keyword`. Returns list of video IDs."""
        data = await self._get("/search", {
            "part": "id",
            "q": keyword,
            "type": "video",
            "maxResults": min(max_results, 50),
            "order": "relevance",
            "videoEmbeddable": "true",
            "safeSearch": "none",
        })
        return [item["id"]["videoId"] for item in data.get("items", [])]

    async def _get_comments(self, video_id: str, max_results: int = 50) -> list[dict]:
        """
        Fetch top-level comment threads for a video.
        Returns list of dicts with: text, author_name, author_channel_id,
        like_count, published_at.
        """
        try:
            data = await self._get("/commentThreads", {
                "part": "snippet",
                "videoId": video_id,
                "maxResults": min(max_results, 100),
                "order": "relevance",
                "textFormat": "plainText",
            })
        except Exception:
            # Comments may be disabled for this video — return empty list
            return []

        comments: list[dict] = []
        for item in data.get("items", []):
            top = item.get("snippet", {}).get("topLevelComment", {}).get("snippet", {})
            if not top:
                continue
            text = top.get("textDisplay", "").strip()
            if not text or len(text) < 10:     # skip very short comments
                continue
            comments.append({
                "text": text,
                "author_name": top.get("authorDisplayName", ""),
                "author_channel_id": top.get("authorChannelId", {}).get("value", ""),
                "like_count": top.get("likeCount", 0),
                "published_at": top.get("publishedAt", ""),
            })
        return comments

    async def _get_comments_by_author(
        self,
        video_id: str,
        author_channel_id: str,
        max_results: int = 10,
    ) -> list[dict]:
        """
        Fetch comments on a specific video filtered by author channel ID.
        YouTube doesn't have a direct author-filter endpoint; we fetch all
        comments and filter in Python.
        """
        all_comments = await self._get_comments(video_id, max_results=100)
        return [
            c for c in all_comments
            if c.get("author_channel_id") == author_channel_id
        ][:max_results]


# ── Location inference ────────────────────────────────────────────────────────

_CITY_SIGNALS: dict[str, list[str]] = {
    "chennai": ["chennai", "madras", "tamil nadu", "tn", "chn"],
    "bangalore": ["bangalore", "bengaluru", "blr", "karnataka"],
    "mumbai": ["mumbai", "bombay", "maharashtra", "mum"],
    "delhi": ["delhi", "new delhi", "ncr"],
    "hyderabad": ["hyderabad", "hyd", "telangana"],
    "kolkata": ["kolkata", "calcutta", "wb", "west bengal"],
}

_INDIA_SIGNALS = ["india", "indian", "desi", "bharat"]


def _infer_location(
    display_name: str,
    comment_text: str,
    target_city: str | None,
) -> tuple[str | None, str]:
    """
    Infer location confidence from the author's display name and comment text.
    YouTube comments rarely contain location signals; most users get 'unknown'.
    """
    combined = f"{display_name} {comment_text}".lower()
    city_lower = (target_city or "").lower()

    if city_lower:
        signals = _CITY_SIGNALS.get(city_lower, [city_lower])
        if any(sig in combined for sig in signals):
            return target_city, "confirmed"

    if any(sig in combined for sig in _INDIA_SIGNALS):
        return "India", "regional"

    return None, "unknown"
