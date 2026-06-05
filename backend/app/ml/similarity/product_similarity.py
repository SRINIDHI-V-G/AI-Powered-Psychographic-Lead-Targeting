"""
Similar product discovery — prompt builder, response parser, and OCEAN similarity.

Three public components:

  SIMILAR_PRODUCTS_SYSTEM_PROMPT
      Constant passed as the LLM system role message.

  build_similar_products_prompt(product, product_ocean) -> str
      Builds the user-side LLM prompt. Returns a plain string ready for
      OllamaClient.generate(prompt=..., system=SIMILAR_PRODUCTS_SYSTEM_PROMPT).

  parse_similar_products_response(raw) -> list[dict]
      Defensive parser that handles clean JSON, wrapper objects, markdown
      fences, and partially truncated responses. Returns a validated list
      (possibly empty — never raises).

  cosine_ocean_similarity(vec_a, vec_b) -> float
      Cosine similarity in 5-D OCEAN space. Both vectors must be 0-100 scale
      dicts with keys: openness, conscientiousness, extraversion, agreeableness,
      neuroticism. Returns a float in [0.0, 1.0].

Scale note:
  All OCEAN values handled here are on the 0-100 scale used by
  ProductOceanProfile and UserOceanScore. The 0-10 scale used by
  MotivationOceanProfile is converted BEFORE anything is passed here.
"""
from __future__ import annotations

import json
import math
import re

# ── System prompt ─────────────────────────────────────────────────────────────

SIMILAR_PRODUCTS_SYSTEM_PROMPT = (
    "You are a product market analyst specialising in psychographic consumer research. "
    "Given a product and its buyer personality profile (Big Five OCEAN model), "
    "identify similar products whose buyers share the same personality traits. "
    "Focus on personality alignment, not just product category. "
    "Always respond with valid JSON only. No explanation text outside the JSON."
)

# ── OCEAN dimension order (shared by prompt and similarity functions) ─────────

_OCEAN_DIMS = (
    "openness",
    "conscientiousness",
    "extraversion",
    "agreeableness",
    "neuroticism",
)

# ── Prompt builder ────────────────────────────────────────────────────────────

def build_similar_products_prompt(product: dict, product_ocean: dict) -> str:
    """
    Build the user-side LLM prompt for similar product discovery.

    Parameters
    ----------
    product : dict
        Must contain: name, category, description.
        Optional: price_range, keywords (list[str]).
    product_ocean : dict
        OCEAN profile on 0-100 scale.
        Keys: openness, conscientiousness, extraversion, agreeableness, neuroticism.

    Returns
    -------
    str
        Formatted prompt string. No markdown. Starts with context, ends with
        the exact JSON format the parser expects.
    """
    name        = product.get("name", "Unknown Product")
    category    = product.get("category", "general")
    description = product.get("description", "")
    price_range = product.get("price_range", "")
    keywords    = product.get("keywords") or []

    o  = _fmt(product_ocean.get("openness",          50))
    c  = _fmt(product_ocean.get("conscientiousness",  50))
    e  = _fmt(product_ocean.get("extraversion",       50))
    a  = _fmt(product_ocean.get("agreeableness",      50))
    n  = _fmt(product_ocean.get("neuroticism",        50))

    kw_line = ""
    if keywords:
        kw_line = f"Keywords: {', '.join(str(k) for k in keywords[:10])}\n"

    price_line = ""
    if price_range:
        price_line = f"Price Range: {price_range}\n"

    return (
        "Find 8 products similar to the one described below based on OCEAN personality alignment.\n\n"
        f"Product Name: {name}\n"
        f"Category: {category}\n"
        f"Description: {description}\n"
        f"{price_line}"
        f"{kw_line}"
        "\n"
        "This product's buyer personality profile (OCEAN, 0-100 scale):\n"
        f"  Openness:          {o}\n"
        f"  Conscientiousness: {c}\n"
        f"  Extraversion:      {e}\n"
        f"  Agreeableness:     {a}\n"
        f"  Neuroticism:       {n}\n"
        "\n"
        "For each similar product provide:\n"
        "  - product_name      : short name\n"
        "  - category          : product category\n"
        "  - description       : one sentence explaining why buyers of this product "
        "share the same personality as buyers of the source product\n"
        "  - ocean             : OCEAN profile of this product's typical buyer "
        "(0-100 scale, keys: openness, conscientiousness, extraversion, "
        "agreeableness, neuroticism)\n"
        "  - discovery_keywords: list of 4-6 search terms to find discussions "
        "about this product on Reddit, YouTube, and Instagram\n"
        "\n"
        "Rules:\n"
        "- Output ONLY raw JSON. No markdown. No code blocks. No backticks. "
        "No explanation.\n"
        "- Start your response with { and end with }\n"
        "- All OCEAN scores must be floats between 0.0 and 100.0\n"
        "- discovery_keywords must be a JSON array of strings\n"
        "\n"
        "Required JSON format:\n"
        '{"similar_products": ['
        '{"product_name": "Laptop", '
        '"category": "electronics", '
        '"description": "Buyers share high openness and conscientiousness.", '
        '"ocean": {"openness": 82.0, "conscientiousness": 71.0, '
        '"extraversion": 55.0, "agreeableness": 58.0, "neuroticism": 28.0}, '
        '"discovery_keywords": ["best laptop 2024", "laptop review", '
        '"ultrabook comparison"]}'
        "]}"
    )


