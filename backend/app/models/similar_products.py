"""
SimilarProduct model.

Each row represents one similar product found for a registered product.
The product_similarity_service generates these by:
  1. Calling the LLM to suggest similar products given the product's context
     and OCEAN profile.
  2. Asking the LLM to also supply an OCEAN profile for each candidate.
  3. Computing cosine similarity between the candidate OCEAN and the product OCEAN.
  4. Keeping only candidates above the similarity threshold (default 0.65).

The discovery_keywords list is what gets injected into the keyword search
during discovery — it tells Reddit/YouTube/Instagram what to search for
to find people discussing this similar product.

is_active lets a company disable a noisy similar product via the API
without deleting it from history.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class SimilarProduct(Base):
    __tablename__ = "similar_products"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Identity ──────────────────────────────────────────────────────────────
    similar_product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    similar_product_category: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    similar_product_description: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )

    # ── OCEAN profile of the similar product (0-100 scale, LLM-generated) ────
    openness: Mapped[float | None] = mapped_column(Float, nullable=True)
    conscientiousness: Mapped[float | None] = mapped_column(Float, nullable=True)
    extraversion: Mapped[float | None] = mapped_column(Float, nullable=True)
    agreeableness: Mapped[float | None] = mapped_column(Float, nullable=True)
    neuroticism: Mapped[float | None] = mapped_column(Float, nullable=True)

    similarity_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    discovery_keywords: Mapped[list] = mapped_column(JSONB, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    product: Mapped["Product"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Product", back_populates="similar_products"
    )
    # One-to-many: users discovered via this similar product's keywords.
    # Not cascade-deleted — losing a similar product record should not
    # delete the discovered users (they have scientific value independently).
    discovered_users: Mapped[list["DiscoveredUser"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "DiscoveredUser",
        back_populates="similar_product",
        foreign_keys="[DiscoveredUser.similar_product_id]",
        lazy="select",
    )
