"""
Lead validation, inspection, analytics, and export queries.

This module exists to answer: "Does the ranking system produce useful leads?"

Key additions over the basic matching CRUD:
  - get_lead_inspection()     Full profile: OCEAN + NLP + sample content + quality flags
  - get_lead_analytics()      Score distributions, confidence stats, calibration notes
  - get_leads_for_export()    All ranked leads as flat dicts for CSV/JSON export
"""
from __future__ import annotations

import statistics as pystats
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discovery import DiscoveredUser, UserContent
from app.models.matching import LeadMatch
from app.models.motivation import MotivationCategory
from app.models.nlp import UserNlpFeatures
from app.models.ocean import UserOceanScore

# ── Quality thresholds ────────────────────────────────────────────────────────

QUALITY_MIN_CONFIDENCE = 40.0
QUALITY_MIN_TOKENS = 30
QUALITY_MIN_INTEREST_TAGS = 3
QUALITY_SCORING_METHODS_FLAGGED = {"insufficient_content"}

# Number of content samples included in an inspection response
INSPECTION_CONTENT_SAMPLES = 5
INSPECTION_SAMPLE_MAX_CHARS = 400


def _quality_flags(
    confidence: float,
    scoring_method: str,
    total_tokens: int,
    interest_tag_count: int,
) -> list[str]:
    """Return a list of quality warning strings for a lead."""
    flags: list[str] = []
    if scoring_method in QUALITY_SCORING_METHODS_FLAGGED:
        flags.append("INSUFFICIENT_CONTENT: OCEAN scored at neutral defaults due to too little text.")
    if scoring_method == "heuristic":
        flags.append("HEURISTIC_OCEAN: Personality scored via Empath heuristic, not LLM inference.")
    if confidence < QUALITY_MIN_CONFIDENCE:
        flags.append(f"LOW_CONFIDENCE: Match confidence {confidence:.0f}/100 is below threshold ({QUALITY_MIN_CONFIDENCE:.0f}).")
    if total_tokens < QUALITY_MIN_TOKENS:
        flags.append(f"LOW_TOKEN_COUNT: Only {total_tokens} content tokens — insufficient for reliable NLP.")
    if interest_tag_count < QUALITY_MIN_INTEREST_TAGS:
        flags.append(f"THIN_INTEREST_SIGNAL: Only {interest_tag_count} Empath interest tags detected.")
    return flags


# ── Lead inspection ───────────────────────────────────────────────────────────

