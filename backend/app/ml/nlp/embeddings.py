"""
Sentence Transformer embedding model (all-MiniLM-L6-v2).

Singleton to avoid reloading the 90MB model on every NLP call.
First instantiation downloads the model (~90MB, one-time, cached).

Output: 384-dimensional L2-normalised float vector.
  - L2-normalised means dot(u, v) == cosine_similarity(u, v).
  - All embeddings stored as JSONB list[float] in user_embeddings.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer as _SentenceTransformer

logger = logging.getLogger(__name__)

_MODEL_NAME = "all-MiniLM-L6-v2"


class EmbeddingModel:
    """
    Singleton wrapper around SentenceTransformer.
    Thread-safe after the first construction.
    """
    _instance: "EmbeddingModel | None" = None
    _model: "_SentenceTransformer | None" = None

    def __new__(cls) -> "EmbeddingModel":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _load(self) -> None:
        if self._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer
            logger.info("Loading sentence-transformer model: %s", _MODEL_NAME)
            self._model = SentenceTransformer(_MODEL_NAME)
            logger.info("Embedding model loaded (%d dims)", self.dimensions)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to load embedding model {_MODEL_NAME}: {exc}"
            ) from exc

    @property
    def dimensions(self) -> int:
        return 384

    def encode(self, text: str) -> list[float]:
        """
        Encode a single text string to a 384-dim L2-normalised vector.
        Returns a plain Python list[float] suitable for JSONB storage.
        """
        self._load()
        if not text or not text.strip():
            return [0.0] * self.dimensions
        vec: np.ndarray = self._model.encode(  # type: ignore[union-attr]
            text, normalize_embeddings=True
        )
        return vec.tolist()

    def encode_batch(self, texts: list[str]) -> list[list[float]]:
        """Encode a batch of texts. More efficient than calling encode() in a loop."""
        self._load()
        if not texts:
            return []
        vecs: np.ndarray = self._model.encode(  # type: ignore[union-attr]
            texts, normalize_embeddings=True, batch_size=32, show_progress_bar=False
        )
        return vecs.tolist()

    @staticmethod
    def cosine_similarity(a: list[float], b: list[float]) -> float:
        """
        Cosine similarity between two L2-normalised vectors.
        Since both are unit vectors, this is just the dot product.
        """
        arr_a = np.array(a, dtype=np.float32)
        arr_b = np.array(b, dtype=np.float32)
        return float(np.dot(arr_a, arr_b))
