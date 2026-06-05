"""
Confidence engine — converts handle_score + signal context into a
calibrated confidence value and a tier classification.

Tier logic
----------
confirmed   score >= 88 AND extracted directly from profile URL
extracted   score >= 68 AND found explicitly in bio text
inferred    score >= 48 AND derived from username transformation patterns
predicted   score <  48 OR purely generative (Ollama / pattern library)

Anti-overconfidence ceilings
-----------------------------
confirmed   95  (never claim 100% — handle could belong to a different person)
extracted   88
inferred    72
predicted   58

Signal conflict penalties
--------------------------
If a candidate handle contradicts signals from confirmed handles (very low
fingerprint consistency despite high username similarity), apply a -10 penalty.
If the generator source is Ollama (hallucination-prone), apply a -5 penalty.
"""
from __future__ import annotations


# ── Tier thresholds (handle_score, 0-100) ────────────────────────────────────

_TIER_THRESHOLDS = {
    "confirmed":  88.0,
    "extracted":  68.0,
    "inferred":   48.0,
    "predicted":   0.0,
}

# Anti-overconfidence ceilings per tier
_CONFIDENCE_CEILINGS = {
    "confirmed":  95.0,
    "extracted":  88.0,
    "inferred":   72.0,
    "predicted":  58.0,
}

# Generator-level trust priors (added to base confidence before ceiling)
_SOURCE_TRUST = {
    "bio_extractor":      20.0,
    "username_variants":  10.0,
    "name_expansion":      8.0,
    "pattern_library":     5.0,
    "interest_injection":  3.0,
    "ollama":              2.0,
}


def classify_tier(
    handle_score: float,
    source: str,
    bio_extracted: bool = False,
) -> str:
    """
    Assign a tier based on handle_score and extraction context.

    bio_extracted=True forces the tier to be at least "extracted" regardless
    of score (bio-sourced handles are always explicit signals).
    """
    if bio_extracted:
        return "confirmed" if handle_score >= _TIER_THRESHOLDS["confirmed"] else "extracted"

    if handle_score >= _TIER_THRESHOLDS["confirmed"]:
        return "confirmed"
    if handle_score >= _TIER_THRESHOLDS["extracted"]:
        return "extracted"
    if handle_score >= _TIER_THRESHOLDS["inferred"]:
        return "inferred"
    return "predicted"


def compute_confidence(
    handle_score: float,
    tier: str,
    source: str,
    fingerprint_consistency: float,
    username_similarity: float,
    ocean_plausibility: float,
) -> float:
    """
    Compute calibrated confidence for a handle candidate.

    Algorithm
    ---------
    1. Start from handle_score as base.
    2. Add source trust prior.
    3. Apply signal conflict penalty when fingerprint and similarity diverge.
    4. Apply Ollama hallucination penalty.
    5. Apply anti-overconfidence ceiling for the tier.
    6. Clamp to [0, 100].

    Returns
    -------
    float: confidence value in [0, 100]
    """
    base = handle_score

    # Source trust boost
    trust_boost = _SOURCE_TRUST.get(source, 0.0)
    confidence = base + trust_boost

    # Signal conflict penalty: high similarity but low fingerprint consistency
    # means the pattern matches the username but doesn't match the confirmed
    # handle fingerprint — contradictory signals.
    if username_similarity > 70.0 and fingerprint_consistency < 35.0:
        confidence -= 10.0

    # Ollama penalty: LLMs hallucinate handles
    if source == "ollama":
        confidence -= 5.0

    # OCEAN plausibility below neutral is a weak negative signal
    if ocean_plausibility < 40.0:
        confidence -= 3.0

    # Anti-overconfidence ceiling
    ceiling = _CONFIDENCE_CEILINGS.get(tier, 58.0)
    confidence = min(confidence, ceiling)

    return max(0.0, min(100.0, round(confidence, 2)))