async def get_lead_inspection(
    db: AsyncSession,
    product_id: UUID,
    user_id: UUID,
) -> dict | None:
    """
    Return the full inspection payload for one lead:
      - Basic profile
      - OCEAN personality dimensions
      - Interest tags + top Empath categories
      - Content quality metrics
      - Top content samples (by engagement)
      - All motivation category scores
      - Quality flags (human-readable warnings)

    Returns None if user has no matches for this product.
    """
    # ── User ──────────────────────────────────────────────────────────────────
    user_r = await db.execute(
        select(DiscoveredUser).where(DiscoveredUser.id == user_id)
    )
    user: DiscoveredUser | None = user_r.scalar_one_or_none()
    if not user:
        return None

    # ── Matches ───────────────────────────────────────────────────────────────
    match_r = await db.execute(
        select(LeadMatch, MotivationCategory)
        .join(MotivationCategory, LeadMatch.motivation_category_id == MotivationCategory.id)
        .where(
            LeadMatch.product_id == product_id,
            LeadMatch.user_id == user_id,
        )
        .order_by(LeadMatch.final_score.desc())
    )
    match_rows = match_r.all()
    if not match_rows:
        return None

    # ── OCEAN score ───────────────────────────────────────────────────────────
    ocean_r = await db.execute(
        select(UserOceanScore).where(UserOceanScore.user_id == user_id)
    )
    ocean: UserOceanScore | None = ocean_r.scalar_one_or_none()

    # ── NLP features ──────────────────────────────────────────────────────────
    nlp_r = await db.execute(
        select(UserNlpFeatures).where(UserNlpFeatures.user_id == user_id)
    )
    nlp: UserNlpFeatures | None = nlp_r.scalar_one_or_none()

    # ── Content samples ───────────────────────────────────────────────────────
    content_r = await db.execute(
        select(UserContent)
        .where(
            UserContent.user_id == user_id,
            UserContent.content_type.in_(["post", "comment", "bio"]),
        )
        .order_by(UserContent.engagement.desc())
        .limit(INSPECTION_CONTENT_SAMPLES)
    )
    content_rows = list(content_r.scalars().all())

    # ── Build match records ───────────────────────────────────────────────────
    best_match = None
    all_scores = []
    for match, cat in match_rows:
        entry = {
            "motivation_category_id": str(cat.id),
            "motivation_category": cat.name,
            "final_score": match.final_score,
            "ocean_score": match.ocean_score,
            "embedding_score": match.embedding_score,
            "interest_score": match.interest_score,
            "confidence": match.confidence,
            "reasoning": match.reasoning,
        }
        all_scores.append(entry)
        if match.is_best_match:
            best_match = {"rank": match.rank, **entry}

    # ── Quality flags ─────────────────────────────────────────────────────────
    scoring_method = ocean.scoring_method if ocean else "unavailable"
    ocean_confidence = ocean.confidence if ocean else 0.0
    total_tokens = nlp.total_tokens if nlp else 0
    interest_tags = list(nlp.interest_tags or []) if nlp else []
    flags = _quality_flags(
        confidence=ocean_confidence,
        scoring_method=scoring_method,
        total_tokens=total_tokens,
        interest_tag_count=len(interest_tags),
    )

    # ── Top Empath categories ─────────────────────────────────────────────────
    raw_empath = dict(nlp.empath_scores or {}) if nlp else {}
    top_empath = sorted(raw_empath.items(), key=lambda x: x[1], reverse=True)[:10]
    empath_list = [{"category": k, "score": round(v, 4)} for k, v in top_empath]

    return {
        "user_id": str(user.id),
        "username": user.username,
        "display_name": user.display_name,
        "platform": user.platform,
        "profile_url": user.profile_url,
        "location": user.location,
        "location_confidence": user.location_confidence,
        "follower_count": user.follower_count,
        "content_quality": {
            "total_tokens": total_tokens,
            "vocabulary_richness": round(nlp.vocabulary_richness or 0.0, 4) if nlp else None,
            "avg_sentence_length": round(nlp.avg_sentence_length or 0.0, 2) if nlp else None,
            "num_content_items": len(content_rows),
        },
        "ocean_profile": {
            "openness": ocean.openness if ocean else None,
            "conscientiousness": ocean.conscientiousness if ocean else None,
            "extraversion": ocean.extraversion if ocean else None,
            "agreeableness": ocean.agreeableness if ocean else None,
            "neuroticism": ocean.neuroticism if ocean else None,
            "confidence": ocean_confidence,
            "scoring_method": scoring_method,
        },
        "interest_tags": interest_tags,
        "top_empath_categories": empath_list,
        "content_samples": [
            {
                "content_type": c.content_type,
                "content_text": c.content_text[:INSPECTION_SAMPLE_MAX_CHARS],
                "engagement": c.engagement,
                "source_url": c.source_url,
            }
            for c in content_rows
        ],
        "best_match": best_match,
        "all_category_scores": all_scores,
        "quality_flags": flags,
        "passes_quality_filter": len(flags) == 0,
    }


# ── Analytics ─────────────────────────────────────────────────────────────────

def _distribution_stats(values: list[float]) -> dict:
    """Compute descriptive statistics for a list of floats."""
    if not values:
        return {"count": 0, "min": None, "max": None, "mean": None,
                "median": None, "p25": None, "p75": None, "std_dev": None}
    sorted_v = sorted(values)
    n = len(sorted_v)

    def percentile(p: float) -> float:
        idx = p / 100.0 * (n - 1)
        lo, hi = int(idx), min(int(idx) + 1, n - 1)
        return sorted_v[lo] + (idx - lo) * (sorted_v[hi] - sorted_v[lo])

    return {
        "count": n,
        "min": round(sorted_v[0], 2),
        "max": round(sorted_v[-1], 2),
        "mean": round(pystats.mean(values), 2),
        "median": round(pystats.median(values), 2),
        "p25": round(percentile(25), 2),
        "p75": round(percentile(75), 2),
        "std_dev": round(pystats.stdev(values) if n > 1 else 0.0, 2),
    }


