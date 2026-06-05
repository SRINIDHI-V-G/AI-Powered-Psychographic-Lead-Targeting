"""
Handle ranker — computes a composite handle_score for each candidate.

Four scoring components:

  username_similarity_score
    How similar the candidate handle is to the known username using
    normalised Levenshtein / longest-common-subsequence ratio.
    High similarity → the person likely reuses the same handle.

  interest_alignment_score
    Fraction of the user's interest tags present in the candidate string.
    Handles that embed interest keywords are self-labelling and stable.

  ocean_plausibility_score
    OCEAN predicts naming style preferences:
      High Openness         → creative, unusual handles; penalise generic patterns.
      High Conscientiousness → structured, formal handles (first.last); reward these.
      High Extraversion      → verbose, expressive handles; reward them.
      High Agreeableness    → friendly, plain names; reward simplicity.
      High Neuroticism       → no strong prior — neutral weight.

  fingerprint_consistency_score
    If bio extraction already found confirmed/extracted handles, reward
    candidates whose character n-gram fingerprint matches that known baseline.

Final handle_score:
  0.35 * username_similarity
+ 0.25 * interest_alignment
+ 0.20 * ocean_plausibility
+ 0.20 * fingerprint_consistency
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

from app.ml.handles.handle_generator import Candidate


@dataclass
class RankedHandle:
    handle: str
    platform: str
    handle_score: float
    username_similarity: float
    interest_alignment: float
    ocean_plausibility: float
    fingerprint_consistency: float
    source: str
    evidence: dict


# ── Levenshtein similarity ────────────────────────────────────────────────────

def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i]
        for j, cb in enumerate(b, 1):
            curr.append(min(
                prev[j] + 1,
                curr[j - 1] + 1,
                prev[j - 1] + (0 if ca == cb else 1),
            ))
        prev = curr
    return prev[-1]


def _lcs_length(a: str, b: str) -> int:
    m, n = len(a), len(b)
    dp = [[0] * (n + 1) for _ in range(2)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if a[i - 1] == b[j - 1]:
                dp[i % 2][j] = dp[(i - 1) % 2][j - 1] + 1
            else:
                dp[i % 2][j] = max(dp[(i - 1) % 2][j], dp[i % 2][j - 1])
    return dp[m % 2][n]


def compute_username_similarity(candidate: str, username: str) -> float:
    """
    0–100. Combines normalised edit distance and LCS ratio.
    Strips non-alphanumeric chars before comparison.
    """
    c = re.sub(r"[^a-z0-9]", "", candidate.lower())
    u = re.sub(r"[^a-z0-9]", "", username.lower())
    if not c or not u:
        return 0.0

    max_len = max(len(c), len(u))
    lev_ratio = 1.0 - _levenshtein(c, u) / max_len
    lcs_ratio = _lcs_length(c, u) / max_len

    raw = 0.6 * lev_ratio + 0.4 * lcs_ratio
    return round(raw * 100.0, 2)


# ── Interest alignment ────────────────────────────────────────────────────────

def compute_interest_alignment(candidate: str, interest_tags: list[str]) -> float:
    """
    0–100. Proportion of interest tags found (substring) in the candidate.
    Rewards handles that embed identity keywords.
    """
    if not interest_tags:
        return 30.0
    c_lower = candidate.lower()
    matches = sum(1 for tag in interest_tags if tag.lower() in c_lower)
    raw = matches / len(interest_tags)
    # Sigmoid-style amplification so even 1 match gives a useful signal
    amplified = 1.0 - math.exp(-3.0 * raw)
    return round(amplified * 100.0, 2)


# ── OCEAN plausibility ────────────────────────────────────────────────────────

def compute_ocean_plausibility(
    candidate: str,
    ocean: dict[str, float] | None,
) -> float:
    """
    0–100. Uses OCEAN dimensions (0-100 scale) to estimate naming style match.
    Returns 50.0 (neutral) when ocean is None.
    """
    if not ocean:
        return 50.0

    o = ocean.get("openness", 50.0) / 100.0
    c_ = ocean.get("conscientiousness", 50.0) / 100.0
    e = ocean.get("extraversion", 50.0) / 100.0
    a = ocean.get("agreeableness", 50.0) / 100.0

    # Complexity of the handle (length, separator use, digit use)
    alpha_only = re.sub(r"[^a-z]", "", candidate.lower())
    has_separator = bool(re.search(r"[._-]", candidate))
    has_digit = bool(re.search(r"\d", candidate))
    length = len(candidate)

    score = 50.0

    # High openness → creative / unusual handles
    if o > 0.6:
        if length > 10 or has_digit:
            score += (o - 0.6) * 25
    # High conscientiousness → structured (separator, real-name style)
    if c_ > 0.6:
        if has_separator:
            score += (c_ - 0.6) * 30
    # High extraversion → expressive, longer handles
    if e > 0.6:
        if length >= 8:
            score += (e - 0.6) * 20
    # High agreeableness → simple, plain names
    if a > 0.6:
        if not has_digit and not has_separator and len(alpha_only) >= 4:
            score += (a - 0.6) * 15

    return round(min(100.0, max(0.0, score)), 2)


# ── Fingerprint consistency ────────────────────────────────────────────────────

def _char_ngrams(text: str, n: int = 3) -> set[str]:
    text = re.sub(r"[^a-z0-9]", "", text.lower())
    return {text[i:i + n] for i in range(len(text) - n + 1)}


def compute_fingerprint_consistency(
    candidate: str,
    confirmed_handles: list[str],
) -> float:
    """
    0–100. Jaccard similarity between candidate's 3-gram fingerprint and the
    union of fingerprints from already-confirmed/extracted handles.
    Returns 50.0 when no confirmed handles are available.
    """
    if not confirmed_handles:
        return 50.0

    cand_grams = _char_ngrams(candidate)
    if not cand_grams:
        return 30.0

    baseline_grams: set[str] = set()
    for h in confirmed_handles:
        baseline_grams |= _char_ngrams(h)

    if not baseline_grams:
        return 50.0

    intersection = len(cand_grams & baseline_grams)
    union = len(cand_grams | baseline_grams)
    jaccard = intersection / union if union else 0.0
    return round(jaccard * 100.0, 2)


# ── Composite scorer ──────────────────────────────────────────────────────────

_W_USERNAME    = 0.35
_W_INTEREST    = 0.25
_W_OCEAN       = 0.20
_W_FINGERPRINT = 0.20


def rank_candidates(
    candidates: list[Candidate],
    username: str,
    interest_tags: list[str],
    ocean: dict[str, float] | None,
    confirmed_handles: list[str],
) -> list[RankedHandle]:
    """
    Score all candidates and return a list of RankedHandle ordered by
    handle_score descending.

    Parameters
    ----------
    candidates        : from handle_generator.generate_candidate_pool()
    username          : known username (used as similarity baseline)
    interest_tags     : user's NLP interest tags
    ocean             : user's OCEAN scores as {dim: 0-100 float} or None
    confirmed_handles : handles already confirmed/extracted from bio
    """
    ranked: list[RankedHandle] = []

    for cand in candidates:
        us = compute_username_similarity(cand.handle, username)
        ia = compute_interest_alignment(cand.handle, interest_tags)
        op = compute_ocean_plausibility(cand.handle, ocean)
        fc = compute_fingerprint_consistency(cand.handle, confirmed_handles)

        score = (
            _W_USERNAME    * us +
            _W_INTEREST    * ia +
            _W_OCEAN       * op +
            _W_FINGERPRINT * fc
        )

        ranked.append(RankedHandle(
            handle=cand.handle,
            platform=cand.platform,
            handle_score=round(score, 2),
            username_similarity=us,
            interest_alignment=ia,
            ocean_plausibility=op,
            fingerprint_consistency=fc,
            source=cand.source,
            evidence=cand.evidence,
        ))

    ranked.sort(key=lambda r: r.handle_score, reverse=True)
    return ranked
