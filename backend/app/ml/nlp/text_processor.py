"""
Basic text processor — pure Python replacement for spaCy.

spaCy 3.7/3.8 has a pydantic-v1-compat / Python 3.12 incompatibility.
Rather than carry that dependency, we implement the metrics we actually need
for OCEAN scoring and the matching engine using stdlib + regex.

Metrics produced:
  vocabulary_richness   — unique lemmas / total tokens (approximated via split)
  avg_sentence_length   — mean words per sentence
  total_tokens          — non-empty word count
  spacy_entities        — basic entity extraction using regex patterns for
                          Indian cities, organisations, and proper nouns
  keyword_frequency     — top-20 content words (non-stopword) with frequency

These metrics are stored in user_nlp_features and referenced in OCEAN prompts.
The approximation quality is sufficient for psychographic scoring — the OCEAN
LLM ultimately reads the user's actual post text, not just these metrics.
"""
from __future__ import annotations

import re
from collections import Counter

# ── Simple English stopwords ──────────────────────────────────────────────────
_STOPWORDS: frozenset[str] = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "must", "shall", "can", "need",
    "this", "that", "these", "those", "it", "its", "i", "me", "my",
    "we", "our", "you", "your", "he", "his", "she", "her", "they", "their",
    "what", "which", "who", "whom", "when", "where", "why", "how",
    "all", "any", "both", "each", "few", "more", "most", "other", "some",
    "such", "no", "not", "only", "same", "so", "than", "too", "very",
    "just", "as", "if", "while", "although", "because", "since", "until",
    "also", "even", "now", "then", "there", "here", "like", "really",
    "much", "many", "one", "two", "get", "got", "make", "made", "go",
    "going", "know", "think", "want", "use", "see", "come", "take", "time",
    "about", "up", "out", "into", "over", "after", "back", "way", "good",
    "new", "work", "still", "well", "down", "first", "long", "never",
    "am", "im", "dont", "cant", "wont", "its", "thats", "whats", "ive",
    "id", "ll", "re", "ve", "s", "t", "m",
})

# ── Basic sentence boundary detection ────────────────────────────────────────
_SENTENCE_END = re.compile(r"[.!?]+")
# ── Non-word removal for tokenisation ─────────────────────────────────────────
_NON_WORD = re.compile(r"[^a-zA-Z0-9\s]")
# ── Named entity patterns (India-specific) ────────────────────────────────────
_CITY_PATTERN = re.compile(
    r"\b(Chennai|Madras|Bangalore|Bengaluru|Mumbai|Bombay|Delhi|"
    r"Hyderabad|Kolkata|Calcutta|Pune|Ahmedabad|Jaipur|Kochi|"
    r"Surat|Lucknow|Kanpur|Nagpur|Indore|Bhopal|Patna|Vadodara)\b",
    re.IGNORECASE,
)
_ORG_INDICATORS = re.compile(
    r"\b([A-Z][a-zA-Z]+ (?:Ltd|Pvt|Inc|Corp|Foundation|University|Institute|"
    r"College|School|Hospital|Group|Technologies|Solutions|Services|Consulting))\b"
)


def extract_features(text: str) -> dict:
    """
    Compute basic NLP features from cleaned text.

    Returns:
      {
        "entities": [{"text": str, "label": str}, ...],
        "vocabulary_richness": float,
        "avg_sentence_length": float,
        "total_tokens": int,
        "keyword_frequency": {word: count, ...}  # top 20 content words
      }
    """
    if not text or not text.strip():
        return {
            "entities": [],
            "vocabulary_richness": 0.0,
            "avg_sentence_length": 0.0,
            "total_tokens": 0,
            "keyword_frequency": {},
        }

    # ── Named entities ────────────────────────────────────────────────────────
    entities: list[dict] = []
    for m in _CITY_PATTERN.finditer(text):
        entities.append({"text": m.group(), "label": "GPE"})
    for m in _ORG_INDICATORS.finditer(text):
        entities.append({"text": m.group(), "label": "ORG"})

    # Deduplicate entities by text
    seen: set[str] = set()
    unique_entities = []
    for e in entities:
        key = e["text"].lower()
        if key not in seen:
            seen.add(key)
            unique_entities.append(e)

    # ── Tokenisation ──────────────────────────────────────────────────────────
    words_raw = text.lower().split()
    words = [_NON_WORD.sub("", w) for w in words_raw]
    words = [w for w in words if w and len(w) > 1]

    total_tokens = len(words)
    unique_lemmas = len(set(words))

    vocabulary_richness = (
        round(unique_lemmas / total_tokens, 4) if total_tokens > 0 else 0.0
    )

    # ── Sentence length ───────────────────────────────────────────────────────
    sentences = [s.strip() for s in _SENTENCE_END.split(text) if s.strip()]
    if sentences:
        sentence_word_counts = [len(s.split()) for s in sentences]
        avg_sentence_length = round(
            sum(sentence_word_counts) / len(sentence_word_counts), 2
        )
    else:
        avg_sentence_length = float(total_tokens)

    # ── Keyword frequency (content words only) ────────────────────────────────
    content_words = [w for w in words if w not in _STOPWORDS and len(w) > 2]
    freq = Counter(content_words)
    keyword_frequency = dict(freq.most_common(20))

    return {
        "entities": unique_entities,
        "vocabulary_richness": vocabulary_richness,
        "avg_sentence_length": avg_sentence_length,
        "total_tokens": total_tokens,
        "keyword_frequency": keyword_frequency,
    }
