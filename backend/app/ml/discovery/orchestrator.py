"""
DiscoveryOrchestrator — coordinates discovery providers for a product.

Responsibilities:
  1. Build a list of ALL configured providers.
  2. Run all providers' discover_users() concurrently (asyncio.gather).
     Failures on individual providers are caught and logged; other
     providers continue regardless.
  3. Aggregate users from all successful providers.
  4. Persist RawDiscoveredUser → DiscoveredUser in the DB (with dedup).
  5. Call collect_content() per user and persist UserContent.
  6. Update DiscoveryJob status counters throughout.

Provider isolation guarantee:
  Any provider that raises during discover_users() is skipped and its
  error recorded in job.search_config["provider_results"]. The pipeline
  continues as long as at least one provider returns users.

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


async def _build_provider_registry() -> list[BaseDiscoveryProvider]:
    """
    Return all available real providers in priority order.

    Priority order (highest first):
      1. RedditProvider     — if Reddit credentials are configured
      2. YouTubeProvider    — if YouTube API key is configured
      3. InstagramProvider  — if Instagram credentials are configured
      4. GoogleReviewsProvider — if Google Places API key is configured

    Returns an empty list when MOCK_DISCOVERY=True or no credentials are
    configured for any provider. The orchestrator falls back to
    MockDiscoveryProvider in that case.

    InstagramProvider.__init__ performs a synchronous blocking network login.
    It is initialised via asyncio.to_thread() so the event loop is never blocked.
    """
    import asyncio

    if settings.MOCK_DISCOVERY:
        return []

    if not (
        settings.reddit_credentials_configured()
        or settings.youtube_credentials_configured()
        or settings.instagram_credentials_configured()
        or settings.google_places_credentials_configured()
    ):
        return []

    providers: list[BaseDiscoveryProvider] = []

    if settings.reddit_credentials_configured():
        try:
            from app.ml.discovery.reddit_provider import RedditProvider
            providers.append(RedditProvider())
        except Exception as exc:
            logger.warning("RedditProvider failed to initialise: %s", exc)

    if settings.youtube_credentials_configured():
        try:
            from app.ml.discovery.youtube_provider import YouTubeProvider
            providers.append(YouTubeProvider())
        except Exception as exc:
            logger.warning("YouTubeProvider failed to initialise: %s", exc)

    if settings.instagram_credentials_configured():
        # Run blocking login in a thread so the event loop is not frozen.
        try:
            from app.ml.discovery.instagram_provider import InstagramProvider
            provider = await asyncio.wait_for(
                asyncio.to_thread(InstagramProvider),
                timeout=30.0,
            )
            providers.append(provider)
        except asyncio.TimeoutError:
            logger.warning("InstagramProvider init timed out (30s) — skipping")
        except Exception as exc:
            logger.warning("InstagramProvider failed to initialise: %s", exc)

    if settings.google_places_credentials_configured():
        try:
            from app.ml.discovery.google_reviews_provider import GoogleReviewsProvider
            providers.append(GoogleReviewsProvider())
        except Exception as exc:
            logger.warning("GoogleReviewsProvider failed to initialise: %s", exc)

    return providers


async def _get_all_providers(
    product_category: str = "",
    product_region: str = "",
    preferred_provider: str = "",
) -> list[BaseDiscoveryProvider]:
    """
    Return ALL configured and available providers to run for a discovery job.

    If preferred_provider is set (via job.search_config["preferred_provider"]),
    that provider is moved to the front of the list so it runs first.  All
    other configured providers still run after it.

    Falls back to [MockDiscoveryProvider] when:
      - MOCK_DISCOVERY=True, OR
      - No real credentials are configured AND FALLBACK_TO_MOCK_ON_ERROR=True.

    Raises RuntimeError when no providers are available and
    FALLBACK_TO_MOCK_ON_ERROR=False.
    """
    if settings.MOCK_DISCOVERY:
        logger.info("DiscoveryOrchestrator: MOCK_DISCOVERY=True — using MockDiscoveryProvider")
        from app.ml.discovery.mock_provider import MockDiscoveryProvider
        return [MockDiscoveryProvider(delay_ms=0)]

    registry = await _build_provider_registry()

    if not registry:
        if settings.FALLBACK_TO_MOCK_ON_ERROR:
            logger.warning(
                "DiscoveryOrchestrator: no real providers configured — "
                "falling back to MockDiscoveryProvider. "
                "Set FALLBACK_TO_MOCK_ON_ERROR=false to surface this as a failure."
            )
            from app.ml.discovery.mock_provider import MockDiscoveryProvider
            return [MockDiscoveryProvider(delay_ms=0)]
        raise RuntimeError(
            "No discovery providers are configured. "
            "Set at least one of: REDDIT_USER_AGENT, YOUTUBE_API_KEY, "
            "GOOGLE_PLACES_API_KEY, or INSTAGRAM_USERNAME+PASSWORD. "
            "Set FALLBACK_TO_MOCK_ON_ERROR=true to use MockDiscoveryProvider instead."
        )

    # Move preferred_provider to the front, keep all others after it.
    if preferred_provider:
        pref_lower = preferred_provider.lower()
        front = [p for p in registry if p.name == pref_lower]
        rest  = [p for p in registry if p.name != pref_lower]
        if front:
            logger.info(
                "DiscoveryOrchestrator: preferred_provider=%s moved to front; "
                "remaining providers will also run: %s",
                preferred_provider, [p.name for p in rest],
            )
            return front + rest
        logger.warning(
            "DiscoveryOrchestrator: preferred_provider=%r not in registry "
            "(not configured or failed to init) — running all providers in default order",
            preferred_provider,
        )

    logger.info(
        "DiscoveryOrchestrator: %d provider(s) will run: %s",
        len(registry), [p.name for p in registry],
    )
    return registry


class DiscoveryOrchestrator:
    """
    Runs the full discovery + content-collection pipeline for one job.

    All configured providers are attempted sequentially.  A provider that
    raises an exception is logged and skipped; remaining providers continue.
    The job succeeds as long as at least one provider returns users with
    collectable content.
    """

    async def run(self, job_id: UUID, db: AsyncSession) -> None:
        """
        Execute the full discovery pipeline for *job_id*.

        Stages:
          1. Load job + product from DB.
          2. Extract keywords from motivation categories + similar products.
          3. Get all configured providers.
          4. Run each provider sequentially; catch + log failures per provider.
          5. Aggregate raw users from all successful providers.
          6. Persist discovered users (with dedup).
          7. Collect + persist content for each user (per-user try/except).
          8. Mark job complete and advance product.pipeline_step.
          9. Auto-trigger NLP if any content was collected.
        """
        _log = f"[DISCOVERY job={str(job_id)[:8]}]"
        logger.info("%s START", _log)

        job: DiscoveryJob | None = await db.get(DiscoveryJob, job_id)
        if not job:
            logger.error("%s job not found in DB", _log)
            return

        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        await db.commit()

        try:
            # ── 1. Load product + keywords ────────────────────────────────────
            from app.models.product import Product, ProductStatus
            from app.crud.motivation import get_motivations_by_product

            product = await db.get(Product, job.product_id)
            if not product:
                raise ValueError(f"Product {job.product_id} not found")

            # Immediately surface progress in the UI — users see step 5 while
            # providers are running instead of watching step 4 the whole time.
            product.status = ProductStatus.discovering
            product.pipeline_step = 5
            await db.commit()

            # ── Buyer-intent keyword assembly ─────────────────────────────────
            # ONLY search_keywords are used for provider queries.
            #
            # search_keywords: phrases buyers use in discussions/content
            #   → passed to YouTube, Instagram, Reddit, Google Reviews
            #
            # interest_tags: personality/lifestyle labels (e.g. "music production",
            #   "audio engineering") used for OCEAN scoring, matching, and
            #   handle generation — NOT for search.
            #   Passing them to Instagram search_users() finds businesses whose
            #   account names match those labels (e.g. music production studios),
            #   not individual buyers.
            categories = await get_motivations_by_product(db, product.id)
            all_keywords: list[str] = []
            for cat in categories:
                if cat.ocean_profile:
                    all_keywords.extend(cat.ocean_profile.search_keywords or [])
                    # interest_tags deliberately excluded here — they are used
                    # downstream in OCEAN scoring and matching only.

            seen_kw: set[str] = set()
            unique_keywords: list[str] = []
            for kw in all_keywords:
                kw_clean = kw.strip().lower()
                if kw_clean and kw_clean not in seen_kw:
                    seen_kw.add(kw_clean)
                    unique_keywords.append(kw_clean)

            logger.info(
                "%s built %d buyer-intent keywords from %d motivation categories "
                "(product.keywords excluded to avoid seller contamination)",
                _log, len(unique_keywords), len(categories),
            )

            # ── Location-scoped query injection ───────────────────────────────
            # Prepend location-qualified variants of the top queries so that
            # providers surface geographically relevant content first.
            # E.g. "work from home tips" + Chennai → "work from home tips Chennai"

            # Safety: derive city from target_location ("Chennai, India" → "Chennai")
            # when target_city was not stored explicitly (older products or API-created).
            _derived_city = (product.target_city or "").strip()
            if not _derived_city and product.target_location and "," in product.target_location:
                _derived_city = product.target_location.split(",")[0].strip()

            location_tag = _derived_city
            if not location_tag:
                location_tag = (product.target_country or "").strip()
            if location_tag and location_tag.lower() not in ("global", "worldwide", ""):
                location_variants: list[str] = []
                for kw in unique_keywords[:8]:  # top 8 queries get location variant
                    lv = f"{kw} {location_tag.lower()}"
                    if lv not in seen_kw:
                        seen_kw.add(lv)
                        location_variants.append(lv)
                # Insert location-scoped queries first — providers process them first
                unique_keywords = location_variants + unique_keywords
                logger.info(
                    "%s prepended %d location-scoped queries (location=%r)",
                    _log, len(location_variants), location_tag,
                )

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

            # ── 2. Get ALL configured providers ──────────────────────────────
            preferred = (job.search_config or {}).get("preferred_provider", "")
            providers = await _get_all_providers(
                product_category=product.category or "",
                product_region=product.target_country or "",
                preferred_provider=preferred,
            )

            # ── 3. Run all providers concurrently; isolate failures ───────────
            # asyncio.gather runs every provider in parallel — if two providers
            # each take 3 min, total is 3 min instead of 6 min.
            import asyncio as _asyncio_providers

            all_raw_with_provider: list[tuple[RawDiscoveredUser, BaseDiscoveryProvider]] = []
            provider_results: dict[str, dict] = {}
            tried_names: list[str] = []
            successful_platforms: list[str] = []

            async def _run_provider(
                p: BaseDiscoveryProvider,
            ) -> tuple[BaseDiscoveryProvider, list[RawDiscoveredUser], Exception | None]:
                logger.info(
                    "%s provider=%s START (keywords=%d max_users=%d)",
                    _log, p.name, len(unique_keywords), job.max_users,
                )
                try:
                    users = await p.discover_users(
                        keywords=unique_keywords,
                        target_city=_derived_city or product.target_city,
                        max_users=job.max_users,
                        search_config=job.search_config or {},
                    )
                    return p, users, None
                except Exception as exc:
                    return p, [], exc

            provider_outcomes: list[
                tuple[BaseDiscoveryProvider, list[RawDiscoveredUser], Exception | None]
            ] = await _asyncio_providers.gather(*[_run_provider(p) for p in providers])

            for provider, raw_users, exc in provider_outcomes:
                tried_names.append(provider.name)
                if exc:
                    logger.warning(
                        "%s provider=%s FAILED — skipping. Error: %s",
                        _log, provider.name, exc,
                    )
                    provider_results[provider.name] = {
                        "status": "failed",
                        "error": str(exc)[:300],
                    }
                else:
                    logger.info(
                        "%s provider=%s → %d users", _log, provider.name, len(raw_users)
                    )
                    for raw in raw_users:
                        all_raw_with_provider.append((raw, provider))
                    provider_results[provider.name] = {
                        "status": "ok",
                        "users_found": len(raw_users),
                    }
                    if raw_users and provider.platform not in successful_platforms:
                        successful_platforms.append(provider.platform)

            # If combined results exceed max_users, interleave round-robin so every
            # provider that found users contributes equally to the final pool.
            # A simple [:max_users] slice would silently drop later providers entirely.
            if job.max_users and len(all_raw_with_provider) > job.max_users:
                # Build per-provider pools (order-preserving)
                _pools: dict[str, list[tuple[RawDiscoveredUser, BaseDiscoveryProvider]]] = {}
                for _raw, _prov in all_raw_with_provider:
                    _pools.setdefault(_prov.name, []).append((_raw, _prov))

                _interleaved: list[tuple[RawDiscoveredUser, BaseDiscoveryProvider]] = []
                _provider_names = list(_pools.keys())
                _idx = 0
                while len(_interleaved) < job.max_users:
                    _contributed = False
                    for _name in _provider_names:
                        if _pools[_name] and len(_interleaved) < job.max_users:
                            _interleaved.append(_pools[_name].pop(0))
                            _contributed = True
                    if not _contributed:
                        break
                all_raw_with_provider = _interleaved
                logger.info(
                    "%s interleaved %d providers → capped to max_users=%d",
                    _log, len(_provider_names), job.max_users,
                )

            total_raw = len(all_raw_with_provider)
            logger.info(
                "%s all providers done — total raw users=%d results=%s",
                _log, total_raw, provider_results,
            )

            # Update job metadata: record which providers ran + their outcomes
            job.provider_name = "+".join(tried_names) if tried_names else "none"
            job.sources = list(successful_platforms)
            config = dict(job.search_config or {})
            config["provider_results"] = provider_results
            job.search_config = config
            await db.commit()

            # ── 4. Persist discovered users ───────────────────────────────────
            job.status = "collecting"
            await db.commit()

            # ── Location filtering ────────────────────────────────────────────
            # When a specific target city/country is set, deprioritise users
            # with unknown location so the lead pool is geographically relevant.
            # "confirmed" and "regional" users are always kept.
            # "unknown" users are admitted only if we don't have enough confirmed ones.
            _target_city = _derived_city or (product.target_city or "").strip()
            _target_country = (product.target_country or "").strip()
            _has_location_target = bool(_target_city) or bool(
                _target_country and _target_country.lower()
                not in ("global", "worldwide", "")
            )
            if _has_location_target:
                _confirmed = [
                    (r, p) for r, p in all_raw_with_provider
                    if r.location_confidence in ("confirmed", "regional")
                ]
                _unknown = [
                    (r, p) for r, p in all_raw_with_provider
                    if r.location_confidence == "unknown"
                ]
                _min_users = max(5, (job.max_users or 50) // 3)
                if len(_confirmed) >= _min_users:
                    # Enough confirmed users — prefer them. But guarantee every
                    # provider that contributed raw users still adds a minimum
                    # share: YouTube/Reddit commenters rarely expose their city
                    # in comments even when they are local buyers, so a hard
                    # "drop all unknowns" would silently zero out entire platforms.
                    _confirmed_provider_names = {p.name for _, p in _confirmed}
                    _supplement: list = []
                    # Each absent provider gets up to 25 % of the job cap
                    _floor = max(3, (job.max_users or 50) // 4)
                    _supplement_counts: dict[str, int] = {}
                    for _raw, _prov in _unknown:
                        if _prov.name not in _confirmed_provider_names:
                            _cnt = _supplement_counts.get(_prov.name, 0)
                            if _cnt < _floor:
                                _supplement.append((_raw, _prov))
                                _supplement_counts[_prov.name] = _cnt + 1
                    all_raw_with_provider = _confirmed + _supplement
                    if _supplement:
                        logger.info(
                            "%s location filter: supplemented %d users from "
                            "providers absent in confirmed set: %s",
                            _log, len(_supplement),
                            {k: v for k, v in _supplement_counts.items()},
                        )
                else:
                    # Not enough confirmed — pad with some unknowns to keep pool viable
                    _fill = max(0, _min_users - len(_confirmed))
                    all_raw_with_provider = _confirmed + _unknown[:_fill]
                logger.info(
                    "%s location filter: confirmed=%d unknown=%d → using %d users",
                    _log, len(_confirmed), len(_unknown), len(all_raw_with_provider),
                )

            # (discovered_user, raw_user, provider_that_found_them)
            persisted_users: list[tuple[DiscoveredUser, RawDiscoveredUser, BaseDiscoveryProvider]] = []
            for raw, src_provider in all_raw_with_provider:
                du = await self._upsert_user(db, job, raw)
                if du:
                    persisted_users.append((du, raw, src_provider))

            job.users_discovered = len(persisted_users)
            await db.commit()
            logger.info(
                "%s persisted %d discovered users (deduplicated from %d raw)",
                _log, len(persisted_users), total_raw,
            )

            # ── 5 + 6. Collect + persist content (concurrent HTTP, sequential DB) ─
            # HTTP fetches run concurrently within each batch (big speedup vs sequential).
            # DB writes stay sequential on the shared session (safe for AsyncSession).
            import asyncio as _asyncio

            async def _fetch(
                raw: RawDiscoveredUser,
                src: BaseDiscoveryProvider,
                max_items: int,
            ) -> tuple[list[ContentItem], Exception | None]:
                try:
                    return await src.collect_content(raw, max_items=max_items), None
                except Exception as exc:
                    return [], exc

            batch_size = settings.DISCOVERY_CONTENT_BATCH_SIZE
            for i in range(0, len(persisted_users), batch_size):
                batch = persisted_users[i: i + batch_size]

                # Fire all HTTP calls in this batch concurrently
                fetch_results: list[tuple[list[ContentItem], Exception | None]] = (
                    await _asyncio.gather(*[
                        _fetch(raw, src, settings.DISCOVERY_CONTENT_PER_USER)
                        for _, raw, src in batch
                    ])
                )

                # Persist sequentially (safe on single AsyncSession)
                for (du, raw, src_provider), (content_items, exc) in zip(batch, fetch_results):
                    if exc:
                        logger.warning(
                            "%s content collection failed for %s (%s): %s",
                            _log, raw.username, src_provider.name, exc,
                        )
                    elif content_items:
                        await self._persist_content(db, du.id, content_items)
                        du.content_collected = True
                        job.users_content_collected += 1

                await db.commit()
                logger.info(
                    "%s content collected: %d / %d",
                    _log, job.users_content_collected, len(persisted_users),
                )

            # ── 7. Classify discovered users ──────────────────────────────────
            # Runs before NLP so that business/competitor accounts are flagged
            # as pipeline_excluded=True. NLP, OCEAN, and matching skip them.
            # UNKNOWN accounts pass through but receive a score penalty in
            # matching.
            from app.services.classification_service import classify_job_users
            classification_summary = await classify_job_users(job.id, db)
            logger.info(
                "%s classification done — buyers=%d excluded=%d "
                "(businesses=%d competitors=%d) unknown=%d",
                _log,
                classification_summary["buyers"],
                classification_summary["excluded"],
                classification_summary["businesses"],
                classification_summary["competitors"],
                classification_summary["unknown"],
            )

            # ── 8. Mark job complete ──────────────────────────────────────────
            # product.status was already set to "discovering" (step 5) at the
            # start of this run so the UI shows progress immediately.
            job.status = "completed"
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()

            logger.info(
                "%s DONE — providers_tried=%s users_discovered=%d users_with_content=%d",
                _log, tried_names, job.users_discovered, job.users_content_collected,
            )

            # ── 9. Auto-trigger NLP — fires if any provider collected content ──
            if job.users_content_collected > 0:
                from app.services.nlp_service import start_nlp_background
                logger.info(
                    "%s auto-triggering NLP for %d users",
                    _log, job.users_content_collected,
                )
                await start_nlp_background(str(product.id))
            else:
                logger.warning(
                    "%s no content collected from any provider — NLP not triggered. "
                    "Provider results: %s",
                    _log, provider_results,
                )

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
        Insert a discovered user, skipping duplicates within this job
        (same platform + platform_user_id + job_id).
        Returns the persisted DiscoveredUser, or None if it was a duplicate.
        """
        from sqlalchemy import select

        existing = await db.execute(
            select(DiscoveredUser).where(
                DiscoveredUser.platform == raw.platform,
                DiscoveredUser.platform_user_id == raw.platform_user_id,
                DiscoveredUser.discovery_job_id == job.id,
            )
        )
        if existing.scalar_one_or_none():
            return None

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
        await db.flush()
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
