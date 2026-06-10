"""
Rule-based + scoring account-type classifier.

Two-pass classification per user:
  Pass 1 — Hard rules: a single strong signal produces an immediate result
            at high confidence (0.87–0.93).
  Pass 2 — Competitor check: both product-category terms AND selling language
            required; overrides other classifications.
  Pass 3 — Signal scoring: weighted multi-signal accumulation. Business signals
            add positive score; consumer signals subtract.

Account type labels and pipeline behaviour:
  buyer      → passes through at full weight
  enthusiast → passes through at full weight
  community  → passes through at full weight
  creator    → passes through at full weight (individual content creators may
               be real buyers; they are not excluded)
  business   → EXCLUDED (pipeline_excluded=True)
  store      → EXCLUDED
  competitor → EXCLUDED
  unknown    → passes through NLP/OCEAN/matching, but final_score in matching
               is multiplied by UNKNOWN_SCORE_MULTIPLIER (25% reduction) and
               a warning is appended to the match reasoning for review.

No LLM fallback is used — this classifier is purely rule-based.
The LLM path can be added as a separate layer for UNKNOWN cases in a future
iteration without changing any of the interfaces here.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# ── Public constants ───────────────────────────────────────────────────────────

EXCLUDED_TYPES: frozenset[str] = frozenset({"business", "store", "competitor"})

# Applied to LeadMatch.final_score when account_type == "unknown".
# 25% reduction keeps unknowns in the output for manual review but
# ensures they rank below confirmed buyers.
UNKNOWN_SCORE_MULTIPLIER: float = 0.75

# ── Hard bio patterns (lower-cased) ───────────────────────────────────────────
# Any single match → immediate BUSINESS classification at 0.93 confidence.

_HARD_BIO: list[str] = [
    "dm for collab",
    "dm for collaboration",
    "dm for booking",
    "dm for inquiries",
    "dm for orders",
    "available for hire",
    "available for bookings",
    "for business inquiries",
    "for collaborations",
    "book a session",
    "book now",
    "order now",
    "shop now",
    "buy now",
    "production house",
    "creative agency",
    "marketing agency",
    "advertising agency",
    "pvt ltd",
    "private limited",
    " llp",
    " inc.",
    " ltd.",
    "elevating brands",
    "we help businesses",
    "your go-to",
    "one-stop",
    "transforming businesses",
    "we replace",       # "We replace messy tools with one smart workspace"
]

# Hard username suffix tokens.
# Match only when the suffix is preceded by at least 3 other chars,
# so "studio" alone would not match (needs e.g. "teknostudio").

_HARD_USERNAME_SUFFIXES: list[str] = [
    "official",
    "hq",
    "pvtltd",
    "solutions",
    "technologies",
    "agency",
    "studio",
    "studios",
    "productions",
    "academy",
    "services",
    "media",
    "entertainment",
    "records",
    "creation",
    "creations",
]

# Display-name brand separators: "Brand | tagline" or "Brand - City Descriptor"
_BRAND_SEPARATORS: list[str] = [" | ", " — "]

# Words that confirm a display separator indicates a business tagline.
_TAGLINE_WORDS: frozenset[str] = frozenset({
    "production", "studio", "agency", "tool", "ai", "marketing",
    "creative", "music", "tech", "technology", "solutions", "services",
    "workflow", "platform", "software",
})

# ── Scored bio business terms (phrase, weight, signal_tag) ────────────────────

_BIO_BUSINESS_SCORED: list[tuple[str, float, str]] = [
    ("workflow",        2.0, "bio_workflow"),
    ("workspace",       2.0, "bio_workspace"),
    ("platform",        1.5, "bio_platform"),
    (" tool",           1.5, "bio_tool"),
    ("software",        2.0, "bio_software"),
    ("saas",            2.5, "bio_saas"),
    ("solutions",       1.5, "bio_solutions"),
    ("services",        1.5, "bio_services"),
    ("smart ",          1.0, "bio_smart"),
    ("empower",         1.5, "bio_empower"),
    ("elevating",       1.5, "bio_elevating"),
    ("transforming",    1.5, "bio_transforming"),
    ("helping ",        1.0, "bio_helping"),
    ("we help",         1.5, "bio_we_help"),
    ("our team",        1.5, "bio_our_team"),
    ("innovation",      1.0, "bio_innovation"),
    ("collaboration",   1.0, "bio_collaboration"),
    ("subscribe to our", 1.5, "bio_subscribe_cta"),
]

# Username tokens that raise score moderately when present.
_USERNAME_BUSINESS_TOKENS: list[str] = [
    "music",
    "audio",
    "tekno",
    "techno",
    "tech",
    "digital",
    "creative",
    "design",
    "hub",
    "store",
    "shop",
    "market",
    "brand",
    "channel",
    "labs",
    "media",
    "academy",
    "productions",
    "records",
]

# City-name username suffixes that indicate a "brand+city" pattern.
_CITY_SUFFIXES: list[str] = [
    "chennai", "mumbai", "delhi", "bangalore", "bengaluru",
    "hyderabad", "pune", "kolkata", "india",
]

# ── Consumer signals ───────────────────────────────────────────────────────────

_TAMIL_TOKENS: list[str] = [
    "akka", "anna", "romba", "irruku", "unga", "nalla",
    "podunga", "helpfull", "sslc", "ennoda", "semma", "dei",
]

_PERSONAL_PHRASES: list[str] = [
    "my mark",
    "it's 3 am",
    "its 3 am",
    "3 am",
    "i pray",
    "may everyone",
    "whoever is reading",
    "anyone reading",
    "anybody who",
    "please like",
    "plz like",
    "public exam",
    "i'm trying",
    "i am trying",
    "dear everyone",
]

# YouTube auto-generated ID suffix (e.g. -l9f, -s3k, 6440, -p8o9b).
_AUTO_ID_RE = re.compile(r"[-_][a-z0-9]{2,5}$|[0-9]{4,}$", re.IGNORECASE)

# YouTube channel-ID format: "uc" + 22 base64 chars (matched against lowercased username).
# These are machine-generated IDs for personal/anonymous users, not brand channels.
_YOUTUBE_CHANNEL_ID_RE = re.compile(r"^uc[a-z0-9_\-]{22}$")

# Audio product terms for competitor detection.
_AUDIO_PRODUCT_TERMS: list[str] = [
    "headphone", "earphone", "earbuds", "speaker",
    "noise cancelling", "noise-cancelling", "anc ",
    "wireless audio", "bluetooth audio",
]

_SELLING_TERMS: list[str] = [
    "sell", "shop", "store", "official", "brand", "buy",
    "amazon", "flipkart", "order", "distributor", "reseller",
    "wholesale", "dealer",
]


# ── Result dataclass ───────────────────────────────────────────────────────────

@dataclass
class ClassificationResult:
    label: str              # buyer | enthusiast | community | creator |
                            # business | store | competitor | unknown
    confidence: float       # 0.0 – 1.0
    signals: list[str] = field(default_factory=list)
    excluded: bool = False
    exclusion_reason: str | None = None


# ── Public entry point ─────────────────────────────────────────────────────────

def classify_user(
    username: str,
    display_name: str | None,
    bio: str | None,
    follower_count: int,
    content_texts: list[str],
    *,
    check_competitor: bool = True,
) -> ClassificationResult:
    """
    Classify one discovered user.

    Args:
        username:       Social platform handle (raw, any case).
        display_name:   Full display name or None.
        bio:            Profile bio text or None.
        follower_count: Follower count from the platform API.
        content_texts:  List of post/comment text strings for this user.
        check_competitor: Set False to skip competitor detection (e.g. when
                          the product has no specific category context).

    Returns:
        ClassificationResult with label, confidence (0–1), and a list of
        signal tags that fired during classification.
    """
    u = (username or "").lower().strip()
    d = (display_name or "").lower().strip()
    b = (bio or "").lower().strip()
    all_content = " ".join(content_texts).lower()[:3000]

    signals: list[str] = []
    score = 0.0

    # ── Pass 1: Hard rules ────────────────────────────────────────────────────

    for pat in _HARD_BIO:
        if pat in b:
            signals.append(f"hard_bio:{pat[:35]}")
            return _business(signals, 0.93)

    for suf in _HARD_USERNAME_SUFFIXES:
        if u.endswith(suf) and len(u) > len(suf) + 2:
            signals.append(f"hard_username_suffix:{suf}")
            return _business(signals, 0.88)

    for sep in _BRAND_SEPARATORS:
        if sep in d:
            after = d.split(sep, 1)[1]
            if any(w in after for w in _TAGLINE_WORDS):
                signals.append(f"hard_display_brand_sep:{sep.strip()}")
                return _business(signals, 0.87)

    # ── Pass 2: Competitor detection ──────────────────────────────────────────

    if check_competitor:
        combined = f"{u} {d} {b}"
        has_product = any(t in combined for t in _AUDIO_PRODUCT_TERMS)
        has_selling = any(t in combined for t in _SELLING_TERMS)
        if has_product and has_selling:
            signals.append("competitor_product_and_selling_terms")
            return ClassificationResult(
                label="competitor",
                confidence=0.90,
                signals=signals,
                excluded=True,
                exclusion_reason="COMPETITOR (audio product + selling language)",
            )

    # ── Pass 3: Signal scoring ────────────────────────────────────────────────

    # Bio business vocabulary
    for phrase, weight, tag in _BIO_BUSINESS_SCORED:
        if phrase in b:
            signals.append(tag)
            score += weight

    # Display name business vocabulary (same terms as bio but lower weight)
    _DISPLAY_BUSINESS_WORDS = [
        "production", "studio", "agency", "records", "entertainment",
        "marketing", "services", "solutions", "technologies", "academy",
    ]
    for word in _DISPLAY_BUSINESS_WORDS:
        if word in d:
            signals.append(f"display_business_word:{word}")
            score += 1.5
            break  # count once — display names are short

    # Bio has formatted service list (multiple newlines, substantial length)
    if bio and bio.count("\n") >= 2 and len(b) > 60:
        signals.append("bio_formatted_service_list")
        score += 1.5

    # Username has known business tokens (count up to 2 — multiple tokens
    # compounding means the username is likely a concatenated brand name).
    _matched_tokens = 0
    for tok in _USERNAME_BUSINESS_TOKENS:
        if tok in u:
            signals.append(f"username_token:{tok}")
            score += 1.5
            _matched_tokens += 1
            if _matched_tokens >= 2:
                break

    # Username has brand+city pattern (brand name followed immediately by city)
    for city in _CITY_SUFFIXES:
        if u.endswith(city) and len(u) > len(city) + 2:
            signals.append(f"username_city_suffix:{city}")
            score += 1.0
            break

    # All content is outward-facing — no first-person singular voice
    has_first_person = bool(
        re.search(r"\b(i |i'm|i've|i am|my |me |i,|i\.|i!)\b", all_content)
    )
    if all_content and not has_first_person:
        signals.append("content_no_first_person")
        score += 1.5

    # ── Consumer signal subtractors ───────────────────────────────────────────

    tamil_count = sum(1 for tok in _TAMIL_TOKENS if tok in all_content)
    if tamil_count >= 2:
        signals.append(f"consumer_tamil_tokens:{tamil_count}")
        score -= 3.0
    elif tamil_count == 1:
        signals.append("consumer_tamil_token:1")
        score -= 1.5

    for phrase in _PERSONAL_PHRASES:
        if phrase in all_content:
            signals.append(f"consumer_personal_phrase:{phrase[:25]}")
            score -= 2.0
            break

    if _AUTO_ID_RE.search(u):
        signals.append("consumer_auto_id_suffix")
        score -= 2.5

    # YouTube machine-generated channel ID ("UC" + 22 base64 chars) — very
    # strong indicator of a real individual user, not a brand channel.
    if _YOUTUBE_CHANNEL_ID_RE.match(u):
        signals.append("consumer_youtube_channel_id")
        score -= 3.0

    if not b:
        signals.append("consumer_no_bio")
        score -= 1.5

    # Short, emoji-containing reaction content
    for txt in content_texts:
        words = txt.strip().split()
        has_emoji = any(ord(c) > 127 for c in txt)
        if len(words) <= 15 and has_emoji:
            signals.append("consumer_reaction_content")
            score -= 1.5
            break

    # ── Threshold classification ──────────────────────────────────────────────

    if score >= 4.0:
        conf = min(0.60 + score * 0.04, 0.94)
        return _business(signals, conf)

    if score >= 2.5:
        # Likely a content channel rather than a company — not excluded
        return ClassificationResult(
            label="creator",
            confidence=0.70,
            signals=signals,
            excluded=False,
        )

    if score <= -2.5:
        conf = min(0.65 + abs(score) * 0.04, 0.92)
        return ClassificationResult(label="buyer", confidence=conf, signals=signals)

    if score <= -1.0:
        return ClassificationResult(label="enthusiast", confidence=0.70, signals=signals)

    # Insufficient signal in either direction
    return ClassificationResult(label="unknown", confidence=0.50, signals=signals)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _business(signals: list[str], confidence: float) -> ClassificationResult:
    return ClassificationResult(
        label="business",
        confidence=confidence,
        signals=signals,
        excluded=True,
        exclusion_reason=f"BUSINESS (confidence={confidence:.2f})",
    )
