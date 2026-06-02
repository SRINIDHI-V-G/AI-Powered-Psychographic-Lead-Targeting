"""
NLP layer models.

UserEmbedding   — sentence-transformer vector for a discovered user
UserNlpFeatures — extracted NLP signals: Empath, spaCy, linguistic metrics

These rows feed directly into OCEAN scoring and the matching engine.
They are computed once per user and updated only if content is re-collected.

Embedding storage: JSONB list-of-floats (384 dimensions, all-MiniLM-L6-v2).
Using JSONB instead of pgvector keeps the setup dependency-free.
Migration to VECTOR(384) is a simple ALTER TABLE when pgvector is available (Phase G).
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

    # 384-element list of floats stored as JSONB.
    # Schema: [float, float, ...] — exactly 384 elements.
    # All embeddings are L2-normalised (unit vectors) so dot product == cosine similarity.
    embedding: Mapped[list] = mapped_column(JSONB, nullable=False)

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
