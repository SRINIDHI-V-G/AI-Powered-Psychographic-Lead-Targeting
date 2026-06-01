import json
import re

SYSTEM_PROMPT = (
    "You are an expert psychographic marketing strategist. "
    "Your job is to identify the distinct psychological motivations behind product purchases. "
    "Always respond with valid JSON only. No explanation text outside the JSON."
)


def build_motivation_prompt(product: dict) -> str:
    return f"""Analyze this product and generate exactly 5 distinct motivation categories.
Each category represents a different psychological reason WHY someone would buy this product.

Product Name: {product['name']}
Category: {product['category']}
Price Range: {product['price_range']}
Description: {product['description']}

For each motivation category provide:
- name: short category name (5-7 words max)
- description: 2-3 sentences explaining this buyer type and what drives them
- ocean: Big Five personality scores, each a float from 0.0 to 10.0
  - openness: curiosity, creativity, aesthetic appreciation
  - conscientiousness: organisation, discipline, planning
  - extraversion: sociability, assertiveness, enthusiasm
  - agreeableness: cooperation, trust, warmth
  - emotional_stability: calmness, resilience (high = stable, low = anxious)
- interest_tags: list of 5-8 interest areas this buyer likely follows
- search_keywords: list of 8-12 keywords they would use in posts or captions
- hashtags: list of 6-10 hashtags they would use

Return ONLY this exact JSON — no text before or after it:
{{
  "motivation_categories": [
    {{
      "name": "string",
      "description": "string",
      "ocean": {{
        "openness": 0.0,
        "conscientiousness": 0.0,
        "extraversion": 0.0,
        "agreeableness": 0.0,
        "emotional_stability": 0.0
      }},
      "interest_tags": [],
      "search_keywords": [],
      "hashtags": []
    }}
  ]
}}"""


def _clamp(value: object, lo: float = 0.0, hi: float = 10.0) -> float:
    try:
        return max(lo, min(hi, float(value)))
    except (TypeError, ValueError):
        return 5.0


def parse_motivation_response(text: str) -> list[dict] | None:
    """
    Extracts the first JSON object from the LLM response and returns
    a cleaned list of motivation category dicts. Returns None if parsing fails.
    """
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None

    try:
        data = json.loads(match.group())
    except json.JSONDecodeError:
        return None

    raw_categories = data.get("motivation_categories")
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
                    "openness": _clamp(ocean_raw.get("openness", 5.0)),
                    "conscientiousness": _clamp(ocean_raw.get("conscientiousness", 5.0)),
                    "extraversion": _clamp(ocean_raw.get("extraversion", 5.0)),
                    "agreeableness": _clamp(ocean_raw.get("agreeableness", 5.0)),
                    "emotional_stability": _clamp(ocean_raw.get("emotional_stability", 5.0)),
                },
                "interest_tags": [str(t) for t in cat.get("interest_tags") or []],
                "search_keywords": [str(k) for k in cat.get("search_keywords") or []],
                "hashtags": [str(h) for h in cat.get("hashtags") or []],
            }
        )

    return cleaned if cleaned else None