# ── Response parser ───────────────────────────────────────────────────────────

def parse_similar_products_response(raw: str) -> list[dict]:
    """
    Extract and validate a list of similar product dicts from raw LLM output.

    Parsing strategy (mirrors motivation_prompter.parse_motivation_response):
      1. Strip markdown fences.
      2. Try full JSON parse — look for "similar_products" array inside a
         wrapper object, or a bare array.
      3. Fall back to brace-matching to recover individual items from
         truncated responses.
      4. Validate and clamp each item before returning.

    Returns an empty list if nothing usable is found. Never raises.
    """
    candidates: list[dict] = []

    # ── Strategy 1: full JSON parse ───────────────────────────────────────────
    json_str = _extract_json_block(raw)
    if json_str:
        try:
            data = json.loads(json_str)
            if isinstance(data, dict):
                candidates = data.get("similar_products") or []
            elif isinstance(data, list):
                candidates = data
        except json.JSONDecodeError:
            pass

    # ── Strategy 2: brace-match fallback for truncated output ────────────────
    if not candidates:
        candidates = _recover_partial_items(raw)

    if not isinstance(candidates, list):
        return []

    # ── Validate and normalise each candidate ─────────────────────────────────
    validated: list[dict] = []
    for item in candidates:
        cleaned = _validate_item(item)
        if cleaned is not None:
            validated.append(cleaned)

    return validated


# ── OCEAN cosine similarity ───────────────────────────────────────────────────

def cosine_ocean_similarity(
    vec_a: dict[str, float],
    vec_b: dict[str, float],
) -> float:
    """
    Cosine similarity between two OCEAN personality vectors (0-100 scale).

    Parameters
    ----------
    vec_a, vec_b : dict
        Keys: openness, conscientiousness, extraversion, agreeableness, neuroticism.
        Values: floats on the 0-100 scale.

    Returns
    -------
    float
        Similarity score in [0.0, 1.0].
        Returns 0.0 if either vector is all-zero (undefined cosine).

    Implementation note:
        Pure Python — no numpy dependency. Matches the approach used in
        ml/matching/scorer.py (Euclidean distance) for consistency.
        All five dimensions are weighted equally.
    """
    a_vals = [float(vec_a.get(d, 50.0)) for d in _OCEAN_DIMS]
    b_vals = [float(vec_b.get(d, 50.0)) for d in _OCEAN_DIMS]

    dot    = sum(x * y for x, y in zip(a_vals, b_vals))
    mag_a  = math.sqrt(sum(x * x for x in a_vals))
    mag_b  = math.sqrt(sum(y * y for y in b_vals))

    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0

    raw = dot / (mag_a * mag_b)
    # Clamp to [0.0, 1.0]: cosine of two non-negative vectors (0-100) is always
    # non-negative, but floating-point arithmetic can produce tiny negative values.
    return max(0.0, min(1.0, raw))


