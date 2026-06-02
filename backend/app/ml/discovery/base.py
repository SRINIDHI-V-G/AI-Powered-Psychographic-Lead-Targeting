"""
Discovery provider contract.

All discovery providers implement BaseDiscoveryProvider.
The contract guarantees that providers:
  1. Return RawDiscoveredUser objects (real, identifiable people)
  2. Return ContentItem objects (their public posts/comments)
  3. NEVER return review data or enrichment signals

Providers must NOT know about or write to database tables.
All persistence is the responsibility of the DiscoveryOrchestrator.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import AsyncIterator


# ── Data contracts ────────────────────────────────────────────────────────────

@dataclass
class RawDiscoveredUser:
    """
    A real, identifiable social-media user returned by a discovery provider.

    This is the provider's output format. The orchestrator maps it to the
    DiscoveredUser ORM model before persisting.
    """
    # Required
    platform: str           # "reddit", "youtube", "forum"
    source_provider: str    # "reddit", "youtube_data_api", "discourse"
    username: str           # public handle

    # Optional but strongly preferred
    platform_user_id: str | None = None
    display_name: str | None = None
    bio: str | None = None
    location: str | None = None

    # Location confidence: confirmed | inferred | regional | unknown
    # See discovery/base.py docstring for exact semantics.
    location_confidence: str = "unknown"

    # For Reddit: link_karma + comment_karma (engagement proxy, NOT post count)
    # For YouTube: subscriber count
    follower_count: int = 0

    # Only set by providers that have a reliable post count metric.
    # Reddit providers MUST leave this None — Reddit's API does not expose
    # actual post count, only karma totals. Storing estimates creates
    # false precision in the matching engine.
    post_count: int | None = None

    profile_url: str | None = None

    # Unstructured provider-specific metadata kept for debugging.
    # Not used by the NLP or OCEAN pipeline.
    raw_profile: dict = field(default_factory=dict)

    # Which subreddit/channel/forum the user was found in
    discovered_via: str = ""


@dataclass
class ContentItem:
    """
    One piece of public content from a discovered user.
    Maps to the UserContent ORM model.
    """
    # bio | post | comment
    content_type: str
    content_text: str
    source_url: str | None = None
    engagement: int = 0
    posted_at: datetime | None = None


# ── Location confidence semantics ─────────────────────────────────────────────
# confirmed — city name appears explicitly in the user's bio text
#             e.g. "Interior designer in Chennai"
# inferred  — user was found via a city-specific community
#             e.g. discovered in r/Chennai or r/Bangalore
# regional  — country-level signal only, no specific city
#             e.g. mentions "India" in bio, or found via r/india
# unknown   — no geographic signal detected

LOCATION_CONFIDENCE_LEVELS = ("confirmed", "inferred", "regional", "unknown")


# ── Abstract base class ───────────────────────────────────────────────────────

class BaseDiscoveryProvider(ABC):
    """
    Abstract base class for all discovery providers.

    Concrete implementations:
      - RedditProvider  (Phase B1)
      - YouTubeProvider (Phase B2 — not yet implemented)
      - ForumProvider   (Phase B2 — not yet implemented)

    Each provider must handle its own rate limiting and retry logic.
    The orchestrator calls providers sequentially or in parallel depending
    on the job configuration.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier, e.g. 'reddit'. Stored in discovery_jobs.provider_name."""

    @property
    @abstractmethod
    def platform(self) -> str:
        """Display platform name, e.g. 'reddit'. Stored in discovered_users.platform."""

    @property
    def supported_categories(self) -> list[str]:
        """
        Product categories this provider is effective for.
        Return ["*"] to indicate all categories are supported.
        The orchestrator uses this to select appropriate providers per product.
        """
        return ["*"]

    @property
    def supported_regions(self) -> list[str]:
        """
        ISO country codes this provider has reasonable coverage for.
        Return ["*"] to indicate global coverage.
        """
        return ["*"]

    @abstractmethod
    async def health_check(self) -> dict:
        """
        Returns:
          {"ok": True,  "provider": self.name, "detail": "..."}
          {"ok": False, "provider": self.name, "detail": "<reason>"}
        """

    @abstractmethod
    async def discover_users(
        self,
        keywords: list[str],
        target_city: str | None,
        max_users: int,
        search_config: dict,
    ) -> list[RawDiscoveredUser]:
        """
        Discover up to *max_users* public users relevant to the given keywords.

        Parameters
        ----------
        keywords    : merged, deduplicated list from all motivation categories
        target_city : the product's target city (used for location filtering)
        max_users   : hard upper limit on returned users
        search_config : full job search config dict (for provider-specific options)

        Returns a list of RawDiscoveredUser. May be shorter than max_users if
        the source is exhausted.
        """

    @abstractmethod
    async def collect_content(
        self,
        user: RawDiscoveredUser,
        max_items: int,
    ) -> list[ContentItem]:
        """
        Fetch up to *max_items* public content pieces for a discovered user.

        Parameters
        ----------
        user      : the RawDiscoveredUser whose content to collect
        max_items : upper limit (default from settings.DISCOVERY_CONTENT_PER_USER)

        Returns a list of ContentItem. Bio is included as content_type='bio'
        if the user has one.
        """
