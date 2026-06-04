"""
InstagramProvider — discovers users from public Instagram content.

Authentication: Username + password via instagrapi (Instagram Private API).
  - Uses a dedicated Instagram account (not your personal account).
  - Sessions are persisted to a JSON file to avoid repeated logins.
  - Credentials are read from environment variables.

Credentials required (set in .env by project owner):
  INSTAGRAM_USERNAME   — Instagram account username (dedicated account recommended)
  INSTAGRAM_PASSWORD   — Instagram account password

Session persistence:
  INSTAGRAM_SESSION_FILE — path to session JSON file (default: instagram_session.json)
  The session file stores cookies and device fingerprint so the client can resume
  without re-login on restart. Mount a persistent volume at this path in Docker.

Discovery flow:
  1. Convert motivation keywords → Instagram hashtags (e.g. "luxury sofa" → "luxurysofa").
  2. Search each hashtag for recent posts (up to INSTAGRAM_MAX_POSTS_PER_HASHTAG).
  3. Collect post authors as candidate leads (discovery_method = "poster").
  4. Collect commenters on each post (discovery_method = "commenter").
  5. Merge records for users found via both sources (discovery_method = "both").
  6. Fetch full profiles for all discovered users (filter out private profiles).
  7. Return as RawDiscoveredUser list.

discovery_method field (stored in raw_profile):
  "poster"    — user was found as a post author via hashtag search
  "commenter" — user was found commenting on a relevant post
  "both"      — user was found as both poster and commenter

Rate limiting:
  - instagrapi enforces request delays via client.delay_range = [1, 3] (seconds).
  - Additional 1.5s sleep between hashtag searches.
  - PleaseWaitFewMinutes exception → 65s sleep + retry.

Error handling:
  - LoginRequired       → automatic re-authentication (once per call)
  - PleaseWaitFewMinutes→ sleep 65s and retry (once per call)
  - ChallengeRequired   → logged, raises RuntimeError with recovery instructions
  - PrivateError        → skip (private profile — no public content to collect)
  - UserNotFound        → skip (account deleted or deactivated)
  - MediaNotFound       → skip (post deleted or unavailable)
  - General exceptions  → logged at WARNING/DEBUG, continue with next item

post_count: populated from Instagram media_count when available.
follower_count: populated from Instagram follower_count.
"""
from __future__ import annotations

import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Any

from app.config import settings
from app.ml.discovery.base import BaseDiscoveryProvider, ContentItem, RawDiscoveredUser

logger = logging.getLogger(__name__)

# ── City / location signals ───────────────────────────────────────────────────

_CITY_SIGNALS: dict[str, list[str]] = {
    "chennai": ["chennai", "madras", "tamil nadu", "tn", "chn", "namma chennai"],
    "bangalore": ["bangalore", "bengaluru", "blr", "karnataka", "namma bengaluru"],
    "mumbai": ["mumbai", "bombay", "maharashtra", "mum", "aamchi mumbai"],
    "delhi": ["delhi", "new delhi", "ncr", "gurgaon", "gurugram", "noida"],
    "hyderabad": ["hyderabad", "hyd", "telangana", "cyberabad"],
    "kolkata": ["kolkata", "calcutta", "wb", "west bengal"],
    "pune": ["pune", "pmc"],
    "ahmedabad": ["ahmedabad", "amd", "gujarat"],
    "kochi": ["kochi", "cochin", "kerala", "ernakulam"],
    "jaipur": ["jaipur", "rajasthan", "pink city"],
}

_INDIA_SIGNALS = ["india", "indian", "desi", "bharat", "indiadesign", "indiahomes"]

# Compiled pattern for whole-word India detection.
# Using word boundaries prevents "desi" from matching "design", etc.
_INDIA_RE = re.compile(
    r"\b(" + "|".join(re.escape(s) for s in _INDIA_SIGNALS) + r")\b",
    re.IGNORECASE,
)


