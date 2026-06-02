"""
BERTopic topic modeller — optional component.

BERTopic requires UMAP + HDBSCAN which uses 500MB+ of RAM.
For Phase C it is treated as optional:
  - If bertopic is not installed → returns empty topics silently.
  - If fewer than 2 texts are available → returns empty topics.
  - On any error → returns empty topics, logs warning.

Install to enable: pip install bertopic==0.16.0
RAM requirement: ~600MB peak. Not suitable for Railway free tier (512MB limit).
Defer to Phase G (infrastructure hardening) if memory is constrained.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class TopicModeler:
    """
    Optional singleton wrapper around BERTopic.
    Gracefully returns empty results when unavailable.
    """
    _instance: "TopicModeler | None" = None
    _model: object | None = None
    _available: bool | None = None

    def __new__(cls) -> "TopicModeler":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _check_available(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            import bertopic  # noqa: F401
            self._available = True
        except ImportError:
            logger.info(
                "BERTopic not installed — topic modelling disabled. "
                "Install with: pip install bertopic==0.16.0"
            )
            self._available = False
        return self._available  # type: ignore[return-value]

    def get_topics(self, texts: list[str]) -> list[dict]:
        """
        Fit BERTopic on texts and return topic assignments.
        Returns [] when BERTopic is unavailable or texts < 2.

        Return format: [{"topic_id": int, "probability": float}, ...]
        """
        if not self._check_available():
            return []
        if len(texts) < 2:
            return []
        try:
            if self._model is None:
                from bertopic import BERTopic  # type: ignore[import]
                self._model = BERTopic(min_topic_size=2, verbose=False)
            topics, probs = self._model.fit_transform(texts)  # type: ignore[union-attr]
            return [
                {"topic_id": int(t), "probability": float(p)}
                for t, p in zip(topics, probs)
            ]
        except Exception as exc:
            logger.warning("BERTopic failed: %s — returning empty topics", exc)
            return []