def _histogram(values: list[float], buckets: int = 10) -> list[dict]:
    """Build a histogram with `buckets` equal-width bins from 0–100."""
    bucket_size = 100.0 / buckets
    counts = [0] * buckets
    for v in values:
        idx = min(int(v / bucket_size), buckets - 1)
        counts[idx] += 1
    return [
        {
            "range": f"{int(i * bucket_size)}–{int((i + 1) * bucket_size)}",
            "count": counts[i],
        }
        for i in range(buckets)
    ]


def _calibration_notes(
    final_scores: list[float],
    confidences: list[float],
    scoring_methods: list[str],
) -> list[str]:
    """
    Generate honest, data-driven observations about scoring behaviour.
    These help a reviewer assess whether the ranking is reliable.
    """
    notes: list[str] = []
    if not final_scores:
        return ["No ranked leads available for analysis."]

    # Score spread
    std = pystats.stdev(final_scores) if len(final_scores) > 1 else 0.0
    mean = pystats.mean(final_scores)
    if std < 8.0:
        notes.append(
            f"Scores are tightly clustered (mean={mean:.1f}, σ={std:.1f}). "
            "Ranking is based on small differences — top vs bottom leads may not be strongly differentiated. "
            "Review top 10% and bottom 10% manually to assess separation quality."
        )
    elif std < 15.0:
        notes.append(
            f"Moderate score spread (mean={mean:.1f}, σ={std:.1f}). "
            "Rankings provide reasonable differentiation. "
            "Leads scoring ≥75 are likely strong candidates; below 65 warrant manual review."
        )
    else:
        notes.append(
            f"Good score spread (mean={mean:.1f}, σ={std:.1f}). "
            "The ranking system is producing meaningful differentiation between leads."
        )

    # OCEAN floor note
    notes.append(
        "OCEAN similarity scores have a mathematical floor of ~59 for random profiles. "
        "Scores above 75 indicate genuine personality alignment; below 65 indicates weak alignment. "
        "Absolute values below 65 do not mean 'poor lead' — use relative ranking, not absolute thresholds."
    )

    # Confidence concern
    if confidences:
        low_conf = sum(1 for c in confidences if c < QUALITY_MIN_CONFIDENCE)
        pct_low = low_conf / len(confidences) * 100
        if pct_low > 30:
            notes.append(
                f"{pct_low:.0f}% of ranked leads have confidence below {QUALITY_MIN_CONFIDENCE}. "
                "Most users had insufficient content for reliable psychographic scoring. "
                "Consider filtering with min_confidence=40 to see only reliable leads."
            )

    # Insufficient-content warning
    insuff = sum(1 for m in scoring_methods if m == "insufficient_content")
    if insuff > 0:
        pct = insuff / len(scoring_methods) * 100
        notes.append(
            f"{insuff} leads ({pct:.0f}%) were scored with neutral OCEAN defaults "
            "(insufficient_content method). Their ranking is driven by embedding and interest "
            "signals only, not personality. Filter these with min_confidence=40."
        )

    # Embedding signal note
    notes.append(
        "Embedding similarity compares casual social media posts to formal marketing descriptions "
        "— expect scores of 60–80 as normal, not 90+. "
        "This component provides topical direction, not strong discrimination."
    )

    return notes