def _infer_location(
    bio: str,
    target_city: str | None,
    extra_text: str = "",
) -> tuple[str | None, str]:
    """
    Infer location confidence from Instagram biography and supplementary text
    (captions, hashtag names).

    Returns (location_text, confidence_level).

    Confidence levels:
      confirmed — city name or alias found in bio or post text
      regional  — India-level signal only (no specific city detected)
      unknown   — no geographic signal found
    """
    combined = f"{bio} {extra_text}".lower()
    city_lower = (target_city or "").lower()

    if city_lower:
        signals = _CITY_SIGNALS.get(city_lower, [city_lower])
        for sig in signals:
            if sig in combined:
                return target_city, "confirmed"

    if _INDIA_RE.search(combined):
        return "India", "regional"

    return None, "unknown"


def _keywords_to_hashtags(keywords: list[str]) -> list[str]:
    """
    Convert motivation keywords into Instagram hashtag names (without the # prefix).

    Strategy:
      1. Multi-word keywords → concatenated (e.g. "luxury sofa" → "luxurysofa").
      2. Individual words (≥4 chars) added as separate hashtags for broader reach.
      3. Deduplication preserving insertion order.
      4. Capped at 30 hashtags to limit API usage.

    Examples:
      "luxury sofa"     → ["luxurysofa", "luxury", "sofa"]
      "interior design" → ["interiordesign", "interior", "design"]
      "premium leather" → ["premiumleather", "premium", "leather"]
    """
    seen: set[str] = set()
    hashtags: list[str] = []

    for kw in keywords:
        # Strip special characters, lower-case, split on whitespace
        cleaned = re.sub(r"[^a-zA-Z0-9\s]", "", kw.lower()).strip()
        if not cleaned:
            continue

        words = [w for w in cleaned.split() if len(w) >= 3]
        if not words:
            continue

        # Compound form first (highest specificity)
        compound = "".join(words)
        if compound not in seen and 3 <= len(compound) <= 30:
            seen.add(compound)
            hashtags.append(compound)

        # Individual meaningful words (≥4 chars)
        for word in words:
            if word not in seen and len(word) >= 4:
                seen.add(word)
                hashtags.append(word)

    return hashtags[:30]


