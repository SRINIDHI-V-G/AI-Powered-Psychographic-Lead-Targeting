"""
NLP layer models.

UserEmbedding   — sentence-transformer vector for a discovered user
UserNlpFeatures — extracted NLP signals: Empath, spaCy, linguistic metrics

Embedding storage strategy (dual-column for zero-downtime migration):
  embedding        — JSONB list-of-floats (384 dims) — backward compat, always populated
  embedding_vector — pgvector VECTOR(384) — populated by migration 005 and all new writes

The matching engine uses embedding_vector when available and falls back to the JSONB
column.  Once all rows have embedding_vector populated (after migration 005 data backfill),
the JSONB column can be dropped in a future migration.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

def _check_pgvector_available() -> bool:
    """
    Returns True only when BOTH the Python package AND the PostgreSQL extension
    are available. The package alone is not sufficient — migration 005 must have
    run successfully so the DB column is actually VECTOR(384), not JSONB.
    If the extension is missing the DB column is JSONB and pgvector's deserializer
    would crash with "'list' object has no attribute 'split'".
    """
    try:
        from pgvector.sqlalchemy import Vector  # noqa: F401 — just checking import
    except ImportError:
        return False
    # Check the DB extension at import time via a synchronous psycopg2 call.
    # This avoids the async-at-module-load-time problem. Falls back to False
    # on any error so the app boots safely even without pgvector.
    try:
        import os
        from sqlalchemy import create_engine, text as sa_text
        db_url = os.environ.get("DATABASE_URL", "")
        # Convert async URL to sync for this one-time check
        sync_url = db_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
        if not sync_url or "postgresql" not in sync_url:
            return False
        engine = create_engine(sync_url, pool_size=1, max_overflow=0)
        with engine.connect() as conn:
            r = conn.execute(sa_text("SELECT 1 FROM pg_extension WHERE extname='vector'"))
            has_ext = r.fetchone() is not None
        engine.dispose()
        return has_ext
    except Exception:
        return False


try:
    from pgvector.sqlalchemy import Vector as _Vector
    _HAS_PGVECTOR = _check_pgvector_available()
    _VECTOR_TYPE = _Vector(384) if _HAS_PGVECTOR else JSONB
except ImportError:
    _Vector = None
    _VECTOR_TYPE = JSONB
    _HAS_PGVECTOR = False


class UserEmbedding(Base):
    """
    384-dimensional sentence-transformer embedding for a discovered user.
    Generated from the combined text of their bio + posts + comments.
    Used by the matching engine for cosine similarity against motivation embeddings.
    """
    __tablename__ = "user_embeddings"

    __table_args__ = (
        UniqueConstraint("user_id", "embedding_type", name="uq_user_embedding_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("discovered_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # "combined" — bio + posts + comments concatenated (default and only type for Phase C)
    embedding_type: Mapped[str] = mapped_column(String(20), default="combined", nullable=False)

    # JSONB fallback — always populated for backward compatibility.
    # Schema: [float, float, ...] — exactly 384 L2-normalised floats.
    embedding: Mapped[list] = mapped_column(JSONB, nullable=False)

    # pgvector native column — populated from migration 005 onward.
    # Uses pgvector VECTOR(384) when pgvector package is installed; falls back
    # to nullable JSONB otherwise so the app boots without the extension.
    # The Alembic migration creates this as VECTOR(384) in the database.
    embedding_vector: Mapped[list | None] = mapped_column(
        _VECTOR_TYPE,   # Vector(384) or JSONB depending on installation
        nullable=True,
    )

    model_used: Mapped[str] = mapped_column(
        String(100), default="all-MiniLM-L6-v2", nullable=False
    )
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["DiscoveredUser"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "DiscoveredUser", back_populates="embedding"
    )


class UserNlpFeatures(Base):
    """
    NLP features extracted from a discovered user's combined public content.

    empath_scores     — dict of {category: float} from the Empath lexicon (~200 categories).
                        Only non-zero scores stored to reduce JSONB size.
    bertopic_topics   — list of {topic_id, probability} dicts from BERTopic.
                        Empty list if BERTopic is unavailable or < 2 posts.
    spacy_entities    — list of {text, label} dicts (ORG, GPE, PERSON, etc.)
    interest_tags     — top 10 Empath categories as a plain string list.
                        These are the primary signal for matching and OCEAN prompts.
    vocabulary_richness   — unique lemmas / total tokens (0.0–1.0)
    avg_sentence_length   — mean tokens per sentence
    total_tokens          — total non-stop, non-punct tokens in combined text
    """
    __tablename__ = "user_nlp_features"

    __table_args__ = (
        UniqueConstraint("user_id", name="uq_user_nlp_features"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("discovered_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Empath emotional/topic category scores (non-zero only)
    empath_scores: Mapped[dict] = mapped_column(JSONB, default=dict)

    # BERTopic assignments — empty list when BERTopic is unavailable
    bertopic_topics: Mapped[list] = mapped_column(JSONB, default=list)
    bertopic_probs: Mapped[list] = mapped_column(JSONB, default=list)

    # spaCy named entities
    spacy_entities: Mapped[list] = mapped_column(JSONB, default=list)

    # Derived signals used directly in OCEAN prompts and matching
    interest_tags: Mapped[list] = mapped_column(JSONB, default=list)
    keyword_frequency: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Linguistic metrics
    vocabulary_richness: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_sentence_length: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped["DiscoveredUser"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "DiscoveredUser", back_populates="nlp_features"
    )
