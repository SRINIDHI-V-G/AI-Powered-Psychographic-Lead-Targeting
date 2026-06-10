import json
import re

SYSTEM_PROMPT = (
    "You are an expert psychographic marketing strategist. "
    "Your job is to identify the distinct psychological motivations behind product purchases. "
    "Always respond with valid JSON only. No explanation text outside the JSON."
)


def build_motivation_prompt(product: dict) -> str:
    name        = product["name"]
    category    = product["category"]
    price_range = product["price_range"]
    description = product["description"]

    return (
        "You are analyzing a product to identify 5 distinct psychographic BUYER types.\n\n"
        f"Product Name: {name}\n"
        f"Category: {category}\n"
        f"Price Range: {price_range}\n"
        f"Description: {description}\n\n"
        "Generate exactly 5 motivation categories. "
        "Each category is a different psychological reason WHY someone buys this product.\n\n"
        "CRITICAL RULE for search_keywords:\n"
        "These must be phrases that BUYERS use when talking about their LIFESTYLE, PROBLEMS, "
        "and INTERESTS — NOT phrases that describe the product itself.\n"
        "The goal is to find communities of potential customers online, not product sellers.\n"
        "NEVER include the product name, product category, or brand names in search_keywords.\n"
        "Instead, think: what does this buyer type talk about, search for, or post about "
        "on YouTube and Instagram BEFORE they decide to buy this product?\n\n"
        f"Example for '{name}':\n"
        "  BAD search_keywords (finds sellers): "
        f'["{name.lower()}", "{category} review", "best {category}"]\n'
        "  GOOD search_keywords (finds buyers): lifestyle topics, pain points, "
        "communities this buyer belongs to, hobbies and interests related to WHY they buy.\n\n"
        "Rules:\n"
        "- Output ONLY raw JSON. No markdown. No code blocks. No backticks. No explanation.\n"
        "- Start your response with { and end with }\n"
        "- All OCEAN scores must be floats between 0.0 and 10.0\n\n"
        'Required JSON format (replace example values with real content):\n'
        '{"motivation_categories": ['
        '{"name": "short buyer persona name", '
        '"description": "1-2 sentences about this buyer and their motivation", '
        '"ocean": {"openness": 7.5, "conscientiousness": 6.0, "extraversion": 5.5, '
        '"agreeableness": 6.5, "emotional_stability": 7.0}, '
        '"interest_tags": ["lifestyle tag1", "lifestyle tag2", "lifestyle tag3"], '
        '"search_keywords": ["buyer lifestyle query1", "buyer lifestyle query2", '
        '"buyer pain point query3", "buyer interest query4", "buyer community query5"], '
        '"hashtags": ["#lifestyle1", "#interest2", "#community3"]}'
        "]}"
    )


def _clamp(value: object, lo: float = 0.0, hi: float = 10.0) -> float:
    try:
        return max(lo, min(hi, float(value)))
    except (TypeError, ValueError):
        return 5.0


def _strip_markdown_fences(text: str) -> str:
    """Remove ```json ... ``` or ``` ... ``` wrappers that Llama sometimes adds."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _extract_json(text: str) -> str | None:
    """
    Try two strategies to pull a JSON object out of raw LLM output.
    Returns the raw JSON string, or None if nothing usable is found.
    """
    # Strategy 1: strip markdown fences — if what remains starts with { use it directly
    cleaned = _strip_markdown_fences(text)
    if cleaned.startswith("{"):
        return cleaned

    # Strategy 2: find the first { ... } block with greedy match
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return match.group()

    return None


def _recover_partial_categories(text: str) -> list[dict]:
    """
    Fallback for truncated JSON. The outer object may never close (truncated),
    so we locate the 'motivation_categories' array first, then brace-match
    each individual category object inside it.
    """
    # Step 1: find the start of the categories array
    marker = '"motivation_categories"'
    marker_idx = text.find(marker)
    if marker_idx == -1:
        return []

    bracket_idx = text.find("[", marker_idx + len(marker))
    if bracket_idx == -1:
        return []

    # Step 2: search inside the array for complete category objects
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
                    candidate = search_area[i : j + 1]
                    try:
                        obj = json.loads(candidate)
                        if isinstance(obj, dict) and "name" in obj and "ocean" in obj:
                            recovered.append(obj)
                    except json.JSONDecodeError:
                        pass
                    i = j + 1
                    break
            j += 1
        else:
            break  # reached end of text with no closing brace — stop
    return recovered


def parse_motivation_response(text: str) -> list[dict] | None:
    """
    Extracts a JSON object from raw LLM output and returns a cleaned list of
    motivation category dicts. Returns None if parsing fails at any step.

    Strategy:
      1. Try to parse the whole response as JSON (handles clean output).
      2. If that fails (e.g. truncated), recover individual category objects
         using brace-matching (handles cut-off responses).
    """
    raw_categories: list = []

    # Strategy 1 — full JSON parse
    json_str = _extract_json(text)
    if json_str:
        try:
            data = json.loads(json_str)
            raw_categories = data.get("motivation_categories") or []
        except json.JSONDecodeError:
            pass

    # Strategy 2 — brace-matching fallback for truncated responses
    if not raw_categories:
        raw_categories = _recover_partial_categories(text)

    if not isinstance(raw_categories, list) or not raw_categories:
        return None

    cleaned: list[dict] = []
    for cat in raw_categories:
        if not isinstance(cat, dict):
            continue
        ocean_raw = cat.get("ocean") or {}
        cleaned.append(
            {
                "name": str(cat.get("name", "Unnamed"))[:255],
                "description": str(cat.get("description", "")),
                "ocean": {
                    "openness":            _clamp(ocean_raw.get("openness", 5.0)),
                    "conscientiousness":   _clamp(ocean_raw.get("conscientiousness", 5.0)),
                    "extraversion":        _clamp(ocean_raw.get("extraversion", 5.0)),
                    "agreeableness":       _clamp(ocean_raw.get("agreeableness", 5.0)),
                    "emotional_stability": _clamp(ocean_raw.get("emotional_stability", 5.0)),
                },
                "interest_tags":   [str(t) for t in cat.get("interest_tags") or []],
                "search_keywords": [str(k) for k in cat.get("search_keywords") or []],
                "hashtags":        [str(h) for h in cat.get("hashtags") or []],
            }
        )

    return cleaned if cleaned else None
