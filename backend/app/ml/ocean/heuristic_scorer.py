"""
Heuristic OCEAN scorer using Empath lexicon signals.

Used when:
  - USE_MOCK_LLM = True
  - Ollama is unreachable / returns unparseable output
  - User has fewer than MIN_TOKENS_FOR_LLM tokens

Algorithm:
  1. Each OCEAN dimension has a set of associated Empath categories.
  2. For each dimension, compute the sum of Empath scores across its categories.
  3. Normalize the sum and shift it around a neutral baseline (50).
  4. Confidence scales with total_tokens, empath coverage, and vocabulary richness.

The result is unbiased — it reflects WHAT the user talks about, not what the
product needs. This mirrors the LLM path's independence from product context.

Literature basis:
  - Pennebaker & King (1999): LIWC → Big Five mappings
  - Fast & Funder (2008): word use and personality
  - Empath extends LIWC with neural lexicon expansion (Fast et al., 2016)
"""
from __future__ import annotations

# ── Empath → OCEAN mappings ───────────────────────────────────────────────────
# Each OCEAN dimension is associated with Empath categories that positively
# predict high scores on that dimension.

_OPENNESS_CATS: tuple[str, ...] = (
    "art", "music", "beauty", "imagination", "reading", "intellectual",
    "science", "education", "writing", "creativity", "curiosity",
    "travel", "nature", "philosophy", "poetry", "learning",
)

_CONSCIENTIOUSNESS_CATS: tuple[str, ...] = (
    "work", "achievement", "order", "discipline", "business", "money",
    "health", "exercise", "planning", "quality", "cleaning", "hygiene",
    "home", "leadership", "diligence",
)

_EXTRAVERSION_CATS: tuple[str, ...] = (
    "social", "party", "fun", "sports", "communication", "positive_emotion",
    "joy", "energy", "excitement", "humor", "friendship", "celebration",
    "entertainment", "optimism",
)

_AGREEABLENESS_CATS: tuple[str, ...] = (
    "affection", "helping", "family", "love", "trust", "care", "warmth",
    "sympathy", "cooperation", "kindness", "generosity", "forgiveness",
    "support", "sharing",
)

_NEUROTICISM_CATS: tuple[str, ...] = (
    "negative_emotion", "anxiety", "anger", "sadness", "fear", "stress",
    "shame", "disgust", "disappointment", "pain", "suffering", "confusion",
    "nervousness", "irritability",
)

_EMPATH_MAP: dict[str, tuple[str, ...]] = {
    "openness":          _OPENNESS_CATS,
    "conscientiousness": _CONSCIENTIOUSNESS_CATS,
    "extraversion":      _EXTRAVERSION_CATS,
    "agreeableness":     _AGREEABLENESS_CATS,
    "neuroticism":       _NEUROTICISM_CATS,
}

# Typical high Empath score for a dominant category in real content (~0.15).
# Scores above this are treated as full signal strength.
_HIGH_SIGNAL_THRESHOLD = 0.12

# Maximum points lifted above/below the neutral 50 baseline.
_MAX_LIFT = 40.0

_NEUTRAL = 50.0


def _dimension_score(dimension: str, empath_scores: dict[str, float]) -> float:
    """
    Compute a single OCEAN dimension score in 0-100 from Empath signals.
    """
    categories = _EMPATH_MAP[dimension]
    relevant = [empath_scores.get(cat, 0.0) for cat in categories]
    present = [s for s in relevant if s > 0]

    if not present:
        return _NEUTRAL

    # Average of present-category scores (absent = 0)
    avg_present = sum(present) / len(present)

    # Normalize: _HIGH_SIGNAL_THRESHOLD maps to full lift
    normalized = min(avg_present / _HIGH_SIGNAL_THRESHOLD, 1.0)

    return round(min(100.0, max(0.0, _NEUTRAL + normalized * _MAX_LIFT)), 1)


def compute_confidence(
    total_tokens: int,
    empath_scores: dict[str, float],
    vocabulary_richness: float | None,
) -> float:
    """
    Compute a confidence score (0-100) based on available evidence quality.

    Components:
      - Token count (0-50 pts): more content = more reliable signal
      - Empath coverage (0-30 pts): more non-zero categories = richer signal
      - Vocabulary richness (0-20 pts): richer writing = more interpretable
    """
    token_component = min(total_tokens, 500) / 500 * 50
    empath_component = min(len(empath_scores), 30) / 30 * 30
    vocab_component = (vocabulary_richness or 0.0) * 20
    return round(min(100.0, token_component + empath_component + vocab_component), 1)


def compute_heuristic_scores(
    empath_scores: dict[str, float],
    total_tokens: int = 0,
    vocabulary_richness: float | None = None,
    avg_sentence_length: float | None = None,
) -> dict:
    """
    Compute OCEAN personality scores from Empath signals without LLM.

    Returns a dict matching the shape of parse_ocean_response():
      {
        "openness":          float,  # 0-100
        "conscientiousness": float,
        "extraversion":      float,
        "agreeableness":     float,
        "neuroticism":       float,
        "confidence":        float,
        "reasoning":         {dim: str},
        "scoring_method":    "heuristic",
      }
    """
    scores = {
        dim: _dimension_score(dim, empath_scores)
        for dim in _EMPATH_MAP
    }
    confidence = compute_confidence(total_tokens, empath_scores, vocabulary_richness)

    # Brief reasoning note per dimension
    reasoning: dict[str, str] = {}
    for dim, cats in _EMPATH_MAP.items():
        matched = [c for c in cats if empath_scores.get(c, 0.0) > 0]
        if matched:
            reasoning[dim] = (
                f"Heuristic estimate. Empath signals: {', '.join(matched[:4])}."
            )
        else:
            reasoning[dim] = "Heuristic estimate. No matching Empath signals — defaulting to neutral."

    return {
        "openness":          scores["openness"],
        "conscientiousness": scores["conscientiousness"],
        "extraversion":      scores["extraversion"],
        "agreeableness":     scores["agreeableness"],
        "neuroticism":       scores["neuroticism"],
        "confidence":        confidence,
        "reasoning":         reasoning,
        "scoring_method":    "heuristic",
    }


def compute_insufficient_content_scores() -> dict:
    """
    Return neutral OCEAN scores when a user has too little content to score.
    All dimensions default to 50 (average) with very low confidence.
    """
    reasoning = {
        dim: "Insufficient content for reliable scoring."
        for dim in _EMPATH_MAP
    }
    return {
        "openness":          50.0,
        "conscientiousness": 50.0,
        "extraversion":      50.0,
        "agreeableness":     50.0,
        "neuroticism":       50.0,
        "confidence":        10.0,
        "reasoning":         reasoning,
        "scoring_method":    "insufficient_content",
    }
