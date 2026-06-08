"""
RedditProvider — discovers users from public Reddit content.

Authentication: NONE — uses Reddit's public JSON API.
  No CLIENT_ID, CLIENT_SECRET, or OAuth required.
  Only a proper User-Agent header is needed.

Public endpoints used:
  https://www.reddit.com/r/{sub}/search.json?q={kw}&restrict_sr=1&sort=relevance
  https://www.reddit.com/r/{sub}/new.json
  https://www.reddit.com/r/{sub}/top.json?t=month
  https://www.reddit.com/user/{username}/about.json
  https://www.reddit.com/user/{username}/submitted.json
  https://www.reddit.com/user/{username}/comments.json

Environment variables:
  REDDIT_USER_AGENT  — e.g. "python:PsychographicLeads:1.0 (by u/username)"
  REDDIT_USERNAME    — optional, for future authenticated features
  REDDIT_PASSWORD    — optional, for future authenticated features

Rate limit: ~1 req/sec safe baseline (Reddit unofficial limit for public API).
Content per user: settings.DISCOVERY_CONTENT_PER_USER (default 15).
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import httpx

from app.config import settings
from app.ml.discovery.base import BaseDiscoveryProvider, ContentItem, RawDiscoveredUser
from app.ml.discovery.subreddit_map import get_city_subreddits, get_subreddits_for_keywords

logger = logging.getLogger(__name__)

# Reddit base URL for public JSON API
_BASE = "https://www.reddit.com"

# Authors to always skip — bots and deleted accounts
_SKIP_AUTHORS = frozenset({"[deleted]", "AutoModerator", "reddit"})


def _infer_location(
    bio: str,
    subreddit_name: str,
    target_city: str | None,
) -> tuple[str | None, str]:
    """
    Returns (location_text, confidence_level).
    confirmed — city in bio · inferred — city subreddit · regional — India signal · unknown
    """
    bio_lower = (bio or "").lower()
    sub_lower = subreddit_name.lower()
    city_lower = (target_city or "").lower()

    if city_lower and city_lower in bio_lower:
        return target_city, "confirmed"

    _CITY_ALIASES: dict[str, list[str]] = {
        "chennai":   ["madras", "tamil nadu", "tn", "chn"],
        "bangalore": ["bengaluru", "blr", "karnataka"],
        "mumbai":    ["bombay", "maharashtra", "mum"],
        "delhi":     ["new delhi", "ncr", "delhincr"],
        "hyderabad": ["hyd", "telangana"],
        "kolkata":   ["calcutta", "wb", "west bengal"],
    }
    for alias in _CITY_ALIASES.get(city_lower, []):
        if alias in bio_lower:
            return target_city, "confirmed"

    if city_lower and (city_lower in sub_lower or sub_lower in city_lower):
        return target_city, "inferred"

    if any(sig in bio_lower for sig in ["india", "indian", "r/india", "desi"]):
        return "India", "regional"

    return None, "unknown"


class RedditProvider(BaseDiscoveryProvider):
    """
    Discovers users from public Reddit content using raw httpx JSON requests.
    Requires ZERO OAuth credentials — public JSON API only.
    """

    def __init__(self) -> None:
        user_agent = settings.REDDIT_USER_AGENT or "python:PsychographicLeads:1.0"
        self._client = httpx.Client(
            headers={"User-Agent": user_agent},
            timeout=15.0,
            follow_redirects=True,
        )
        logger.info("RedditProvider initialised (public JSON API, no OAuth)")

    def __del__(self) -> None:
        try:
            self._client.close()
        except Exception:
            pass

    @property
    def name(self) -> str:
        return "reddit"

    @property
    def platform(self) -> str:
        return "reddit"

    # ── Public API helpers ────────────────────────────────────────────────────

    def _get_json(self, path: str, params: dict | None = None, retries: int = 2) -> dict:
        """GET a Reddit JSON endpoint. Handles 429 rate-limit with backoff."""
        url = f"{_BASE}{path}" if path.startswith("/") else path
        for attempt in range(retries + 1):
            try:
                resp = self._client.get(url, params=params)
                if resp.status_code == 429:
                    wait = 10 * (attempt + 1)
                    logger.warning("Reddit rate-limited (429) — sleeping %ds", wait)
                    time.sleep(wait)
                    continue
                if resp.status_code in (403, 404):
                    return {}  # private/banned/missing — caller handles
                resp.raise_for_status()
                return resp.json()
            except httpx.TimeoutException:
                if attempt < retries:
                    time.sleep(3)
                    continue
                return {}
            except Exception as exc:
                logger.debug("Reddit GET %s failed: %s", path, exc)
                return {}
        return {}

    # ── Discovery ─────────────────────────────────────────────────────────────

    async def health_check(self) -> dict:
        import asyncio
        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(None, self._health_check_sync)
            return result
        except Exception as exc:
            return {"ok": False, "provider": self.name, "detail": str(exc)}

    def _health_check_sync(self) -> dict:
        data = self._get_json("/r/redditdev/new.json", params={"limit": 1})
        children = data.get("data", {}).get("children", [])
        if children:
            title = children[0].get("data", {}).get("title", "")
            return {"ok": True, "provider": self.name, "detail": f"Public JSON API reachable (r/redditdev post: {title[:50]!r})"}
        return {"ok": False, "provider": self.name, "detail": "No posts returned from r/redditdev"}

    async def discover_users(
        self,
        keywords: list[str],
        target_city: str | None,
        max_users: int,
        search_config: dict,
    ) -> list[RawDiscoveredUser]:
        import asyncio
        loop = asyncio.get_running_loop()

        clean_keywords = [kw for kw in keywords if kw and kw.strip()]
        if not clean_keywords:
            logger.warning("RedditProvider: no valid keywords — returning empty")
            return []

        topic_subs = get_subreddits_for_keywords(clean_keywords, max_subreddits=8)
        city_subs  = get_city_subreddits(target_city)
        all_subs   = list(dict.fromkeys(topic_subs + city_subs))

        if not all_subs:
            logger.warning("RedditProvider: no subreddits for keywords=%s", clean_keywords[:4])
            return []

        logger.info(
            "RedditProvider: subreddits=%s keywords=%s max=%d",
            all_subs[:6], clean_keywords[:4], max_users,
        )

        result = await loop.run_in_executor(
            None, self._discover_sync,
            all_subs, clean_keywords, target_city, max_users,
        )
        logger.info("RedditProvider: discovered %d users", len(result))
        return result

    def _discover_sync(
        self,
        all_subs: list[str],
        keywords: list[str],
        target_city: str | None,
        max_users: int,
    ) -> list[RawDiscoveredUser]:
        """
        Two-pass discovery:
          Pass 1 — collect unique author usernames from subreddit searches (fast, no profile fetches)
          Pass 2 — fetch full profiles via /user/{u}/about.json (one call per unique user)
        """
        # Pass 1: Collect unique (username → subreddit) pairs
        author_map: dict[str, str] = {}   # username → first subreddit where found
        n_subs = len(all_subs)
        MAX_KW_PER_SUB = 3

        for sub_idx, sub_name in enumerate(all_subs):
            if len(author_map) >= max_users * 3:
                break
            sub_keywords = [
                keywords[i]
                for i in range(sub_idx, len(keywords), max(n_subs, 1))
            ][:MAX_KW_PER_SUB] or keywords[:MAX_KW_PER_SUB]

            for kw in sub_keywords:
                new_authors = self._get_authors_from_subreddit(
                    sub_name, kw, limit=50
                )
                for uname in new_authors:
                    if uname not in author_map:
                        author_map[uname] = sub_name
                time.sleep(0.5)  # polite inter-request delay

        logger.info("RedditProvider: %d unique authors found across subreddits", len(author_map))

        # Pass 2: Fetch profiles and build RawDiscoveredUser objects
        result: list[RawDiscoveredUser] = []
        candidates = list(author_map.items())[:max_users * 2]

        for username, sub_name in candidates:
            if len(result) >= max_users:
                break
            time.sleep(0.4)
            profile = self._fetch_user_profile(username, sub_name)
            if not profile:
                continue
            location, conf = _infer_location(profile.bio or "", sub_name, target_city)
            profile.location = location
            profile.location_confidence = conf
            result.append(profile)

        return result

    def _get_authors_from_subreddit(
        self,
        sub_name: str,
        keyword: str,
        limit: int,
    ) -> list[str]:
        """
        Return unique author usernames from subreddit search + /new.json.
        No profile fetches — just usernames from post metadata.
        """
        authors: list[str] = []
        seen: set[str] = set()

        def _extract_authors(children: list) -> None:
            for child in children:
                post = child.get("data", {})
                author = post.get("author", "")
                if not author or author in _SKIP_AUTHORS or author in seen:
                    continue
                seen.add(author)
                authors.append(author)

        # 1. Keyword search (most relevant)
        try:
            data = self._get_json(
                f"/r/{sub_name}/search.json",
                params={
                    "q": keyword,
                    "restrict_sr": "1",
                    "sort": "relevance",
                    "limit": min(limit, 50),
                },
            )
            _extract_authors(data.get("data", {}).get("children", []))
        except Exception as exc:
            logger.debug("r/%s search for %r failed: %s", sub_name, keyword, exc)

        # 2. Supplement with /new.json if search was sparse
        if len(authors) < limit // 3:
            try:
                data = self._get_json(
                    f"/r/{sub_name}/new.json",
                    params={"limit": min(limit, 50)},
                )
                _extract_authors(data.get("data", {}).get("children", []))
            except Exception as exc:
                logger.debug("r/%s /new.json failed: %s", sub_name, exc)

        # 3. /top.json as final supplement
        if len(authors) < limit // 4:
            try:
                data = self._get_json(
                    f"/r/{sub_name}/top.json",
                    params={"limit": min(limit, 50), "t": "month"},
                )
                _extract_authors(data.get("data", {}).get("children", []))
            except Exception as exc:
                logger.debug("r/%s /top.json failed: %s", sub_name, exc)

        return authors[:limit]

    def _fetch_user_profile(
        self,
        username: str,
        discovered_via: str,
    ) -> RawDiscoveredUser | None:
        """
        Fetch public user profile from /user/{username}/about.json.
        Returns None for suspended, deleted, or inaccessible accounts.
        """
        data = self._get_json(f"/user/{username}/about.json")
        if not data:
            return None

        kind = data.get("kind", "")
        if kind == "t2":
            udata = data.get("data", {})
        elif "data" in data:
            udata = data["data"]
        else:
            return None

        # Skip suspended or banned users
        if udata.get("is_suspended", False) or udata.get("is_blocked", False):
            return None

        name = udata.get("name", username)
        bio = ""
        subreddit_info = udata.get("subreddit") or {}
        if isinstance(subreddit_info, dict):
            bio = subreddit_info.get("public_description", "") or ""

        link_karma    = udata.get("link_karma", 0) or 0
        comment_karma = udata.get("comment_karma", 0) or 0

        return RawDiscoveredUser(
            platform="reddit",
            source_provider="reddit",
            platform_user_id=udata.get("id", username),
            username=name,
            display_name=name,
            bio=bio.strip() or None,
            follower_count=link_karma + comment_karma,
            post_count=None,  # Reddit API exposes karma, not post count
            profile_url=f"https://reddit.com/u/{name}",
            discovered_via=discovered_via,
            raw_profile={
                "link_karma":    link_karma,
                "comment_karma": comment_karma,
                "account_age_days": max(
                    0,
                    int((time.time() - (udata.get("created_utc") or time.time())) / 86400),
                ),
                "subreddit": discovered_via,
            },
        )

    # ── Content collection ────────────────────────────────────────────────────

    async def collect_content(
        self,
        user: RawDiscoveredUser,
        max_items: int,
    ) -> list[ContentItem]:
        import asyncio
        loop = asyncio.get_running_loop()
        items: list[ContentItem] = []

        # Bio first
        if user.bio:
            items.append(ContentItem(
                content_type="bio",
                content_text=user.bio,
                source_url=user.profile_url,
                engagement=0,
            ))

        needed = max_items - len(items)
        if needed <= 0:
            return items

        try:
            raw = await loop.run_in_executor(
                None, self._fetch_user_content, user.username, needed,
            )
            items.extend(raw)
        except Exception as exc:
            logger.warning("collect_content failed for u/%s: %s", user.username, exc)

        return items[:max_items]

    def _fetch_user_content(self, username: str, limit: int) -> list[ContentItem]:
        """
        Fetch recent posts + comments via:
          /user/{u}/submitted.json
          /user/{u}/comments.json
        """
        items: list[ContentItem] = []

        # Posts (submissions)
        data = self._get_json(
            f"/user/{username}/submitted.json",
            params={"limit": min(limit, 25)},
        )
        for child in data.get("data", {}).get("children", []):
            post = child.get("data", {})
            title   = post.get("title", "") or ""
            body    = post.get("selftext", "") or ""
            text    = f"{title} {body}".strip()
            if not text or text in ("[deleted]", "[removed]"):
                continue

            posted: datetime | None = None
            try:
                if ts := post.get("created_utc"):
                    posted = datetime.fromtimestamp(float(ts), tz=timezone.utc)
            except Exception:
                pass

            items.append(ContentItem(
                content_type="post",
                content_text=text[:2000],
                source_url=f"https://reddit.com{post.get('permalink', '')}",
                engagement=post.get("score", 0) or 0,
                posted_at=posted,
            ))

        # Comments
        if len(items) < limit:
            time.sleep(0.3)
            data = self._get_json(
                f"/user/{username}/comments.json",
                params={"limit": min(limit - len(items), 25)},
            )
            for child in data.get("data", {}).get("children", []):
                comment = child.get("data", {})
                text = (comment.get("body") or "").strip()
                if not text or text in ("[deleted]", "[removed]"):
                    continue

                posted = None
                try:
                    if ts := comment.get("created_utc"):
                        posted = datetime.fromtimestamp(float(ts), tz=timezone.utc)
                except Exception:
                    pass

                items.append(ContentItem(
                    content_type="comment",
                    content_text=text[:2000],
                    source_url=f"https://reddit.com{comment.get('permalink', '')}",
                    engagement=comment.get("score", 0) or 0,
                    posted_at=posted,
                ))

        return items