class InstagramProvider(BaseDiscoveryProvider):
    """
    Discovers Instagram users from public hashtag-based content.

    Finds two classes of leads:
      Posters    — users who publish content related to product keywords.
      Commenters — users who engage with (comment on) relevant posts.

    Users discovered via both paths are merged with discovery_method = "both".

    The provider integrates into the existing discovery architecture without
    any special-case logic in NLP, OCEAN, Matching, or Dashboard components.
    All output uses the same RawDiscoveredUser / ContentItem contracts.
    """

    def __init__(self) -> None:
        if not settings.instagram_credentials_configured():
            raise RuntimeError(
                "Instagram credentials are not configured. "
                "Set INSTAGRAM_USERNAME and INSTAGRAM_PASSWORD in your .env file."
            )

        try:
            from instagrapi import Client  # noqa: F401 — verify library is installed
        except ImportError as exc:
            raise RuntimeError(
                "instagrapi is not installed. "
                "Run: pip install 'instagrapi>=1.6.0'"
            ) from exc

        from instagrapi import Client
        from instagrapi.exceptions import (
            ChallengeRequired,
            LoginRequired,
            PleaseWaitFewMinutes,
        )

        self._username = settings.INSTAGRAM_USERNAME
        self._password = settings.INSTAGRAM_PASSWORD
        self._session_file = settings.INSTAGRAM_SESSION_FILE

        # Store exception classes as instance attributes so they are accessible
        # in helper methods without re-importing (avoids overhead in hot paths).
        self._LoginRequired = LoginRequired
        self._PleaseWaitFewMinutes = PleaseWaitFewMinutes
        self._ChallengeRequired = ChallengeRequired

        self._client = Client()
        # Random delay [1–3 s] between API requests — critical for staying
        # within Instagram's undocumented rate limits.
        self._client.delay_range = [1, 3]

        self._login_with_session_recovery()
        logger.info(
            "InstagramProvider initialised (account=%s, session_file=%s)",
            self._username,
            self._session_file,
        )

    # ── BaseDiscoveryProvider interface ──────────────────────────────────────

    @property
    def name(self) -> str:
        return "instagram"

    @property
    def platform(self) -> str:
        return "instagram"

    @property
    def supported_categories(self) -> list[str]:
        return ["*"]

    @property
    def supported_regions(self) -> list[str]:
        return ["*"]

    async def health_check(self) -> dict:
        """
        Verify the Instagram session is valid by fetching the authenticated
        account's own profile — the lightest possible authenticated API call.
        """
        import asyncio
        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(None, self._health_check_sync)
            return result
        except Exception as exc:
            return {"ok": False, "provider": self.name, "detail": str(exc)}

    def _health_check_sync(self) -> dict:
        try:
            info = self._api_call(self._client.account_info)
            return {
                "ok": True,
                "provider": self.name,
                "detail": f"Authenticated as @{info.username} (pk={info.pk})",
            }
        except Exception as exc:
            return {"ok": False, "provider": self.name, "detail": str(exc)}

    # ── Discovery ─────────────────────────────────────────────────────────────

    async def discover_users(
        self,
        keywords: list[str],
        target_city: str | None,
        max_users: int,
        search_config: dict,
    ) -> list[RawDiscoveredUser]:
        """
        Discover Instagram users from hashtag-based content.

        Steps:
          1. Convert motivation keywords to Instagram hashtags.
          2. For each hashtag: collect recent posts and their commenters.
          3. Merge poster / commenter records for the same user.
          4. Fetch full public profiles.
          5. Return up to max_users RawDiscoveredUser objects.
        """
        import asyncio
        loop = asyncio.get_running_loop()

        hashtags = _keywords_to_hashtags(keywords)
        logger.info(
            "InstagramProvider.discover_users: hashtags=%s keywords=%s max=%d",
            hashtags[:6],
            keywords[:4],
            max_users,
        )

        result = await loop.run_in_executor(
            None, self._discover_sync, hashtags, target_city, max_users, search_config
        )
        logger.info("InstagramProvider: discovered %d users", len(result))
        return result

    def _discover_sync(
        self,
        hashtags: list[str],
        target_city: str | None,
        max_users: int,
        search_config: dict,
    ) -> list[RawDiscoveredUser]:
        """
        Synchronous discovery implementation — runs in the thread pool executor.

        Accumulates user data in a dict keyed by Instagram PK so that
        poster/commenter merging happens naturally as the same user is
        encountered in different contexts.
        """
        max_posts = settings.INSTAGRAM_MAX_POSTS_PER_HASHTAG
        max_comments = settings.INSTAGRAM_MAX_COMMENTS_PER_POST

        # pk (str) → accumulated user data dict
        accumulated: dict[str, dict[str, Any]] = {}

        for hashtag in hashtags:
            # Collect extra candidates beyond max_users to allow for filtering
            # (private profiles, unavailable accounts, etc.)
            if len(accumulated) >= max_users * 3:
                break

            try:
                medias = self._api_call(
                    self._client.hashtag_medias_recent_v1,
                    hashtag,
                    amount=max_posts,
                )
            except Exception as exc:
                logger.warning(
                    "InstagramProvider: hashtag %r failed: %s", hashtag, exc
                )
                continue

            for media in medias:
                try:
                    poster_pk = str(media.user.pk)
                    caption = (getattr(media, "caption_text", None) or "").strip()

                    # ── Register or update poster ─────────────────────────
                    if poster_pk not in accumulated:
                        accumulated[poster_pk] = _new_user_entry(
                            pk=poster_pk,
                            username=media.user.username,
                            display_name=getattr(media.user, "full_name", "") or media.user.username,
                            method="poster",
                            hashtag=hashtag,
                        )
                    else:
                        entry = accumulated[poster_pk]
                        if entry["discovery_method"] == "commenter":
                            entry["discovery_method"] = "both"
                        _add_hashtag(entry, hashtag)

                    if caption:
                        accumulated[poster_pk]["post_captions"].append(caption[:800])

                    # ── Collect commenters from this post ─────────────────
                    try:
                        comments = self._api_call(
                            self._client.media_comments,
                            media.pk,
                            amount=max_comments,
                        )
                    except Exception as exc:
                        logger.debug(
                            "InstagramProvider: comments unavailable for media %s: %s",
                            media.pk, exc,
                        )
                        comments = []

                    for comment in comments:
                        try:
                            comment_text = (getattr(comment, "text", None) or "").strip()
                            if not comment_text or len(comment_text) < 5:
                                continue

                            commenter_pk = str(comment.user.pk)
                            if commenter_pk == poster_pk:
                                continue  # skip author replying to own post

                            if commenter_pk not in accumulated:
                                accumulated[commenter_pk] = _new_user_entry(
                                    pk=commenter_pk,
                                    username=comment.user.username,
                                    display_name=getattr(comment.user, "full_name", "") or comment.user.username,
                                    method="commenter",
                                    hashtag=hashtag,
                                )
                            else:
                                entry = accumulated[commenter_pk]
                                if entry["discovery_method"] == "poster":
                                    entry["discovery_method"] = "both"
                                _add_hashtag(entry, hashtag)

                            accumulated[commenter_pk]["comment_texts"].append(
                                comment_text[:500]
                            )
                        except Exception as exc:
                            logger.debug("Comment processing error: %s", exc)
                            continue

                except Exception as exc:
                    logger.debug("Media processing error: %s", exc)
                    continue

            # Polite inter-hashtag delay
            time.sleep(1.5)

        # ── Fetch full profiles and build RawDiscoveredUser objects ────────
        result: list[RawDiscoveredUser] = []
        candidates = list(accumulated.items())

        for user_pk, data in candidates:
            if len(result) >= max_users:
                break

            try:
                profile = self._api_call(self._client.user_info, int(user_pk))

                if getattr(profile, "is_private", False):
                    logger.debug(
                        "InstagramProvider: skipping private profile @%s",
                        data["username"],
                    )
                    continue

                bio = (getattr(profile, "biography", None) or "").strip()
                hashtag_text = " ".join(data.get("hashtags_seen", []))
                location, confidence = _infer_location(bio, target_city, hashtag_text)

                username = getattr(profile, "username", data["username"])
                result.append(
                    RawDiscoveredUser(
                        platform="instagram",
                        source_provider="instagram",
                        platform_user_id=user_pk,
                        username=username,
                        display_name=getattr(profile, "full_name", data["display_name"]) or username,
                        bio=bio or None,
                        location=location,
                        location_confidence=confidence,
                        follower_count=getattr(profile, "follower_count", 0) or 0,
                        post_count=getattr(profile, "media_count", None),
                        profile_url=f"https://www.instagram.com/{username}/",
                        discovered_via=",".join(data.get("hashtags_seen", [])[:3]),
                        raw_profile={
                            "pk": user_pk,
                            "discovery_method": data["discovery_method"],
                            "post_captions": data.get("post_captions", [])[:5],
                            "comment_texts": data.get("comment_texts", [])[:5],
                            "hashtags_seen": data.get("hashtags_seen", []),
                            "following_count": getattr(profile, "following_count", 0) or 0,
                            "media_count": getattr(profile, "media_count", 0) or 0,
                        },
                    )
                )

            except Exception as exc:
                logger.debug(
                    "InstagramProvider: profile fetch failed for pk=%s (@%s): %s",
                    user_pk, data.get("username", "?"), exc,
                )
                continue

        return result

    # ── Content collection ────────────────────────────────────────────────────

    async def collect_content(
        self,
        user: RawDiscoveredUser,
        max_items: int,
    ) -> list[ContentItem]:
        """
        Return content items for an Instagram user.

        Primary sources (already collected during discover_users — zero new API calls):
          1. Biography              (content_type = "bio")
          2. Post captions          (content_type = "post")
          3. Comment texts          (content_type = "comment")

        Secondary source (one API call, only when primary sources are sparse):
          4. Recent posts fetched from user profile via user_medias()
        """
        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._collect_content_sync, user, max_items
        )

    def _collect_content_sync(
        self,
        user: RawDiscoveredUser,
        max_items: int,
    ) -> list[ContentItem]:
        items: list[ContentItem] = []
        raw = user.raw_profile or {}

        # 1. Biography
        if user.bio:
            items.append(ContentItem(
                content_type="bio",
                content_text=user.bio,
                source_url=user.profile_url,
                engagement=0,
            ))

        # 2. Post captions captured during hashtag discovery
        for caption in raw.get("post_captions", []):
            if len(items) >= max_items:
                break
            if caption and len(caption) >= 10:
                items.append(ContentItem(
                    content_type="post",
                    content_text=caption,
                    source_url=user.profile_url,
                    engagement=0,
                ))

        # 3. Comment texts captured during post crawl
        for comment_text in raw.get("comment_texts", []):
            if len(items) >= max_items:
                break
            if comment_text and len(comment_text) >= 5:
                items.append(ContentItem(
                    content_type="comment",
                    content_text=comment_text,
                    source_url=user.profile_url,
                    engagement=0,
                ))

        # 4. Fetch additional posts if primary content is sparse
        # Threshold: if we have fewer than max(2, max_items//3) items, fetch more.
        need_more = len(items) < max(2, max_items // 3)
        if need_more and user.platform_user_id:
            try:
                fetch_count = min(max_items - len(items) + 2, 12)
                medias = self._api_call(
                    self._client.user_medias,
                    int(user.platform_user_id),
                    amount=fetch_count,
                )
                for media in medias:
                    if len(items) >= max_items:
                        break
                    caption = (getattr(media, "caption_text", None) or "").strip()
                    if not caption or len(caption) < 10:
                        continue

                    posted_at: datetime | None = None
                    taken_at = getattr(media, "taken_at", None)
                    if taken_at:
                        try:
                            if isinstance(taken_at, datetime):
                                posted_at = taken_at
                            else:
                                posted_at = datetime.fromtimestamp(
                                    float(taken_at), tz=timezone.utc
                                )
                        except Exception:
                            pass

                    code = getattr(media, "code", "")
                    items.append(ContentItem(
                        content_type="post",
                        content_text=caption[:1000],
                        source_url=(
                            f"https://www.instagram.com/p/{code}/"
                            if code else user.profile_url
                        ),
                        engagement=getattr(media, "like_count", 0) or 0,
                        posted_at=posted_at,
                    ))
            except Exception as exc:
                logger.debug(
                    "InstagramProvider: additional content fetch failed for @%s: %s",
                    user.username, exc,
                )

        return items[:max_items]

    # ── Session management ────────────────────────────────────────────────────

    def _login_with_session_recovery(self) -> None:
        """
        Authenticate with Instagram, preferring session restoration over fresh login.

        Flow:
          1. If session file exists, load it (restores cookies + device fingerprint).
          2. Call client.login() — uses loaded cookies if valid, else sends credentials.
          3. On LoginRequired after loading a session → clear stale session, retry fresh.
          4. Save the resulting session to file after any successful login.
        """
        session_loaded = False
        if os.path.exists(self._session_file):
            try:
                self._client.load_settings(self._session_file)
                session_loaded = True
                logger.info(
                    "InstagramProvider: session loaded from %s", self._session_file
                )
            except Exception as exc:
                logger.warning(
                    "InstagramProvider: could not load session from %s: %s",
                    self._session_file, exc,
                )

        try:
            self._client.login(self._username, self._password)
            self._save_session()
            logger.info(
                "InstagramProvider: authenticated (session_reused=%s)", session_loaded
            )
        except self._LoginRequired:
            if session_loaded:
                # Stored session is stale — clear and perform a fresh login.
                logger.warning(
                    "InstagramProvider: stored session expired, performing fresh login"
                )
                self._client.set_settings({})
                self._client.login(self._username, self._password)
                self._save_session()
            else:
                raise

        # Verify the session actually works for the private API (not just account_info).
        # A browser-derived session passes login() but fails on all real API calls.
        # Catch this early so the orchestrator falls back to mock instead of running
        # a provider that silently returns 0 results for every hashtag.
        self._verify_api_access()

    def _verify_api_access(self) -> None:
        """
        Confirm the current session can actually reach the private API.

        A browser-derived sessionid passes cl.login() (no challenge triggered
        because user_id is set from the session file), but all mobile private-API
        calls subsequently return LoginRequired.  Catching this here lets the
        orchestrator fall back to MockDiscoveryProvider rather than silently
        producing zero results.

        We probe user_info() on the own account — the lightest private-API call
        available without a hashtag search.
        """
        try:
            uid = None
            if self._client.user_id:
                uid = int(self._client.user_id)
            if uid:
                self._client.user_info(uid)
                logger.info("InstagramProvider: private-API access verified (uid=%d)", uid)
        except self._LoginRequired as exc:
            raise RuntimeError(
                "Instagram session appears valid but the private API rejected all requests "
                "(LoginRequired on user_info). "
                "This usually means a browser-derived sessionid was used instead of a "
                "proper mobile app session. "
                "Run backend/verify_instagram.py and approve the login in your "
                "Instagram app to create a valid mobile session."
            ) from exc
        except Exception:
            # Any other exception (network, timeout, etc.) — don't block startup.
            pass

    def _save_session(self) -> None:
        """Persist the current Instagram session to the configured file."""
        try:
            parent = os.path.dirname(self._session_file)
            if parent:
                os.makedirs(parent, exist_ok=True)
            self._client.dump_settings(self._session_file)
            logger.debug(
                "InstagramProvider: session persisted to %s", self._session_file
            )
        except Exception as exc:
            logger.warning(
                "InstagramProvider: could not persist session to %s: %s",
                self._session_file, exc,
            )

    def _reauth(self) -> None:
        """
        Force a fresh re-authentication by clearing the stale session.
        Raises RuntimeError if Instagram requires a manual challenge (2FA / suspicious login).
        """
        try:
            self._client.set_settings({})
            self._client.login(self._username, self._password)
            self._save_session()
            logger.info("InstagramProvider: re-authenticated successfully")
        except self._ChallengeRequired as exc:
            logger.error(
                "InstagramProvider: Instagram requires manual challenge verification. "
                "Please resolve the security check in a browser and restart the "
                "application. Detail: %s", exc,
            )
            raise RuntimeError(
                "Instagram challenge verification required (2FA or suspicious-login check). "
                "Please log in to Instagram manually from the same IP address and resolve "
                "any security check, then restart the application. "
                "If the problem persists, use a different dedicated account."
            ) from exc

    # ── API call wrapper ──────────────────────────────────────────────────────

    def _api_call(self, fn, *args, **kwargs):
        """
        Execute an instagrapi API call with automatic re-auth and rate-limit handling.

        Retry policy:
          - LoginRequired       → re-authenticate once, then retry the call.
          - PleaseWaitFewMinutes → sleep 65 s, then retry once.
          - All other exceptions propagate unchanged to the caller.
        """
        try:
            return fn(*args, **kwargs)
        except self._LoginRequired:
            logger.warning(
                "InstagramProvider: LoginRequired on %s — re-authenticating",
                getattr(fn, "__name__", str(fn)),
            )
            self._reauth()
            return fn(*args, **kwargs)
        except self._PleaseWaitFewMinutes:
            logger.warning(
                "InstagramProvider: rate-limited (PleaseWaitFewMinutes) — sleeping 65 s"
            )
            time.sleep(65)
            return fn(*args, **kwargs)


# ── Module-level helpers ──────────────────────────────────────────────────────

def _new_user_entry(
    pk: str,
    username: str,
    display_name: str,
    method: str,
    hashtag: str,
) -> dict[str, Any]:
    """Create a fresh accumulated-user entry dict."""
    return {
        "username": username,
        "display_name": display_name,
        "pk": pk,
        "discovery_method": method,   # "poster" | "commenter" | "both"
        "post_captions": [],
        "comment_texts": [],
        "hashtags_seen": [hashtag],
    }


def _add_hashtag(entry: dict[str, Any], hashtag: str) -> None:
    """Add a hashtag to the entry's seen list (deduplicating)."""
    if hashtag not in entry["hashtags_seen"]:
        entry["hashtags_seen"].append(hashtag)
