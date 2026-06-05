"""
ProductOceanProfile model.

Stores the single aggregated OCEAN vector for a registered product.
Derived by the product_ocean_service by averaging all motivation OCEAN
profiles after motivation generation completes.

Scale: all five dimensions stored as 0-100 floats, matching UserOceanScore.
This means the matching service can compare product OCEAN vs lead OCEAN
directly without any scale conversion.

One profile per product (enforced by UNIQUE constraint on product_id).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class ProductOceanProfile(Base):
    __tablename__ = "product_ocean_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # ── OCEAN dimensions (0-100 scale) ────────────────────────────────────────
    openness: Mapped[float] = mapped_column(Float, nullable=False)
    conscientiousness: Mapped[float] = mapped_column(Float, nullable=False)
    extraversion: Mapped[float] = mapped_column(Float, nullable=False)
    agreeableness: Mapped[float] = mapped_column(Float, nullable=False)
    neuroticism: Mapped[float] = mapped_column(Float, nullable=False)

    # How many motivation profiles were averaged to produce this vector.
    # Higher = more representative (more buyer personas contributed).
    confidence: Mapped[float] = mapped_column(Float, default=50.0, nullable=False)
    component_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Always "motivation_average" for now. Reserved for future strategies
    # (e.g., "llm_synthesized" if we later prompt the LLM directly).
    derivation_method: Mapped[str] = mapped_column(
        String(20), default="motivation_average", nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # ── Relationship ──────────────────────────────────────────────────────────
    product: Mapped["Product"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Product", back_populates="ocean_profile"
    )
