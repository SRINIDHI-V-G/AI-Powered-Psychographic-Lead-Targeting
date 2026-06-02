"""
Empath emotional/topic category analyser.

Empath analyses text across ~200 categories (e.g. "affection", "achievement",
"leisure", "negative_emotion") using a neural expansion of the LIWC lexicon.

Singleton to avoid reloading the lexicon on every call.
Only non-zero scores are kept to minimise JSONB storage size.

Output fed into:
  - user_nlp_features.empath_scores (full dict)
  - user_nlp_features.interest_tags (top N categories as plain list)
  - OCEAN scoring prompt (context about user's dominant themes)
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from empath import Empath as _Empath

logger = logging.getLogger(__name__)

# Minimum score to include a category in results.
# Prevents noise from near-zero scores filling up JSONB.
_MIN_SCORE = 0.001


class EmpathAnalyzer:
    """Singleton wrapper around the Empath lexicon."""

    _instance: "EmpathAnalyzer | None" = None
    _lexicon: "_Empath | None" = None

    def __new__(cls) -> "EmpathAnalyzer":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _load(self) -> None:
        if self._lexicon is not None:
            return
        try:
            from empath import Empath
            logger.info("Loading Empath lexicon...")
            self._lexicon = Empath()
            logger.info("Empath lexicon loaded")
        except Exception as exc:
            raise RuntimeError(f"Failed to load Empath lexicon: {exc}") from exc

    def analyze(self, text: str) -> dict[str, float]:
        """
        Score text across ~200 emotional/topic categories.
        Returns only categories with score > _MIN_SCORE.
        Empty dict for empty/None input.
        """
        if not text or not text.strip():
            return {}
        self._load()
        raw: dict[str, float | None] = self._lexicon.analyze(  # type: ignore[union-attr]
            text, normalize=True
        ) or {}
        return {
            k: float(v)
            for k, v in raw.items()
            if v is not None and float(v) > _MIN_SCORE
        }

    def get_top_categories(
        self,
        scores: dict[str, float],
        n: int = 10,
    ) -> list[str]:
        """Return the top-n category names sorted by score descending."""
        sorted_cats = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [cat for cat, _ in sorted_cats[:n]]
