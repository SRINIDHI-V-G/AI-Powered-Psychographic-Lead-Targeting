"""
RedditProvider — discovers users from public Reddit content.

Authentication: Application-Only OAuth (client credentials grant).
  - No end-user Reddit login required.
  - No customer data accessed.
  - Read-only access to all public subreddits.

Credentials required (set in .env by project owner — see CREDENTIALS_REQUIRED.md):
  REDDIT_CLIENT_ID     — from reddit.com/prefs/apps
  REDDIT_CLIENT_SECRET — from reddit.com/prefs/apps
  REDDIT_USER_AGENT    — e.g. "python:PsychographicLeads:1.0 (by u/project_owner)"

Rate limit: PRAW enforces Reddit's 60 req/min limit automatically.
Content per user: settings.DISCOVERY_CONTENT_PER_USER (default 15).
  Rationale: OCEAN prompt uses 8 items; NLP benefits level off after 15.
  15 items gives >95% of signal value at 60% of API cost vs 25.

post_count: NOT populated for Reddit users.
  Reddit's API exposes karma totals, not actual post counts.
  Storing an estimate would create false precision in the matching engine.
  follower_count = link_karma + comment_karma (engagement proxy).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.config import settings
from app.ml.discovery.base import BaseDiscoveryProvider, ContentItem, RawDiscoveredUser
from app.ml.discovery.subreddit_map import get_city_subreddits, get_subreddits_for_keywords

logger = logging.getLogger(__name__)


def _infer_location(
    bio: str,
    subreddit_name: str,
    target_city: str | None,
) -> tuple[str | None, str]:
    """
    Returns (location_text, confidence_level).

    Confidence levels:
      confirmed — city appears explicitly in bio
      inferred  — found via a city-specific subreddit
      regional  — country-level signal only
      unknown   — no geographic signal
    """
    bio_lower = (bio or "").lower()
    sub_lower = subreddit_name.lower()
    city_lower = (target_city or "").lower()

    # Confirmed: city explicitly in bio
    if city_lower and city_lower in bio_lower:
        return target_city, "confirmed"

    # Also check common city abbreviations
    _CITY_ALIASES: dict[str, list[str]] = {
        "chennai": ["madras", "tamil nadu", "tn", "chn"],
        "bangalore": ["bengaluru", "blr", "karnataka"],
        "mumbai": ["bombay", "maharashtra", "mum"],
        "delhi": ["new delhi", "ncr", "delhincr"],
        "hyderabad": ["hyd", "telangana"],
        "kolkata": ["calcutta", "wb", "west bengal"],
    }
    aliases = _CITY_ALIASES.get(city_lower, [])
    if any(alias in bio_lower for alias in aliases):
        return target_city, "confirmed"

    # Inferred: city-specific subreddit
    if city_lower and (city_lower in sub_lower or sub_lower in city_lower):
        return target_city, "inferred"

    # Regional: India-level signals
    india_signals = ["india", "indian", "r/india", "desi"]
    if any(sig in bio_lower for sig in india_signals):
        return "India", "regional"

    return None, "unknown"


class RedditProvider(BaseDiscoveryProvider):
    """
    Discovers users from public Reddit content using PRAW.
    Uses Application-Only OAuth — no user login required.

    Instantiation raises CredentialError if credentials are not configured.
    The orchestrator checks settings.use_mock_discovery() before instantiating.
    """

    def __init__(self) -> None:
        if not settings.reddit_credentials_configured():
            raise RuntimeError(
                "Reddit credentials are not configured. "
                "Set REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, and REDDIT_USER_AGENT "
                "in your .env file. See backend/CREDENTIALS_REQUIRED.md."
            )
        try:
            import praw  # type: ignore[import]
        except ImportError as exc:
            raise RuntimeError("praw is not installed. Run: pip install praw==7.7.1") from exc

        self._reddit = praw.Reddit(
            client_id=settings.REDDIT_CLIENT_ID,
            client_secret=settings.REDDIT_CLIENT_SECRET,
            user_agent=settings.REDDIT_USER_AGENT,
        )
        logger.info(
            "RedditProvider initialised (read-only, client_id=%s...)",
            settings.REDDIT_CLIENT_ID[:6],
        )

    @property
    def name(self) -> str:
        return "reddit"

    @property
    def platform(self) -> str:
        return "reddit"

    async def health_check(self) -> dict:
        try:
            # Cheap API call to verify credentials work
            import asyncio
            loop = asyncio.get_event_loop()
            limits = await loop.run_in_executor(
                None, lambda: self._reddit.auth.limits
            )
            return {
                "ok": True,
                "provider": self.name,
                "detail": f"Reddit API responsive, rate limits: {limits}",
            }
        except Exception as exc:
            return {
                "ok": False,
                "provider": self.name,
                "detail": str(exc),
            }

    async def discover_users(
        self,
        keywords: list[str],
        target_city: str | None,
        max_users: int,
        search_config: dict,
    ) -> list[RawDiscoveredUser]:
        """
        Step A: map keywords → subreddits.
        Step B: search each subreddit with each keyword → extract post authors.
        Step C: fetch author profiles.
        Step D: infer location confidence.
        Step E: deduplicate and return.
        """
        import asyncio

        # A: Get relevant subreddits
        topic_subs = get_subreddits_for_keywords(keywords, max_subreddits=8)
        city_subs = get_city_subreddits(target_city)
        all_subs = list(dict.fromkeys(topic_subs + city_subs))  # ordered dedup

        logger.info(
            "RedditProvider: subreddits=%s keywords=%s max=%d",
            all_subs[:6], keywords[:4], max_users,
        )

        seen_usernames: set[str] = set()
        result: list[RawDiscoveredUser] = []
        loop = asyncio.get_event_loop()

        for sub_name in all_subs:
            if len(result) >= max_users:
                break
            for kw in keywords[:3]:   # cap keywords per subreddit to limit API calls
                if len(result) >= max_users:
                    break
                try:
                    users_from_search = await loop.run_in_executor(
                        None,
                        self._search_subreddit,
                        sub_name, kw, min(50, max_users - len(result)),
                    )
                    for raw_user in users_from_search:
                        uname = raw_user.username
                        if uname in seen_usernames:
                            continue
                        seen_usernames.add(uname)

                        # Infer location
                        location, conf = _infer_location(
                            raw_user.bio or "", sub_name, target_city
                        )
                        raw_user.location = location
                        raw_user.location_confidence = conf

                        result.append(raw_user)
                        if len(result) >= max_users:
                            break

                except Exception as exc:
                    logger.warning(
                        "RedditProvider: error searching r/%s for %r: %s",
                        sub_name, kw, exc,
                    )
                    continue

        logger.info("RedditProvider: discovered %d users", len(result))
        return result

    def _search_subreddit(
        self,
        sub_name: str,
        keyword: str,
        limit: int,
    ) -> list[RawDiscoveredUser]:
        """
        Synchronous: searches a subreddit and extracts unique post authors.
        Runs in a thread pool executor to avoid blocking the event loop.
        """
        users: list[RawDiscoveredUser] = []
        try:
            subreddit = self._reddit.subreddit(sub_name)
            for submission in subreddit.search(keyword, limit=limit, sort="relevance"):
                author = submission.author
                if not author:
                    continue
                try:
                    # Accessing .id forces PRAW to fetch the full Redditor object.
                    # Skip suspended, deleted, or inaccessible accounts.
                    _ = author.id
                    if getattr(author, "is_suspended", False):
                        continue
                    bio_text = ""
                    try:
                        sub_info = getattr(author, "subreddit", {})
                        bio_text = (sub_info or {}).get("public_description", "") or ""
                    except Exception:
                        bio_text = ""

                    users.append(RawDiscoveredUser(
                        platform="reddit",
                        source_provider="reddit",
                        platform_user_id=str(author.id),
                        username=str(author.name),
                        display_name=str(author.name),
                        bio=bio_text or None,
                        follower_count=(
                            getattr(author, "link_karma", 0) +
                            getattr(author, "comment_karma", 0)
                        ),
                        post_count=None,  # Not reliably available from Reddit API
                        profile_url=f"https://reddit.com/u/{author.name}",
                        discovered_via=sub_name,
                        raw_profile={
                            "link_karma":    getattr(author, "link_karma", 0),
                            "comment_karma": getattr(author, "comment_karma", 0),
                            "account_age_days": max(
                                0,
                                int(
                                    (__import__("time").time() -
                                     getattr(author, "created_utc", 0)) / 86400
                                ),
                            ),
                            "subreddit": sub_name,
                        },
                    ))
                except Exception as exc:
                    logger.debug("Could not extract profile for %s: %s", author, exc)
                    continue
        except Exception as exc:
            logger.warning("Error searching r/%s: %s", sub_name, exc)
        return users

    async def collect_content(
        self,
        user: RawDiscoveredUser,
        max_items: int,
    ) -> list[ContentItem]:
        """
        Fetch recent public posts and comments for a Reddit user.
        Bio is included as content_type='bio' if available.

        OCEAN prompt uses max 8 items; NLP benefits plateau at ~15 items.
        max_items default = settings.DISCOVERY_CONTENT_PER_USER (15).
        """
        import asyncio
        loop = asyncio.get_event_loop()
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
            raw_items = await loop.run_in_executor(
                None, self._fetch_user_content, user.username, needed
            )
            items.extend(raw_items)
        except Exception as exc:
            logger.warning("collect_content failed for %s: %s", user.username, exc)

        return items[:max_items]

    def _fetch_user_content(self, username: str, limit: int) -> list[ContentItem]:
        """Synchronous: fetch recent posts/comments for a Reddit user."""
        items: list[ContentItem] = []
        try:
            redditor = self._reddit.redditor(username)
            # Fetch a mix of posts and comments
            for item in redditor.new(limit=limit):
                try:
                    # Submission (post) vs Comment
                    if hasattr(item, "title"):
                        text = f"{item.title} {item.selftext or ''}".strip()
                        ctype = "post"
                        url = f"https://reddit.com{item.permalink}"
                        score = item.score
                    else:
                        text = item.body or ""
                        ctype = "comment"
                        url = f"https://reddit.com{item.permalink}"
                        score = item.score

                    if not text or text == "[deleted]" or text == "[removed]":
                        continue

                    # Trim very long text — OCEAN prompt truncates to 300 chars anyway,
                    # but we store full text for NLP (Empath/BERTopic need more context)
                    text = text[:2000]

                    posted = None
                    try:
                        if hasattr(item, "created_utc"):
                            posted = datetime.fromtimestamp(
                                item.created_utc, tz=timezone.utc
                            )
                    except Exception:
                        pass

                    items.append(ContentItem(
                        content_type=ctype,
                        content_text=text,
                        source_url=url,
                        engagement=score,
                        posted_at=posted,
                    ))
                except Exception as exc:
                    logger.debug("Error processing content item: %s", exc)
                    continue
        except Exception as exc:
            logger.warning("Could not fetch content for %s: %s", username, exc)
        return items
