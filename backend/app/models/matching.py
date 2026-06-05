"""
Lead matching model.

LeadMatch stores one psychographic match score per (user × motivation_category) pair.

After all users are scored for a product:
  - is_best_match=True  marks the motivation category that best fits each user
  - rank                is assigned only to is_best_match=True rows, ordered by
                        final_score DESC across all users for the product

This design preserves the full match matrix for audit/debug while supporting
fast ranked-lead queries via the is_best_match + rank index.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class LeadMatch(Base):
    """
    One psychographic match score for a (discovered user, motivation category) pair.
    """
    __tablename__ = "lead_matches"

    __table_args__ = (
        # One score per user per motivation category — upserted on re-run.
        UniqueConstraint(
            "user_id", "motivation_category_id",
            name="uq_lead_match_user_category",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("discovered_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    motivation_category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("motivation_categories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Component scores (0–100) ──────────────────────────────────────────────
    ocean_score: Mapped[float] = mapped_column(Float, nullable=False)
    embedding_score: Mapped[float] = mapped_column(Float, nullable=False)
    interest_score: Mapped[float] = mapped_column(Float, nullable=False)

    # OCEAN similarity between this lead and the product-level OCEAN vector.
    # Informational only — does NOT affect final_score. NULL if the product
    # has no ocean_profile yet (e.g., product predates this feature).
    product_ocean_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # ── Composite score (0–100) ───────────────────────────────────────────────
    final_score: Mapped[float] = mapped_column(Float, nullable=False, index=True)

    # ── Match quality metadata ─────────────────────────────────────────────────
    confidence: Mapped[float] = mapped_column(Float, default=50.0)

    # True for the motivation category that best matches this user.
    # Only one row per user has is_best_match=True.
    is_best_match: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    # Ordinal rank among all users for this product (1 = best).
    # Non-null only on is_best_match=True rows after ranking pass.
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Human-readable explanations for this match score.
    # Schema: ["reason 1", "reason 2", ...]
    reasoning: Mapped[list] = mapped_column(JSONB, default=list)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    user: Mapped["DiscoveredUser"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "DiscoveredUser", back_populates="lead_matches"
    )
    motivation_category: Mapped["MotivationCategory"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "MotivationCategory"
    )
