"""
Psychographic matching scorer.

Computes a composite match score between a discovered user and a product
motivation category using three independent signals:

  Component        Weight   Rationale
  ─────────────────────────────────────────────────────────────────────
  OCEAN similarity   50%    Core psychographic alignment — strongest signal.
                            Euclidean proximity in 5D personality space.
  Embedding sim.     25%    Semantic alignment between user content and
                            motivation description (all-MiniLM-L6-v2 vectors).
  Interest overlap   25%    Explicit topic/keyword match between user interest
                            tags and motivation interest tags + search keywords.

Scale: all inputs and outputs 0–100.

NOTE — OCEAN scale inversion:
  MotivationOceanProfile stores `emotional_stability` (0–10).
  UserOceanScore stores `neuroticism` (0–100).
  Conversion applied here: motiv_neuroticism = 100 − (emotional_stability × 10).
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.motivation import MotivationOceanProfile
    from app.models.ocean import UserOceanScore
    from app.models.nlp import UserNlpFeatures

# ── Composite weights ─────────────────────────────────────────────────────────

OCEAN_WEIGHT = 0.50
EMBEDDING_WEIGHT = 0.25
INTEREST_WEIGHT = 0.25

_DIMS = ("openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism")
_MAX_OCEAN_DIST = math.sqrt(5) * 100  # ≈ 223.6 — maximum Euclidean distance in [0,100]^5


# ── OCEAN similarity ──────────────────────────────────────────────────────────

def normalize_motivation_ocean(motiv: "MotivationOceanProfile") -> dict[str, float]:
    """
    Convert motivation OCEAN profile (0-10 scale) to 0-100 with neuroticism inversion.
    Returns dict keyed by the same dimension names used in UserOceanScore.
    """
    return {
        "openness":          _clamp10(motiv.openness) * 10.0,
        "conscientiousness": _clamp10(motiv.conscientiousness) * 10.0,
        "extraversion":      _clamp10(motiv.extraversion) * 10.0,
        "agreeableness":     _clamp10(motiv.agreeableness) * 10.0,
        # emotional_stability is the INVERSE of neuroticism
        "neuroticism":       100.0 - _clamp10(motiv.emotional_stability) * 10.0,
    }


def compute_ocean_similarity(
    user_score: "UserOceanScore",
    motiv_ocean_100: dict[str, float],
) -> float:
    """
    Euclidean distance-based similarity in 5D OCEAN space.

    Distance 0 → score 100 (identical personality profile).
    Max distance (√5 × 100 ≈ 223.6) → score 0.

    Returns 0–100 (float, 2 decimal places).
    """
    user_vec = [getattr(user_score, d) for d in _DIMS]
    motiv_vec = [motiv_ocean_100[d] for d in _DIMS]

    dist_sq = sum((u - m) ** 2 for u, m in zip(user_vec, motiv_vec))
    dist = math.sqrt(dist_sq)
    return _clamp100((1.0 - dist / _MAX_OCEAN_DIST) * 100.0)


# ── Embedding similarity ──────────────────────────────────────────────────────

def compute_embedding_similarity(
    user_vec: list[float] | None,
    motiv_vec: list[float] | None,
) -> float:
    """
    Cosine similarity between two L2-normalised sentence-transformer vectors.

    Because both vectors are unit-normalised, dot product == cosine similarity.
    Cosine range [-1, +1] is mapped to [0, 100].

    Returns 50.0 (neutral) if either vector is absent.
    """
    if not user_vec or not motiv_vec:
        return 50.0

    dot = sum(u * m for u, m in zip(user_vec, motiv_vec))
    # Map [-1, 1] → [0, 100]
    return _clamp100((dot + 1.0) / 2.0 * 100.0)


# ── Interest tag / keyword overlap ────────────────────────────────────────────

def compute_interest_score(
    user_tags: list[str],
    user_keyword_freq: dict[str, int],
    motiv_tags: list[str],
    motiv_keywords: list[str],
) -> float:
    """
    Overlap score between user interest signals and motivation tags/keywords.

    Components:
      60% — Jaccard similarity on Empath interest tags
      40% — Fraction of motivation search keywords present in user keyword vocabulary

    Returns 0–100.
    """
    user_tag_set = {t.lower() for t in user_tags}
    motiv_tag_set = {t.lower() for t in motiv_tags}

    if user_tag_set and motiv_tag_set:
        intersection = len(user_tag_set & motiv_tag_set)
        union = len(user_tag_set | motiv_tag_set)
        tag_jaccard = intersection / union * 100.0
    else:
        tag_jaccard = 0.0

    motiv_kw_set = {k.lower() for k in motiv_keywords}
    user_kw_set = {k.lower() for k in user_keyword_freq.keys()}
    if motiv_kw_set:
        kw_overlap = len(user_kw_set & motiv_kw_set) / len(motiv_kw_set) * 100.0
    else:
        kw_overlap = 0.0

    return _clamp100(0.6 * tag_jaccard + 0.4 * kw_overlap)


# ── Composite score ───────────────────────────────────────────────────────────

def compute_composite_score(
    ocean_score: float,
    embedding_score: float,
    interest_score: float,
) -> float:
    """
    Weighted composite of the three component scores.
    Weights: OCEAN 50%, embedding 25%, interest 25%.
    Returns 0–100.
    """
    raw = (
        OCEAN_WEIGHT * ocean_score
        + EMBEDDING_WEIGHT * embedding_score
        + INTEREST_WEIGHT * interest_score
    )
    return _clamp100(raw)


# ── Confidence ────────────────────────────────────────────────────────────────

def compute_match_confidence(
    user_ocean_confidence: float,
    has_embedding: bool,
    interest_tag_count: int,
) -> float:
    """
    Confidence in the match result (0–100).

    Components:
      50% — OCEAN scoring confidence (quality of the personality signal)
      30% — Whether a user embedding is available (vs fallback 40%)
      20% — Number of interest tags (richness of topic signal)
    """
    ocean_component = _clamp100(user_ocean_confidence) * 0.50
    embedding_component = (100.0 if has_embedding else 40.0) * 0.30
    tag_component = min(interest_tag_count, 10) / 10.0 * 100.0 * 0.20
    return _clamp100(ocean_component + embedding_component + tag_component)


# ── Human-readable reasoning ──────────────────────────────────────────────────

def build_reasoning(
    ocean_score: float,
    embedding_score: float,
    interest_score: float,
    user_tags: list[str],
    motiv_tags: list[str],
    motiv_name: str,
) -> list[str]:
    """
    Generate up to 3 concise explanation strings for a match score.
    """
    reasons: list[str] = []

    if ocean_score >= 75:
        reasons.append(
            f"Strong personality alignment with the '{motiv_name}' archetype "
            f"(OCEAN score: {ocean_score:.0f}/100)."
        )
    elif ocean_score >= 55:
        reasons.append(
            f"Moderate personality alignment with '{motiv_name}' "
            f"(OCEAN score: {ocean_score:.0f}/100)."
        )
    else:
        reasons.append(
            f"Weak personality alignment with '{motiv_name}' "
            f"(OCEAN score: {ocean_score:.0f}/100)."
        )

    if embedding_score >= 65:
        reasons.append(
            f"High semantic similarity between user content and motivation description "
            f"({embedding_score:.0f}/100)."
        )

    shared = [t for t in user_tags if t.lower() in {m.lower() for m in motiv_tags}]
    if shared:
        reasons.append(f"Shared interest signals: {', '.join(shared[:4])}.")
    elif interest_score >= 20:
        reasons.append(f"Keyword vocabulary overlaps with motivation topics ({interest_score:.0f}/100).")

    return reasons


# ── Helpers ───────────────────────────────────────────────────────────────────

def _clamp100(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 2)


def _clamp10(value: float) -> float:
    return max(0.0, min(10.0, float(value)))
