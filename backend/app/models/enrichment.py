"""
Enrichment layer models — STUB for Phase B3.

These tables store market intelligence extracted from review sites, datasets,
and other structured sources. They contain PATTERNS, not people.

Architecture contract:
  - Enrichment providers NEVER write to discovered_users or user_content.
  - Discovery providers NEVER write to these tables.
  - Enrichment signals flow into LLM prompts (motivation generation, OCEAN context).
    They do NOT modify user NLP features or OCEAN scores directly.

Implementation status: Tables defined here; providers implemented in Phase B3.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class EnrichmentJob(Base):
    """
    Tracks one enrichment run for a product from a specific source.
    Analogous to DiscoveryJob but for market intelligence, not users.
    """
    __tablename__ = "enrichment_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # e.g. "amazon_dataset", "trustpilot", "g2", "capterra", "mouthshut"
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False)
    items_processed: Mapped[int] = mapped_column(Integer, default=0)
    signals_extracted: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ProductEnrichmentSignal(Base):
    """
    A single extracted market intelligence signal for a product category.

    signal_type values:
      pain_point          — something buyers complain about or struggle with
      buying_criterion    — what buyers say explicitly drove their purchase
      personality_indicator — language/behaviour patterns observed in reviews
      sentiment_theme     — recurring emotional theme in the source data
      lifestyle_indicator — contextual signals about buyers' lifestyle
      decision_factor     — practical consideration in the purchase decision

    These signals are injected into motivation generation prompts and OCEAN
    scoring context to ground LLM outputs in real purchase behaviour data.
    They are NEVER scored as individual users or added to the lead pipeline.
    """
    __tablename__ = "product_enrichment_signals"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    enrichment_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("enrichment_jobs.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    signal_type: Mapped[str] = mapped_column(String(30), nullable=False)

    # Short extracted phrase (1-2 sentences max)
    signal_text: Mapped[str] = mapped_column(Text, nullable=False)

    # 0.0–1.0: how frequently this signal appears in the source data
    frequency_score: Mapped[float] = mapped_column(Float, default=0.0)

    # Lightweight OCEAN direction hints derived from this signal.
    # e.g. {"conscientiousness": "high", "openness": "medium"}
    # Not full scores — directional hints only. Full OCEAN scoring happens
    # per-user in the OCEAN pipeline, not here.
    ocean_hint: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Keywords extracted from this signal for NLP/matching context
    keywords: Mapped[list] = mapped_column(JSONB, default=list)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
