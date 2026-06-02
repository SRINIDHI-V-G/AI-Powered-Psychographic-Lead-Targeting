"""
Keyword/category → subreddit mapping.

Maps product interest tags and category names to relevant subreddits.
This is a lookup table, not ML. It encodes curator knowledge about
which Reddit communities have high concentrations of people interested
in specific product categories.

Usage:
    subreddits = get_subreddits_for_keywords(["interior design", "home decor"])
    india_subs = get_india_subreddits(target_city="Chennai")
"""
from __future__ import annotations

# ── Primary interest-tag → subreddit mapping ─────────────────────────────────
# Key: lowercase interest tag or category keyword
# Value: list of subreddit names (without r/ prefix)

INTEREST_TO_SUBREDDITS: dict[str, list[str]] = {
    # ── Home & Interior ───────────────────────────────────────────────────────
    "interior design":    ["interiordesign", "HomeDecorating", "malelivingspace",
                           "femalelivingspace", "DesignMyRoom"],
    "home decor":         ["HomeDecorating", "interiordesign", "homedecor",
                           "DIY", "Renovations"],
    "furniture":          ["furniture", "interiordesign", "HomeImprovement",
                           "HomeDecorating", "buyitforlife"],
    "aesthetics":         ["malelivingspace", "femalelivingspace", "weddingplanning",
                           "minimalist", "Scandinavian"],
    "living room":        ["malelivingspace", "femalelivingspace", "interiordesign"],
    "luxury living":      ["luxuryhomes", "lifestyleadvice", "fatFIRE", "mildlyhigh"],
    "minimalism":         ["minimalism", "minimalist", "ZeroWaste"],
    "modern design":      ["interiordesign", "ModernHomeDesign", "DesignPorn",
                           "architecture"],
    "architecture":       ["architecture", "DesignPorn", "interiordesign",
                           "urbanplanning"],
    "lifestyle":          ["lifestyleadvice", "malefashionadvice", "femalefashionadvice",
                           "simpleliving"],

    # ── Health & Fitness ──────────────────────────────────────────────────────
    "yoga":               ["yoga", "flexibility", "meditation", "mindfulness"],
    "fitness":            ["fitness", "xxfitness", "bodyweightfitness", "running"],
    "wellness":           ["wellness", "HealthyFood", "meditation", "sleep"],
    "meditation":         ["meditation", "mindfulness", "Buddhism", "Stoicism"],
    "nutrition":          ["nutrition", "EatCheapAndHealthy", "veganfitness"],
    "running":            ["running", "trailrunning", "ultrarunning"],

    # ── Technology ────────────────────────────────────────────────────────────
    "electronics":        ["gadgets", "hardware", "tech", "technology"],
    "keyboards":          ["MechanicalKeyboards", "typing", "pcmasterrace"],
    "gaming":             ["gaming", "pcgaming", "buildapc", "pcmasterrace"],
    "programming":        ["programming", "learnprogramming", "cscareerquestions"],
    "software":           ["software", "webdev", "programming"],
    "smartphones":        ["android", "iphone", "gadgets", "technology"],
    "audio":              ["audiophile", "headphones", "vinyl", "hifi"],
    "photography":        ["photography", "photojournalism", "analog"],
    "smart home":         ["smarthome", "homeautomation", "amazonecho"],

    # ── Fashion & Personal Care ───────────────────────────────────────────────
    "fashion":            ["malefashionadvice", "femalefashionadvice", "streetwear",
                           "frugalmalefashion"],
    "beauty":             ["MakeupAddiction", "SkincareAddiction", "AsianBeauty",
                           "HaircareScience"],
    "skincare":           ["SkincareAddiction", "AsianBeauty", "tretinoin"],
    "luxury":             ["luxurygoods", "highstreetwear", "luxuryfashion"],

    # ── Food & Beverage ───────────────────────────────────────────────────────
    "food":               ["food", "cooking", "recipes", "IndianFood", "EatCheapAndHealthy"],
    "coffee":             ["Coffee", "espresso", "tea"],
    "cooking":            ["cooking", "Cooking", "AskCulinary", "recipes"],

    # ── Finance & Investment ──────────────────────────────────────────────────
    "personal finance":   ["personalfinance", "financialindependence", "india_finance",
                           "IndiaInvestments"],
    "investment":         ["investing", "stocks", "IndiaInvestments", "mutualfunds"],
    "frugal":             ["Frugal", "frugalmalefashion", "beermoney"],

    # ── Parenting & Family ────────────────────────────────────────────────────
    "parenting":          ["Parenting", "NewParents", "daddit", "Mommit"],
    "family":             ["Parenting", "family", "NewParents"],

    # ── Travel ────────────────────────────────────────────────────────────────
    "travel":             ["travel", "solotravel", "backpacking", "IndiaTravel"],
    "backpacking":        ["backpacking", "solotravel", "travel"],

    # ── Environment & Sustainability ──────────────────────────────────────────
    "sustainability":     ["ZeroWaste", "Frugal", "zerowastefashion", "anticonsumption"],
    "eco-friendly":       ["ZeroWaste", "sustainability", "environment"],

    # ── Reviews & Quality ─────────────────────────────────────────────────────
    "reviews":            ["buyitforlife", "BuyItForLife", "slatestarcodex"],
    "quality":            ["buyitforlife", "BuyItForLife"],
    "craftsmanship":      ["woodworking", "leathercraft", "DIY", "buyitforlife"],
}

