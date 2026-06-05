"""
Handle generator — produces a ranked candidate pool from five generators.

Generator 1 — Username Variants
  Systematic character-level and structural transforms of the known username
  (e.g. append year, swap separators, trim suffixes, leetspeak initials).

Generator 2 — Name Expansion
  Derives handles from display_name: first.last, flast, f_last, firstlast, etc.
  Also handles single-name display names.

Generator 3 — Interest Injection
  Appends or prepends top interest tags to the username to produce
  interest-labelled handles (e.g. "alice_gaming", "tech_alice").

Generator 4 — Ollama Generation
  Asks the local LLM to suggest plausible social handles given the username,
  display name, bio snippet, and top interests. Falls back gracefully on
  connection/timeout errors.

Generator 5 — Pattern Library
  Applies a curated library of known username transformation patterns observed
  in real cross-platform handle reuse studies.

All generators return Candidate objects. The caller (handle_ranker) is
responsible for scoring and deduplication.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import unicodedata
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Maximum candidates to keep from the full merged pool before ranking
MAX_CANDIDATES = 60

# Confidence ceilings per generator (before ranker rescoring)
_GEN_CEILING = {
    "username_variants": 60.0,
    "name_expansion":    55.0,
    "interest_injection": 48.0,
    "ollama":            52.0,
    "pattern_library":   50.0,
}


@dataclass
class Candidate:
    handle: str
    platform: str
    base_score: float
    source: str
    evidence: dict = field(default_factory=dict)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _slugify(text: str) -> str:
    """Normalize text to a handle-safe ASCII slug."""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-z0-9._-]", "", text.lower())
    return text.strip("._-")


def _dedup(candidates: list[Candidate]) -> list[Candidate]:
    seen: set[tuple[str, str]] = set()
    out: list[Candidate] = []
    for c in candidates:
        key = (c.platform, c.handle.lower())
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


# ── Generator 1: Username Variants ────────────────────────────────────────────

_COMMON_SUFFIXES = ["_", ".", "x", "real", "official", "hq", "io"]
_COMMON_PREFIXES = ["real", "the", "its", "im", "hey"]
_CURRENT_YEAR = "26"

def generate_username_variants(
    username: str,
    platforms: list[str],
) -> list[Candidate]:
    base = _slugify(username)
    if not base:
        return []

    transforms: list[str] = [
        base,
        base + _CURRENT_YEAR,
        base + "0",
        base + "1",
        base + "_",
        base + ".",
        base.rstrip("0123456789"),
        re.sub(r"[._-]", "", base),
        re.sub(r"[._-]", "_", base),
        re.sub(r"[._-]", ".", base),
    ]
    for suf in _COMMON_SUFFIXES:
        transforms.append(base + suf)
    for pre in _COMMON_PREFIXES:
        transforms.append(pre + base)
        transforms.append(pre + "_" + base)

    candidates: list[Candidate] = []
    for h in set(transforms):
        h = h.strip("._-")
        if len(h) < 2:
            continue
        score = _clamp(
            _GEN_CEILING["username_variants"] - (0 if h == base else 10),
        )
        for platform in platforms:
            candidates.append(Candidate(
                handle=h,
                platform=platform,
                base_score=score,
                source="username_variants",
                evidence={"generator": "username_variants", "base": base},
            ))
    return candidates


# ── Generator 2: Name Expansion ────────────────────────────────────────────────

def generate_name_expansion(
    display_name: str | None,
    platforms: list[str],
) -> list[Candidate]:
    if not display_name:
        return []

    parts = [_slugify(p) for p in display_name.split() if p]
    parts = [p for p in parts if p]
    if not parts:
        return []

    if len(parts) == 1:
        expansions = [parts[0]]
    else:
        first, *rest = parts
        last = rest[-1]
        middle = "".join(rest[:-1])
        expansions = [
            first + last,
            first + "_" + last,
            first + "." + last,
            first[0] + last,
            first[0] + "_" + last,
            first[0] + "." + last,
            first + last[0],
            first + middle[:1] + last,
        ]

    candidates: list[Candidate] = []
    ceiling = _GEN_CEILING["name_expansion"]
    for h in set(expansions):
        h = h.strip("._-")
        if len(h) < 2:
            continue
        for platform in platforms:
            candidates.append(Candidate(
                handle=h,
                platform=platform,
                base_score=ceiling,
                source="name_expansion",
                evidence={"generator": "name_expansion", "display_name": display_name},
            ))
    return candidates


# ── Generator 3: Interest Injection ───────────────────────────────────────────

def generate_interest_injection(
    username: str,
    interest_tags: list[str],
    platforms: list[str],
    max_tags: int = 5,
) -> list[Candidate]:
    base = _slugify(username)
    if not base or not interest_tags:
        return []

    tags = [_slugify(t) for t in interest_tags[:max_tags] if _slugify(t)]
    candidates: list[Candidate] = []
    ceiling = _GEN_CEILING["interest_injection"]

    for tag in tags:
        combos = [
            base + "_" + tag,
            base + "." + tag,
            tag + "_" + base,
            tag + base,
            base + tag,
        ]
        for h in combos:
            h = h.strip("._-")
            if len(h) < 3:
                continue
            for platform in platforms:
                candidates.append(Candidate(
                    handle=h,
                    platform=platform,
                    base_score=ceiling,
                    source="interest_injection",
                    evidence={"generator": "interest_injection", "tag": tag, "base": base},
                ))
    return candidates


# ── Generator 4: Ollama Generation ────────────────────────────────────────────

_OLLAMA_SYSTEM = (
    "You are a social media handle analyst. "
    "Given a Reddit username, display name, bio excerpt, and interest tags, "
    "suggest 8 plausible handles this person might use on Instagram, Twitter, "
    "TikTok, LinkedIn, or GitHub. "
    "Output ONLY a JSON array of objects: "
    '[{"handle": "...", "platform": "..."}, ...]. '
    "No explanation. No markdown. Raw JSON only."
)


async def generate_ollama_handles(
    username: str,
    display_name: str | None,
    bio: str | None,
    interest_tags: list[str],
    platforms: list[str],
) -> list[Candidate]:
    try:
        from app.ml.llm_client import OllamaClient
        from app.config import settings

        bio_snippet = (bio or "")[:200]
        tags_str = ", ".join(interest_tags[:8])
        prompt = (
            f"Username: {username}\n"
            f"Display name: {display_name or 'unknown'}\n"
            f"Bio: {bio_snippet}\n"
            f"Interest tags: {tags_str}\n\n"
            "Suggest 8 likely social handles."
        )

        client = OllamaClient()
        raw = await client.generate(
            prompt=prompt,
            system=_OLLAMA_SYSTEM,
            temperature=0.5,
            num_predict=300,
        )

        # Parse JSON array from response
        json_match = re.search(r"\[.*\]", raw, re.S)
        if not json_match:
            return []

        items = json.loads(json_match.group(0))
        candidates: list[Candidate] = []
        ceiling = _GEN_CEILING["ollama"]

        for item in items:
            if not isinstance(item, dict):
                continue
            h = _slugify(str(item.get("handle", "")))
            p = str(item.get("platform", "unknown")).lower().strip()
            if not h or len(h) < 2:
                continue
            if p not in platforms:
                p = "unknown"
            candidates.append(Candidate(
                handle=h,
                platform=p,
                base_score=ceiling,
                source="ollama",
                evidence={"generator": "ollama", "raw": item},
            ))
        return candidates

    except Exception as exc:
        logger.debug("[HandleGen/Ollama] skipped: %s", exc)
        return []


# ── Generator 5: Pattern Library ──────────────────────────────────────────────

_PATTERN_TRANSFORMS: list[tuple[str, str]] = [
    # (description, python format string using {base})
    ("append_underscore",    "{base}_"),
    ("double_underscore",    "__{base}__"),
    ("prepend_x",            "x{base}"),
    ("append_x",             "{base}x"),
    ("leetspeak_a",          None),   # handled specially
    ("append_official",      "{base}official"),
    ("prepend_get",          "get{base}"),
    ("wrap_its",             "its{base}"),
    ("append_dev",           "{base}dev"),
    ("append_irl",           "{base}irl"),
]


def generate_pattern_library(
    username: str,
    platforms: list[str],
) -> list[Candidate]:
    base = _slugify(username)
    if not base:
        return []

    leet = base.replace("a", "4").replace("e", "3").replace("o", "0").replace("i", "1")

    raw_handles: list[str] = [leet]
    for _, fmt in _PATTERN_TRANSFORMS:
        if fmt is None:
            continue
        try:
            raw_handles.append(fmt.format(base=base))
        except Exception:
            pass

    candidates: list[Candidate] = []
    ceiling = _GEN_CEILING["pattern_library"]
    for h in set(raw_handles):
        h = h.strip("._-")
        if len(h) < 2:
            continue
        for platform in platforms:
            candidates.append(Candidate(
                handle=h,
                platform=platform,
                base_score=ceiling,
                source="pattern_library",
                evidence={"generator": "pattern_library", "base": base},
            ))
    return candidates


# ── Public API ────────────────────────────────────────────────────────────────

async def generate_candidate_pool(
    username: str,
    display_name: str | None,
    bio: str | None,
    interest_tags: list[str],
    platforms: list[str] | None = None,
) -> list[Candidate]:
    """
    Run all five generators and return a deduplicated, size-limited candidate pool.

    Parameters
    ----------
    username      : the known platform username (e.g. Reddit handle)
    display_name  : optional display name
    bio           : optional bio text
    interest_tags : list of Empath/NLP interest tags
    platforms     : target platforms to search; defaults to common set

    Returns
    -------
    list[Candidate] sorted by base_score DESC, capped at MAX_CANDIDATES
    """
    if platforms is None:
        platforms = ["twitter", "instagram", "linkedin", "tiktok", "github"]

    gen1 = generate_username_variants(username, platforms)
    gen2 = generate_name_expansion(display_name, platforms)
    gen3 = generate_interest_injection(username, interest_tags, platforms)
    gen4 = await generate_ollama_handles(username, display_name, bio, interest_tags, platforms)
    gen5 = generate_pattern_library(username, platforms)

    merged = _dedup(gen1 + gen2 + gen3 + gen4 + gen5)
    merged.sort(key=lambda c: c.base_score, reverse=True)
    return merged[:MAX_CANDIDATES]
