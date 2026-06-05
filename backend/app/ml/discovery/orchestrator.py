"""
DiscoveryOrchestrator — coordinates discovery providers for a product.

Responsibilities:
  1. Select the correct provider(s) based on product category + credentials.
  2. Call discover_users() on each provider.
  3. Persist RawDiscoveredUser → DiscoveredUser in the DB.
  4. Call collect_content() per user and persist UserContent.
  5. Update DiscoveryJob status counters throughout.

The orchestrator is the only component that writes to the DB.
Providers never see the DB — they only produce data objects.

Architecture separation:
  Discovery providers  → find people → DiscoveredUser + UserContent
  Enrichment providers → find patterns → ProductEnrichmentSignal (Phase B3)
  These are NEVER mixed here.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.ml.discovery.base import BaseDiscoveryProvider, ContentItem, RawDiscoveredUser
from app.models.discovery import DiscoveredUser, DiscoveryJob, UserContent

logger = logging.getLogger(__name__)


def _build_provider_registry() -> list[BaseDiscoveryProvider]:
    """
    Return all available real providers in priority order.

    Provider selection priority (first matching provider wins):
      1. RedditProvider     — if Reddit credentials are configured
      2. YouTubeProvider    — if YouTube API key is configured
      3. InstagramProvider  — if Instagram credentials are configured

    Returns an empty list when MOCK_DISCOVERY=True or no credentials are
    configured for any provider. The orchestrator falls back to
    MockDiscoveryProvider in that case.
    """
    # Forced mock mode — bypass all real providers
    if settings.MOCK_DISCOVERY:
        return []

    # No real credentials configured at all — fall back to mock
    if not (
        settings.reddit_credentials_configured()
        or settings.youtube_credentials_configured()
        or settings.instagram_credentials_configured()
    ):
        return []

    providers: list[BaseDiscoveryProvider] = []

    # Reddit (primary source — text-rich, ideal for OCEAN scoring)
    if settings.reddit_credentials_configured():
        try:
            from app.ml.discovery.reddit_provider import RedditProvider
            providers.append(RedditProvider())
        except Exception as exc:
            logger.warning("RedditProvider failed to initialise: %s", exc)

    # YouTube (secondary source — comment-based text signals)
    if settings.youtube_credentials_configured():
        try:
            from app.ml.discovery.youtube_provider import YouTubeProvider
            providers.append(YouTubeProvider())
        except Exception as exc:
            logger.warning("YouTubeProvider failed to initialise: %s", exc)

    # Instagram (tertiary source — poster + commenter discovery)
    if settings.instagram_credentials_configured():
        try:
            from app.ml.discovery.instagram_provider import InstagramProvider
            providers.append(InstagramProvider())
        except Exception as exc:
            logger.warning("InstagramProvider failed to initialise: %s", exc)

    return providers


def _select_provider(
    registry: list[BaseDiscoveryProvider],
    product_category: str,
    product_region: str,
) -> BaseDiscoveryProvider | None:
    """
    Pick the highest-priority provider that supports the product's category
    and region.  Returns None if no real provider matches (triggers mock).

    Selection rules:
      1. Exact category match beats wildcard match.
      2. Exact region match beats wildcard match.
      3. Among equally-ranked providers, first in registry wins.
    """
    cat = (product_category or "").lower()
    region = (product_region or "").lower()

    exact: list[BaseDiscoveryProvider] = []
    wildcard: list[BaseDiscoveryProvider] = []

    for p in registry:
        cats = [c.lower() for c in p.supported_categories]
        regions = [r.lower() for r in p.supported_regions]

        cat_match = cat in cats or "*" in cats
        region_match = region in regions or "*" in regions

        if not (cat_match and region_match):
            continue

        if cat in cats and region in regions:
            exact.append(p)
        else:
            wildcard.append(p)

    if exact:
        return exact[0]
    if wildcard:
        return wildcard[0]
    return None


def _get_provider(
    product_category: str = "",
    product_region: str = "",
) -> BaseDiscoveryProvider:
    """
    Return the appropriate discovery provider for a given product.

    Selection order:
      1. Best real provider from registry (Reddit → YouTube based on credentials)
      2. MockDiscoveryProvider as fallback when no real credentials are configured

    Uses MockDiscoveryProvider when:
      - MOCK_DISCOVERY=True in .env
      - Neither Reddit nor YouTube credentials are configured
      - No registered provider supports the product's category/region
    """
    if settings.MOCK_DISCOVERY:
        logger.info("DiscoveryOrchestrator: MOCK_DISCOVERY=True — using MockDiscoveryProvider")
        from app.ml.discovery.mock_provider import MockDiscoveryProvider
        return MockDiscoveryProvider(delay_ms=0)

    registry = _build_provider_registry()
    provider = _select_provider(registry, product_category, product_region)

    if provider is None:
        if settings.FALLBACK_TO_MOCK_ON_ERROR:
            logger.warning(
                "No real provider found for category=%r region=%r — falling back to MockDiscoveryProvider. "
                "Set FALLBACK_TO_MOCK_ON_ERROR=false to surface this as a job failure instead.",
                product_category, product_region,
            )
            from app.ml.discovery.mock_provider import MockDiscoveryProvider
            return MockDiscoveryProvider(delay_ms=0)
        raise RuntimeError(
            "No real discovery provider could be initialised for "
            f"category={product_category!r} region={product_region!r}. "
            "Configure at least one credential set (REDDIT_CLIENT_ID+SECRET, "
            "YOUTUBE_API_KEY, or valid Instagram credentials) and ensure the "
            "provider initialises without errors. "
            "Set FALLBACK_TO_MOCK_ON_ERROR=true to use MockDiscoveryProvider instead."
        )

    logger.info(
        "DiscoveryOrchestrator: selected provider=%s for category=%r region=%r",
        provider.name, product_category, product_region,
    )
    return provider


class DiscoveryOrchestrator:
    """
    Runs the full discovery + content-collection pipeline for one job.
    Called as a FastAPI BackgroundTask.
    """

    async def run(self, job_id: UUID, db: AsyncSession) -> None:
        """
        Execute the full discovery pipeline for *job_id*.

        Stages:
          1. Load job + product from DB.
          2. Extract keywords from motivation categories.
          3. Discover users via provider.
          4. Persist discovered users.
          5. Collect content for each user.
          6. Persist content.
          7. Mark job complete and advance product.pipeline_step.
        """
        _log = f"[DISCOVERY job={str(job_id)[:8]}]"
        logger.info("%s START", _log)

        # ── 1. Load job ───────────────────────────────────────────────────────
        job: DiscoveryJob | None = await db.get(DiscoveryJob, job_id)
        if not job:
            logger.error("%s job not found in DB", _log)
            return

        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        await db.commit()

        try:
            # ── 2. Load product + keywords ────────────────────────────────────
            from app.models.product import Product, ProductStatus
            from app.crud.motivation import get_motivations_by_product

            product = await db.get(Product, job.product_id)
            if not product:
                raise ValueError(f"Product {job.product_id} not found")

            # Merge keywords from all motivation OCEAN profiles
            all_keywords: list[str] = list(product.keywords or [])
            categories = await get_motivations_by_product(db, product.id)
            for cat in categories:
                if cat.ocean_profile:
                    all_keywords.extend(cat.ocean_profile.search_keywords or [])
                    all_keywords.extend(cat.ocean_profile.interest_tags or [])

            # Deduplicate while preserving order
            seen_kw: set[str] = set()
            unique_keywords: list[str] = []
            for kw in all_keywords:
                kw_clean = kw.strip().lower()
                if kw_clean and kw_clean not in seen_kw:
                    seen_kw.add(kw_clean)
                    unique_keywords.append(kw_clean)

            logger.info(
                "%s merged %d unique keywords from %d motivation categories",
                _log, len(unique_keywords), len(categories),
            )

            # ── Expand with similar product keywords ──────────────────────────
            # discovery_service pre-populates job.search_config["similar_products"]
            # with a list of {name, keywords, similarity_score} dicts before this
            # orchestrator is called. We merge those keywords here so providers
            # search for discussions about similar products in the same run.
            sp_entries: list[dict] = (job.search_config or {}).get("similar_products", [])
            sp_kw_added = 0
            for sp_entry in sp_entries:
                for kw in sp_entry.get("keywords", []):
                    kw_clean = kw.strip().lower()
                    if kw_clean and kw_clean not in seen_kw:
                        seen_kw.add(kw_clean)
                        unique_keywords.append(kw_clean)
                        sp_kw_added += 1

            if sp_kw_added:
                logger.info(
                    "%s added %d keywords from %d similar products (total=%d)",
                    _log, sp_kw_added, len(sp_entries), len(unique_keywords),
                )

            # ── 3. Select provider + discover ─────────────────────────────────
            provider = _get_provider(
                product_category=product.category or "",
                product_region=product.target_country or "",
            )
            job.provider_name = provider.name
            job.sources = [provider.platform]
            await db.commit()

            logger.info(
                "%s provider=%s keywords=%d max_users=%d city=%s",
                _log, provider.name, len(unique_keywords),
                job.max_users, product.target_city,
            )

            raw_users = await provider.discover_users(
                keywords=unique_keywords,
                target_city=product.target_city,
                max_users=job.max_users,
                search_config=job.search_config or {},
            )
            logger.info("%s discovered %d raw users", _log, len(raw_users))

            # ── 4. Persist discovered users ───────────────────────────────────
            job.status = "collecting"
            await db.commit()

            persisted_users: list[tuple[DiscoveredUser, RawDiscoveredUser]] = []
            for raw in raw_users:
                du = await self._upsert_user(db, job, raw)
                if du:
                    persisted_users.append((du, raw))

            job.users_discovered = len(persisted_users)
            await db.commit()
            logger.info(
                "%s persisted %d discovered users", _log, len(persisted_users)
            )

            # ── 5 + 6. Collect + persist content (batched) ────────────────────
            batch_size = settings.DISCOVERY_CONTENT_BATCH_SIZE
            for i in range(0, len(persisted_users), batch_size):
                batch = persisted_users[i: i + batch_size]
                for du, raw in batch:
                    try:
                        content_items = await provider.collect_content(
                            raw,
                            max_items=settings.DISCOVERY_CONTENT_PER_USER,
                        )
                        await self._persist_content(db, du.id, content_items)
                        du.content_collected = True
                        job.users_content_collected += 1
                    except Exception as exc:
                        logger.warning(
                            "%s content collection failed for %s: %s",
                            _log, raw.username, exc,
                        )
                await db.commit()
                logger.info(
                    "%s content collected: %d / %d",
                    _log, job.users_content_collected, len(persisted_users),
                )

            # ── 7. Mark job + product complete ────────────────────────────────
            job.status = "completed"
            job.completed_at = datetime.now(timezone.utc)

            product.status = ProductStatus.discovering
            product.pipeline_step = 5
            await db.commit()

            logger.info(
                "%s DONE — %d users discovered, %d with content",
                _log, job.users_discovered, job.users_content_collected,
            )

            # ── 8. Auto-trigger NLP pipeline ──────────────────────────────────
            # Only fire if there is content to process.
            if job.users_content_collected > 0:
                from app.workers.dispatch import dispatch
                logger.info(
                    "%s auto-triggering NLP for %d users",
                    _log, job.users_content_collected,
                )
                dispatch("nlp", str(product.id))

        except Exception as exc:
            import traceback
            tb = traceback.format_exc()
            logger.exception("%s FAILED: %s", _log, exc)
            job.status = "failed"
            job.error_message = f"{type(exc).__name__}: {exc}\n{tb}"[:1000]
            await db.commit()

    async def _upsert_user(
        self,
        db: AsyncSession,
        job: DiscoveryJob,
        raw: RawDiscoveredUser,
    ) -> DiscoveredUser | None:
        """
        Insert a discovered user, skipping duplicates (same platform+user+job).
        Returns the persisted DiscoveredUser or None if skipped.
        """
        from sqlalchemy import select
        from app.models.discovery import DiscoveredUser

        # Check for existing user in this job (ON CONFLICT equivalent)
        existing = await db.execute(
            select(DiscoveredUser).where(
                DiscoveredUser.platform == raw.platform,
                DiscoveredUser.platform_user_id == raw.platform_user_id,
                DiscoveredUser.discovery_job_id == job.id,
            )
        )
        if existing.scalar_one_or_none():
            return None  # already persisted for this job

        du = DiscoveredUser(
            discovery_job_id=job.id,
            product_id=job.product_id,
            platform=raw.platform,
            source_provider=raw.source_provider,
            platform_user_id=raw.platform_user_id,
            username=raw.username,
            display_name=raw.display_name,
            bio=raw.bio,
            location=raw.location,
            location_confidence=raw.location_confidence,
            follower_count=raw.follower_count,
            post_count=raw.post_count,
            profile_url=raw.profile_url,
            raw_profile=raw.raw_profile,
        )
        db.add(du)
        await db.flush()  # assigns du.id without committing
        return du

    async def _persist_content(
        self,
        db: AsyncSession,
        user_id: UUID,
        items: list[ContentItem],
    ) -> None:
        """Bulk-insert content items for a user."""
        for item in items:
            uc = UserContent(
                user_id=user_id,
                content_type=item.content_type,
                content_text=item.content_text,
                source_url=item.source_url,
                engagement=item.engagement,
                posted_at=item.posted_at,
            )
            db.add(uc)
