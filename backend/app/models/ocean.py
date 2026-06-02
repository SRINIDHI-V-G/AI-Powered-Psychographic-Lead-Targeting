"""
OCEAN personality scoring model.

UserOceanScore stores the Big Five personality scores inferred from a
discovered user's public content via NLP signals + LLM reasoning.

Scale: 0-100 (50 = average/neutral).

NOTE on neuroticism vs emotional_stability:
  MotivationOceanProfile (motivation layer) stores `emotional_stability` (0-10).
  UserOceanScore (user layer) stores `neuroticism` (0-100).
  These are inverses. For Phase E matching:
    neuroticism = 100 - (emotional_stability * 10)
    emotional_stability = (100 - neuroticism) / 10
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class UserOceanScore(Base):
    """
    Big Five personality scores for a discovered user.
    Computed after NLP processing. One row per user (upserted on re-run).
    """
    __tablename__ = "user_ocean_scores"

    __table_args__ = (
        UniqueConstraint("user_id", name="uq_user_ocean_score"),
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

    # ── Big Five scores (0-100, 50 = average) ────────────────────────────────
    openness: Mapped[float] = mapped_column(Float, nullable=False)
    conscientiousness: Mapped[float] = mapped_column(Float, nullable=False)
    extraversion: Mapped[float] = mapped_column(Float, nullable=False)
    agreeableness: Mapped[float] = mapped_column(Float, nullable=False)
    # NOTE: neuroticism is the inverse of emotional_stability used in
    # MotivationOceanProfile. See module docstring for the conversion formula.
    neuroticism: Mapped[float] = mapped_column(Float, nullable=False)

    # How confident are we in these scores? (0-100)
    confidence: Mapped[float] = mapped_column(Float, default=50.0)

    # How were these scores produced?
    # "llm"                 — scored by Ollama successfully
    # "heuristic"           — Empath-based heuristic (mock mode or LLM failed)
    # "insufficient_content"— too little text, all dimensions defaulted to 50
    scoring_method: Mapped[str] = mapped_column(
        String(30), nullable=False, default="heuristic"
    )

    # Per-dimension LLM reasoning strings (empty strings for heuristic scoring)
    # Schema: {"openness": "...", "conscientiousness": "...", ...}
    reasoning: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Raw LLM response (for debugging and audit; null for heuristic scores)
    raw_llm_response: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped["DiscoveredUser"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "DiscoveredUser", back_populates="ocean_score"
    )