async def get_lead_analytics(
    db: AsyncSession,
    product_id: UUID,
    min_confidence: float = 0.0,
) -> dict:
    """
    Compute score distributions and calibration notes for all ranked leads
    of a product. Expensive — runs in O(N) over all best-match rows.
    """
    # Load all best-match lead rows
    result = await db.execute(
        select(LeadMatch, UserOceanScore, UserNlpFeatures)
        .join(UserOceanScore, LeadMatch.user_id == UserOceanScore.user_id, isouter=True)
        .join(UserNlpFeatures, LeadMatch.user_id == UserNlpFeatures.user_id, isouter=True)
        .where(
            LeadMatch.product_id == product_id,
            LeadMatch.is_best_match == True,  # noqa: E712
            LeadMatch.confidence >= min_confidence,
        )
        .order_by(LeadMatch.rank.asc().nullslast())
    )
    rows = result.all()

    if not rows:
        return {
            "product_id": str(product_id),
            "total_ranked": 0,
            "quality_summary": {
                "passing_all_filters": 0,
                "pct_passing": 0.0,
                "flagged_low_confidence": 0,
                "flagged_heuristic_ocean": 0,
                "flagged_insufficient_content": 0,
                "recommended_min_confidence": QUALITY_MIN_CONFIDENCE,
            },
            "final_score_distribution": {**_distribution_stats([]), "histogram": _histogram([])},
            "confidence_distribution": _distribution_stats([]),
            "ocean_score_distribution": _distribution_stats([]),
            "embedding_score_distribution": _distribution_stats([]),
            "interest_score_distribution": _distribution_stats([]),
            "top_motivation_categories": [],
            "calibration_notes": ["No ranked leads available for analysis."],
        }

    # Collect parallel arrays
    final_scores, confidences, ocean_scores, emb_scores, int_scores = [], [], [], [], []
    scoring_methods: list[str] = []
    motiv_cat_counts: dict[str, int] = {}
    quality_pass = 0
    low_confidence_count = 0
    heuristic_count = 0
    insufficient_count = 0

    for lead, ocean, nlp in rows:
        final_scores.append(lead.final_score)
        confidences.append(lead.confidence)
        ocean_scores.append(lead.ocean_score)
        emb_scores.append(lead.embedding_score)
        int_scores.append(lead.interest_score)

        sm = ocean.scoring_method if ocean else "unavailable"
        scoring_methods.append(sm)
        total_tokens = nlp.total_tokens if nlp else 0
        interest_tag_count = len(nlp.interest_tags or []) if nlp else 0

        flags = _quality_flags(lead.confidence, sm, total_tokens, interest_tag_count)
        if not flags:
            quality_pass += 1
        if lead.confidence < QUALITY_MIN_CONFIDENCE:
            low_confidence_count += 1
        if sm == "heuristic":
            heuristic_count += 1
        if sm == "insufficient_content":
            insufficient_count += 1

    # Motivation category distribution
    cat_result = await db.execute(
        select(LeadMatch, MotivationCategory)
        .join(MotivationCategory, LeadMatch.motivation_category_id == MotivationCategory.id)
        .where(
            LeadMatch.product_id == product_id,
            LeadMatch.is_best_match == True,  # noqa: E712
        )
    )
    for m, cat in cat_result.all():
        motiv_cat_counts[cat.name] = motiv_cat_counts.get(cat.name, 0) + 1

    top_cats = sorted(motiv_cat_counts.items(), key=lambda x: x[1], reverse=True)

    return {
        "product_id": str(product_id),
        "total_ranked": len(rows),
        "quality_summary": {
            "passing_all_filters": quality_pass,
            "pct_passing": round(quality_pass / len(rows) * 100, 1) if rows else 0.0,
            "flagged_low_confidence": low_confidence_count,
            "flagged_heuristic_ocean": heuristic_count,
            "flagged_insufficient_content": insufficient_count,
            "recommended_min_confidence": QUALITY_MIN_CONFIDENCE,
        },
        "final_score_distribution": {
            **_distribution_stats(final_scores),
            "histogram": _histogram(final_scores),
        },
        "confidence_distribution": _distribution_stats(confidences),
        "ocean_score_distribution": _distribution_stats(ocean_scores),
        "embedding_score_distribution": _distribution_stats(emb_scores),
        "interest_score_distribution": _distribution_stats(int_scores),
        "top_motivation_categories": [
            {"category": name, "count": count}
            for name, count in top_cats
        ],
        "calibration_notes": _calibration_notes(final_scores, confidences, scoring_methods),
    }


# ── Export ────────────────────────────────────────────────────────────────────

