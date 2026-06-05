"""
LeadHandle model.

Stores candidate social-media handles discovered for each pipeline user.
One user can have many handles across multiple platforms.

Tier hierarchy (descending confidence):
  confirmed  — verbatim handle found in the user's bio or profile URL
  extracted  — @mention or hyperlink parsed from bio text
  inferred   — derived from username transformation / fingerprint patterns
  predicted  — LLM or pattern-library candidate, not yet verified
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class LeadHandle(Base):
    __tablename__ = "lead_handles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    discovered_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("discovered_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Target platform for this handle, e.g. "twitter", "instagram", "linkedin"
    platform: Mapped[str] = mapped_column(String(30), nullable=False, index=True)

    # The candidate handle value (without leading @)
    handle: Mapped[str] = mapped_column(String(255), nullable=False)

    # Composite ranking score 0–100 (higher = more likely to be the real handle)
    handle_score: Mapped[float] = mapped_column(Float, nullable=False, index=True)

    # Weighted confidence 0–100. Subject to anti-overconfidence ceilings per tier.
    confidence: Mapped[float] = mapped_column(Float, default=50.0, nullable=False)

    # confirmed | extracted | inferred | predicted
    tier: Mapped[str] = mapped_column(
        String(20), default="predicted", nullable=False, index=True
    )

    # Evidence that drove generation/extraction.
    # Schema: {"source": str, "raw_text": str, "generator": str,
    #          "similarity": float, "interest_tags": [...]}
    evidence_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    # Verification signals (populated after a verification pass, if run).
    # Schema: {"verified": bool, "verification_method": str, "profile_exists": bool,
    #          "profile_url": str, "follower_count": int}
    verification_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    user: Mapped["DiscoveredUser"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "DiscoveredUser",
        back_populates="lead_handles",
    )