# ── Private helpers ───────────────────────────────────────────────────────────

def _fmt(value: object) -> str:
    """Format an OCEAN value for display in the prompt."""
    try:
        return f"{float(value):.1f}"
    except (TypeError, ValueError):
        return "50.0"


def _clamp100(value: object) -> float:
    """Clamp a value to [0.0, 100.0]; return 50.0 on invalid input."""
    try:
        return max(0.0, min(100.0, float(value)))
    except (TypeError, ValueError):
        return 50.0


def _strip_markdown_fences(text: str) -> str:
    """Remove ```json ... ``` or ``` ... ``` wrappers that Llama sometimes adds."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _extract_json_block(text: str) -> str | None:
    """
    Pull the first complete JSON object or array out of raw LLM output.
    Returns the raw JSON string, or None if nothing is found.
    """
    cleaned = _strip_markdown_fences(text)

    # Clean output starting with { — use directly
    if cleaned.startswith("{"):
        return cleaned

    # Bare JSON array
    if cleaned.startswith("["):
        return cleaned

    # Embedded object somewhere in the response
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return match.group()

    return None


def _recover_partial_items(text: str) -> list[dict]:
    """
    Brace-match fallback for truncated LLM responses.
    Locates the 'similar_products' array, then extracts each complete
    item object using depth-counted brace matching.
    Mirrors _recover_partial_categories in motivation_prompter.py.
    """
    marker = '"similar_products"'
    marker_idx = text.find(marker)
    if marker_idx == -1:
        # Try to recover from a bare truncated array
        bracket_idx = text.find("[")
        if bracket_idx == -1:
            return []
        search_area = text[bracket_idx + 1:]
    else:
        bracket_idx = text.find("[", marker_idx + len(marker))
        if bracket_idx == -1:
            return []
        search_area = text[bracket_idx + 1:]

    recovered: list[dict] = []
    i = 0
    while i < len(search_area):
        if search_area[i] != "{":
            i += 1
            continue
        depth = 0
        j = i
        while j < len(search_area):
            ch = search_area[j]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = search_area[i: j + 1]
                    try:
                        obj = json.loads(candidate)
                        if isinstance(obj, dict) and "product_name" in obj:
                            recovered.append(obj)
                    except json.JSONDecodeError:
                        pass
                    i = j + 1
                    break
            j += 1
        else:
            break
    return recovered


def _validate_item(item: object) -> dict | None:
    """
    Validate and normalise one candidate similar product dict.

    Required fields: product_name, ocean (dict with all 5 dimensions).
    All other fields are optional — missing ones get safe defaults.
    Returns None if the item is structurally invalid.
    """
    if not isinstance(item, dict):
        return None

    product_name = str(item.get("product_name") or "").strip()
    if not product_name:
        return None

    ocean_raw = item.get("ocean")
    if not isinstance(ocean_raw, dict):
        return None

    # Require at least 3 of the 5 OCEAN keys to be present and numeric
    numeric_dims = sum(
        1 for d in _OCEAN_DIMS
        if _is_numeric(ocean_raw.get(d))
    )
    if numeric_dims < 3:
        return None

    keywords_raw = item.get("discovery_keywords") or []
    if not isinstance(keywords_raw, list):
        keywords_raw = []

    return {
        "similar_product_name":        product_name[:255],
        "similar_product_category":    str(item.get("category") or "")[:100] or None,
        "similar_product_description": str(item.get("description") or "") or None,
        "openness":          _clamp100(ocean_raw.get("openness",          50)),
        "conscientiousness": _clamp100(ocean_raw.get("conscientiousness",  50)),
        "extraversion":      _clamp100(ocean_raw.get("extraversion",       50)),
        "agreeableness":     _clamp100(ocean_raw.get("agreeableness",      50)),
        "neuroticism":       _clamp100(ocean_raw.get("neuroticism",        50)),
        "discovery_keywords": [str(k) for k in keywords_raw if str(k).strip()][:10],
    }


def _is_numeric(value: object) -> bool:
    """Return True if value can be cast to float."""
    try:
        float(value)  # type: ignore[arg-type]
        return True
    except (TypeError, ValueError):
        return False
