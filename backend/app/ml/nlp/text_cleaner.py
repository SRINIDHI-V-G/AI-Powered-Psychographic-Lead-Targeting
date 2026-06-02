"""
Text cleaning utilities.

clean_text() is the first step in the NLP pipeline. It normalises raw social
media content before it goes into the embedding model or Empath analyser.
"""
from __future__ import annotations

import re
import unicodedata


# Regex compiled once at import time for performance
_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_REDDIT_ARTIFACT_RE = re.compile(r"\[deleted\]|\[removed\]|&amp;|&lt;|&gt;|&nbsp;")
_WHITESPACE_RE = re.compile(r"\s+")
_REPEATED_PUNCT_RE = re.compile(r"([!?.]){3,}")  # !!! or ??? → !  (keep one)


def clean_text(text: str | None, lowercase: bool = False) -> str:
    """
    Normalise raw social media text for NLP processing.

    Steps applied in order:
      1. Handle None / empty input.
      2. Unicode NFKC normalisation (resolves fancy quotes, ligatures, etc.).
      3. Strip HTML tags.
      4. Remove Reddit-specific artefacts ([deleted], HTML entities).
      5. Remove URLs.
      6. Collapse repeated punctuation.
      7. Collapse whitespace.
      8. Optionally lowercase.

    Returns a clean string. Empty input returns "".
    """
    if not text:
        return ""

    # 1. Unicode normalisation
    text = unicodedata.normalize("NFKC", text)

    # 2. Strip HTML
    text = _HTML_TAG_RE.sub(" ", text)

    # 3. Reddit artefacts
    text = _REDDIT_ARTIFACT_RE.sub(" ", text)

    # 4. Remove URLs
    text = _URL_RE.sub(" ", text)

    # 5. Collapse repeated punctuation
    text = _REPEATED_PUNCT_RE.sub(r"\1", text)

    # 6. Normalise whitespace
    text = _WHITESPACE_RE.sub(" ", text).strip()

    if lowercase:
        text = text.lower()

    return text


def combine_user_content(bio: str | None, content_texts: list[str]) -> str:
    """
    Merge a user's bio and post/comment texts into one document.
    Bio is placed first so it's always within the embedding model's window.
    """
    parts: list[str] = []
    if bio:
        cleaned_bio = clean_text(bio)
        if cleaned_bio:
            parts.append(cleaned_bio)
    for text in content_texts:
        cleaned = clean_text(text)
        if cleaned:
            parts.append(cleaned)
    return " ".join(parts)