async def get_leads_summary(db: AsyncSession, product_id: UUID) -> dict:
    """
    Lightweight aggregate stats for the dashboard product overview card.
    Single query — avoids loading the full analytics computation on every page.
    """
    from sqlalchemy import desc as sa_desc

    agg_r = await db.execute(
        select(
            func.count(LeadMatch.id),
            func.avg(LeadMatch.final_score),
            func.max(LeadMatch.final_score),
        ).where(
            LeadMatch.product_id == product_id,
            LeadMatch.is_best_match == True,  # noqa: E712
        )
    )
    count, avg, top = agg_r.one()

    cat_r = await db.execute(
        select(MotivationCategory.name, func.count(LeadMatch.id).label("cnt"))
        .join(LeadMatch, LeadMatch.motivation_category_id == MotivationCategory.id)
        .where(
            LeadMatch.product_id == product_id,
            LeadMatch.is_best_match == True,  # noqa: E712
        )
        .group_by(MotivationCategory.name)
        .order_by(sa_desc("cnt"))
        .limit(1)
    )
    top_cat_row = cat_r.first()

    return {
        "total_ranked": int(count) if count else 0,
        "avg_score": round(float(avg), 1) if avg else None,
        "top_score": round(float(top), 1) if top else None,
        "top_category": top_cat_row[0] if top_cat_row else None,
    }


async def get_leads_for_export(
    db: AsyncSession,
    product_id: UUID,
    min_score: float = 0.0,
    min_confidence: float = 0.0,
    max_rows: int = 5000,
) -> list[dict]:
    """
    Return all ranked leads as flat dicts suitable for CSV/JSON export.
    Includes OCEAN dimensions from the user's ocean score row.
    """
    result = await db.execute(
        select(LeadMatch, DiscoveredUser, MotivationCategory, UserOceanScore, UserNlpFeatures)
        .join(DiscoveredUser, LeadMatch.user_id == DiscoveredUser.id)
        .join(MotivationCategory, LeadMatch.motivation_category_id == MotivationCategory.id)
        .join(UserOceanScore, LeadMatch.user_id == UserOceanScore.user_id, isouter=True)
        .join(UserNlpFeatures, LeadMatch.user_id == UserNlpFeatures.user_id, isouter=True)
        .where(
            LeadMatch.product_id == product_id,
            LeadMatch.is_best_match == True,  # noqa: E712
            LeadMatch.final_score >= min_score,
            LeadMatch.confidence >= min_confidence,
        )
        .order_by(LeadMatch.rank.asc().nullslast())
        .limit(max_rows)
    )
    rows = result.all()

    export_rows = []
    for lead, user, cat, ocean, nlp in rows:
        scoring_method = ocean.scoring_method if ocean else "unavailable"
        total_tokens = nlp.total_tokens if nlp else 0
        interest_tags = list(nlp.interest_tags or []) if nlp else []
        flags = _quality_flags(lead.confidence, scoring_method, total_tokens, len(interest_tags))

        export_rows.append({
            "rank": lead.rank,
            "username": user.username,
            "display_name": user.display_name or "",
            "platform": user.platform,
            "profile_url": user.profile_url or "",
            "location": user.location or "",
            "location_confidence": user.location_confidence,
            "follower_count": user.follower_count,
            "best_motivation_category": cat.name,
            "final_score": lead.final_score,
            "ocean_component_score": lead.ocean_score,
            "embedding_component_score": lead.embedding_score,
            "interest_component_score": lead.interest_score,
            "confidence": lead.confidence,
            "openness": ocean.openness if ocean else None,
            "conscientiousness": ocean.conscientiousness if ocean else None,
            "extraversion": ocean.extraversion if ocean else None,
            "agreeableness": ocean.agreeableness if ocean else None,
            "neuroticism": ocean.neuroticism if ocean else None,
            "ocean_scoring_method": scoring_method,
            "interest_tags": "; ".join(interest_tags[:10]),
            "total_tokens": total_tokens,
            "reasoning": " | ".join(lead.reasoning or []),
            "quality_flags": "; ".join(flags) if flags else "PASS",
        })

    return export_rows
