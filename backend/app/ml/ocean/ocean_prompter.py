"""
OCEAN personality scoring prompt builder and response parser.

Design principles:
  1. Compact prompt — never exceeds ~600 input tokens.
     Sends NLP-derived summaries, NOT raw content dumps.
  2. Robust parser — handles truncated JSON, missing fields,
     out-of-range scores, and string/null values for numbers.
  3. All scores on 0-100 scale, 50 = average/neutral.

NOTE on neuroticism vs emotional_stability:
  MotivationOceanProfile stores `emotional_stability` (0-10 scale).
  User OCEAN scores store `neuroticism` (0-100 scale).
  Inversion for matching (Phase E): neuroticism = 100 - (emotional_stability * 10)
"""
from __future__ import annotations

import json
import re

OCEAN_SYSTEM_PROMPT = (
    "You are an expert psychologist trained in the Big Five personality model (OCEAN). "
    "Analyze the provided digital behavioral signals and infer personality traits. "
    "Be objective, evidence-based, and concise. "
    "Scale: 0 = extremely low, 50 = average, 100 = extremely high. "
    "Always respond with valid JSON only. No explanation outside the JSON."
)

# Minimum token threshold below which we skip LLM and use heuristic scoring.
MIN_TOKENS_FOR_LLM = 30

# Maximum content samples to include in the prompt.
MAX_CONTENT_SAMPLES = 5
MAX_SAMPLE_CHARS = 130


def build_ocean_prompt(
    interest_tags: list[str],
    empath_scores: dict[str, float],
    keyword_frequency: dict[str, int],
    vocabulary_richness: float,
    avg_sentence_length: float,
    total_tokens: int,
    content_samples: list[str] | None = None,
) -> str:
    """
    Build a compact OCEAN scoring prompt from pre-computed NLP features.
    Input is always < 650 tokens; output JSON is ~300-400 tokens.
    """
    # Interest areas (top 8)
    tags_str = ", ".join(interest_tags[:8]) if interest_tags else "none detected"

    # Top empath scores (top 8, formatted as "category(score)")
    top_empath = sorted(empath_scores.items(), key=lambda x: x[1], reverse=True)[:8]
    empath_str = (
        ", ".join(f"{k}({v:.2f})" for k, v in top_empath)
        if top_empath else "none detected"
    )

    # Top keywords (top 8)
    top_kw = sorted(keyword_frequency.items(), key=lambda x: x[1], reverse=True)[:8]
    kw_str = (
        ", ".join(k for k, _ in top_kw)
        if top_kw else "none detected"
    )

    # Content samples (truncated)
    samples_section = ""
    if content_samples:
        trimmed = [s[:MAX_SAMPLE_CHARS].replace("\n", " ") for s in content_samples[:MAX_CONTENT_SAMPLES]]
        numbered = "\n".join(f"{i+1}. {s}" for i, s in enumerate(trimmed))
        samples_section = f"\nContent samples:\n{numbered}\n"

    return (
        "Score this social media user's Big Five personality based on their digital footprint.\n\n"
        f"Interest areas: {tags_str}\n"
        f"Dominant emotional themes: {empath_str}\n"
        f"Frequent content words: {kw_str}\n"
        f"Writing metrics: vocabulary_richness={vocabulary_richness:.2f}, "
        f"avg_sentence_length={avg_sentence_length:.1f} words, total_tokens={total_tokens}"
        f"{samples_section}\n"
        "Scoring guide:\n"
        "- Openness (0-100): creativity, curiosity, openness to new experiences\n"
        "- Conscientiousness (0-100): organization, goal-directedness, reliability\n"
        "- Extraversion (0-100): sociability, assertiveness, positive energy\n"
        "- Agreeableness (0-100): cooperativeness, trust, empathy\n"
        "- Neuroticism (0-100): emotional instability, anxiety, negative affect\n\n"
        "Return ONLY a single compact JSON object. Keep each reasoning value to 3-5 words max:\n"
        '{"openness":75,"conscientiousness":60,"extraversion":45,"agreeableness":70,'
        '"neuroticism":30,"confidence":68,"reasoning":{"openness":"curious, varied interests",'
        '"conscientiousness":"organised, goal-driven","extraversion":"reserved, low energy",'
        '"agreeableness":"empathetic, cooperative","neuroticism":"calm, stable"}}'
    )


# ── Response parsing ──────────────────────────────────────────────────────────

_DIMENSIONS = ("openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism")


def _clamp(value: object, lo: float = 0.0, hi: float = 100.0) -> float:
    try:
        return max(lo, min(hi, float(value)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 50.0


def _strip_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _extract_json_str(text: str) -> str | None:
    cleaned = _strip_fences(text)
    if cleaned.startswith("{"):
        return cleaned
    match = re.search(r"\{.*\}", text, re.DOTALL)
    return match.group() if match else None


def parse_ocean_response(text: str) -> dict | None:
    """
    Parse raw LLM output into an OCEAN score dict.
    Returns None on total failure. Never raises.

    Returned dict shape:
      {
        "openness": float,       # 0-100
        "conscientiousness": float,
        "extraversion": float,
        "agreeableness": float,
        "neuroticism": float,
        "confidence": float,
        "reasoning": {dim: str, ...},
        "scoring_method": "llm",
      }
    """
    if not text or not text.strip():
        return None

    json_str = _extract_json_str(text)
    if not json_str:
        return None

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        # Try to recover a partial object (truncated output)
        data = _recover_partial(json_str)
        if data is None:
            return None

    if not isinstance(data, dict):
        return None

    # Extract and clamp OCEAN dimensions
    result: dict = {}
    for dim in _DIMENSIONS:
        result[dim] = _clamp(data.get(dim, 50.0))

    result["confidence"] = _clamp(data.get("confidence", 50.0))

    # Extract reasoning (per-dimension string explanations)
    raw_reasoning = data.get("reasoning") or {}
    reasoning: dict[str, str] = {}
    if isinstance(raw_reasoning, dict):
        for dim in _DIMENSIONS:
            val = raw_reasoning.get(dim, "")
            reasoning[dim] = str(val)[:500] if val else ""
    result["reasoning"] = reasoning

    result["scoring_method"] = "llm"
    return result


def _recover_partial(text: str) -> dict | None:
    """
    Attempt to recover a truncated JSON object by extracting numeric fields
    using regex. Used when json.loads() fails.
    """
    result: dict = {}
    for dim in list(_DIMENSIONS) + ["confidence"]:
        match = re.search(rf'"{dim}"\s*:\s*([0-9]+(?:\.[0-9]+)?)', text)
        if match:
            result[dim] = _clamp(match.group(1))

    # Need at least one OCEAN dimension to be useful
    if not any(dim in result for dim in _DIMENSIONS):
        return None

    # Fill missing dimensions with neutral 50
    for dim in _DIMENSIONS:
        result.setdefault(dim, 50.0)
    result.setdefault("confidence", 40.0)

    # Try to extract reasoning strings
    reasoning: dict[str, str] = {}
    for dim in _DIMENSIONS:
        match = re.search(rf'"{dim}"\s*:\s*"([^"]*)"', text)
        if match:
            reasoning[dim] = match.group(1)[:500]
    result["reasoning"] = reasoning
    return result
