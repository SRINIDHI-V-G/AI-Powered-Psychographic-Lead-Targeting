"""
Bio extractor — pull explicit handle signals from a user's public bio text
and profile URL.

Extraction targets:
  1. URLs containing recognisable platform paths (twitter.com/x, instagram.com,
     linkedin.com/in, tiktok.com/@, github.com, youtube.com/@, etc.)
  2. @mention tokens (bare @handle or @platform:handle patterns)
  3. Platform-prefixed text ("twitter: handle", "ig: handle", "linkedin: /in/handle")

All extracted handles are returned as tier="extracted" with confidence 70–90
depending on signal strength. Handles confirmed via a direct profile URL are
returned as tier="confirmed" with confidence 90.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import NamedTuple


# ── Platform URL patterns ─────────────────────────────────────────────────────

_PLATFORM_URL_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("twitter",   re.compile(r"(?:twitter\.com|x\.com)/([A-Za-z0-9_]{1,50})", re.I)),
    ("instagram", re.compile(r"instagram\.com/([A-Za-z0-9_.]{1,50})", re.I)),
    ("linkedin",  re.compile(r"linkedin\.com/in/([A-Za-z0-9_-]{1,100})", re.I)),
    ("tiktok",    re.compile(r"tiktok\.com/@?([A-Za-z0-9_.]{1,50})", re.I)),
    ("github",    re.compile(r"github\.com/([A-Za-z0-9_-]{1,100})", re.I)),
    ("youtube",   re.compile(r"youtube\.com/(?:@|user/|channel/)([A-Za-z0-9_.-]{1,100})", re.I)),
    ("reddit",    re.compile(r"reddit\.com/u(?:ser)?/([A-Za-z0-9_-]{3,50})", re.I)),
    ("twitch",    re.compile(r"twitch\.tv/([A-Za-z0-9_]{4,50})", re.I)),
    ("discord",   re.compile(r"discord(?:app)?\.(?:com|gg)/(?:invite/)?([A-Za-z0-9_-]{2,50})", re.I)),
    ("medium",    re.compile(r"medium\.com/@([A-Za-z0-9_.]{1,50})", re.I)),
]

# ── @mention patterns ────────────────────────────────────────────────────────

_AT_MENTION_RE = re.compile(r"@([A-Za-z0-9_]{1,50})")

# Explicit "platform: handle" prefix patterns
_PLATFORM_PREFIX_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("twitter",   re.compile(r"\b(?:twitter|tw|x)\s*[:=]\s*@?([A-Za-z0-9_]{1,50})", re.I)),
    ("instagram", re.compile(r"\b(?:instagram|ig|insta)\s*[:=]\s*@?([A-Za-z0-9_.]{1,50})", re.I)),
    ("linkedin",  re.compile(r"\b(?:linkedin|li|lnkd)\s*[:=]\s*@?([A-Za-z0-9_-]{1,100})", re.I)),
    ("tiktok",    re.compile(r"\b(?:tiktok|tt)\s*[:=]\s*@?([A-Za-z0-9_.]{1,50})", re.I)),
    ("github",    re.compile(r"\b(?:github|gh)\s*[:=]\s*@?([A-Za-z0-9_-]{1,100})", re.I)),
    ("youtube",   re.compile(r"\b(?:youtube|yt)\s*[:=]\s*@?([A-Za-z0-9_.-]{1,100})", re.I)),
    ("twitch",    re.compile(r"\b(?:twitch)\s*[:=]\s*@?([A-Za-z0-9_]{4,50})", re.I)),
]

# Tokens to skip — platform names, common English words that look like handles
_SKIP_TOKENS = frozenset({
    "twitter", "instagram", "linkedin", "tiktok", "github", "youtube",
    "reddit", "twitch", "discord", "medium", "snapchat", "facebook", "fb",
    "me", "my", "i", "is", "am", "at", "in", "on", "to", "the", "a",
})


@dataclass
class ExtractedHandle:
    handle: str
    platform: str
    confidence: float
    tier: str
    evidence: dict = field(default_factory=dict)


def _clean_handle(raw: str) -> str:
    return raw.strip("/@. ").lower()


def _is_valid_handle(handle: str) -> bool:
    if len(handle) < 2 or len(handle) > 100:
        return False
    if handle.lower() in _SKIP_TOKENS:
        return False
    # Must contain at least one alphanumeric character
    return bool(re.search(r"[a-z0-9]", handle, re.I))


def extract_from_bio(
    bio: str,
    profile_url: str | None = None,
    known_username: str | None = None,
) -> list[ExtractedHandle]:
    """
    Parse all handle signals from a user's bio text and optional profile URL.

    Returns a deduplicated list of ExtractedHandle instances ordered by
    descending confidence. Each handle is returned at most once per platform.
    """
    results: dict[tuple[str, str], ExtractedHandle] = {}

    def _add(handle: str, platform: str, confidence: float, tier: str, evidence: dict) -> None:
        handle = _clean_handle(handle)
        if not _is_valid_handle(handle):
            return
        key = (platform, handle)
        existing = results.get(key)
        if existing is None or confidence > existing.confidence:
            results[key] = ExtractedHandle(
                handle=handle,
                platform=platform,
                confidence=confidence,
                tier=tier,
                evidence=evidence,
            )

    combined_text = f"{bio or ''} {profile_url or ''}"

    # ── 1. Platform URL extraction (highest confidence) ────────────────────
    for platform, pattern in _PLATFORM_URL_PATTERNS:
        for match in pattern.finditer(combined_text):
            raw = match.group(1)
            # Distinguish confirmed (from profile_url) vs extracted (from bio)
            in_profile_url = profile_url and pattern.search(profile_url or "")
            tier = "confirmed" if in_profile_url else "extracted"
            conf = 90.0 if tier == "confirmed" else 80.0
            _add(raw, platform, conf, tier, {
                "source": "url_parse",
                "raw_text": match.group(0),
                "generator": "bio_extractor",
            })

    # ── 2. Platform-prefix patterns ────────────────────────────────────────
    for platform, pattern in _PLATFORM_PREFIX_PATTERNS:
        for match in pattern.finditer(bio or ""):
            raw = match.group(1)
            _add(raw, platform, 78.0, "extracted", {
                "source": "platform_prefix",
                "raw_text": match.group(0),
                "generator": "bio_extractor",
            })

    # ── 3. Bare @mention tokens ────────────────────────────────────────────
    for match in _AT_MENTION_RE.finditer(bio or ""):
        raw = match.group(1)
        # Skip if it matches the known username exactly (that's just self-reference)
        if known_username and raw.lower() == known_username.lower():
            continue
        # Bare mentions have no platform signal — tag as "unknown"
        _add(raw, "unknown", 65.0, "extracted", {
            "source": "at_mention",
            "raw_text": match.group(0),
            "generator": "bio_extractor",
        })

    return sorted(results.values(), key=lambda h: h.confidence, reverse=True)