# ── India / regional subreddits ───────────────────────────────────────────────
# Used to find users in India, weighted by city when target_city is specified.

INDIA_SUBREDDITS: list[str] = ["india", "IndiaInvestments", "AskIndia",
                                "IndiaSpeaks", "indianews"]

CITY_SUBREDDITS: dict[str, list[str]] = {
    "chennai":   ["Chennai", "tamilnadu"],
    "bangalore": ["bangalore", "bengaluru", "india"],
    "mumbai":    ["mumbai", "Maharashtra", "india"],
    "delhi":     ["delhi", "DelhiNCR", "india"],
    "hyderabad": ["hyderabad", "telangana", "india"],
    "pune":      ["pune", "Maharashtra", "india"],
    "kolkata":   ["kolkata", "WestBengal", "india"],
    "ahmedabad": ["ahmedabad", "gujarat", "india"],
    "jaipur":    ["jaipur", "Rajasthan", "india"],
    "kochi":     ["Kerala", "india"],
    "default":   ["india"],
}


def get_subreddits_for_keywords(
    keywords: list[str],
    max_subreddits: int = 12,
) -> list[str]:
    """
    Map a list of interest keywords to relevant subreddits.
    Returns a deduplicated list, capped at max_subreddits.
    """
    seen: set[str] = set()
    result: list[str] = []
    for kw in keywords:
        kw_lower = kw.lower().strip()
        subs = INTEREST_TO_SUBREDDITS.get(kw_lower, [])
        # Partial match fallback: check if keyword is a substring of any key
        if not subs:
            for map_key, map_subs in INTEREST_TO_SUBREDDITS.items():
                if kw_lower in map_key or map_key in kw_lower:
                    subs = map_subs
                    break
        for sub in subs:
            if sub not in seen:
                seen.add(sub)
                result.append(sub)
            if len(result) >= max_subreddits:
                return result
    return result


def get_city_subreddits(target_city: str | None) -> list[str]:
    """
    Return subreddits appropriate for the product's target city.
    Always includes at least r/india for regional coverage.
    """
    if not target_city:
        return INDIA_SUBREDDITS[:3]
    city_key = target_city.lower().strip()
    for key, subs in CITY_SUBREDDITS.items():
        if key in city_key or city_key in key:
            return subs
    return CITY_SUBREDDITS["default"]
