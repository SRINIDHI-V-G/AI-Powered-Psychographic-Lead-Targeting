"""
Discovery layer models.

DiscoveryJob     — tracks one discovery run for a product (one provider, one batch)
DiscoveredUser   — a real social-media user found during discovery
UserContent      — individual pieces of public content from a discovered user

These models ONLY represent discovered people and their content.
They never hold enrichment/review data — that lives in enrichment.py.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


# ── Discovery Job ─────────────────────────────────────────────────────────────

class DiscoveryJob(Base):
    """
    One discovery run for a product.
    A product can have multiple jobs (e.g., re-runs or different providers).
    """
    __tablename__ = "discovery_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider_name: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False)
    sources: Mapped[list] = mapped_column(JSONB, default=list)
    search_config: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Snapshot of which similar products and keywords were included in this run.
    similar_products_searched: Mapped[list | None] = mapped_column(
        JSONB, nullable=True
    )

    max_users: Mapped[int] = mapped_column(Integer, default=150)
    users_discovered: Mapped[int] = mapped_column(Integer, default=0)
    users_content_collected: Mapped[int] = mapped_column(Integer, default=0)

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

    # Relationships
    discovered_users: Mapped[list["DiscoveredUser"]] = relationship(
        "DiscoveredUser",
        back_populates="discovery_job",
        cascade="all, delete-orphan",
    )


# ── Discovered User ───────────────────────────────────────────────────────────

class DiscoveredUser(Base):
    """
    A real, identifiable social-media user discovered during a discovery job.
    This is the entry point for the NLP → OCEAN → Matching pipeline.

    IMPORTANT: This table only holds users who are real people with public
    profiles that can potentially be contacted or targeted as leads.
    Anonymous reviewers from Amazon/Trustpilot/etc. are NEVER stored here.
    """
    __tablename__ = "discovered_users"

    __table_args__ = (
        UniqueConstraint(
            "platform", "platform_user_id", "discovery_job_id",
            name="uq_discovered_user_platform_job",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    discovery_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("discovery_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    platform: Mapped[str] = mapped_column(String(30), nullable=False)
    source_provider: Mapped[str] = mapped_column(String(50), nullable=False)
    platform_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    username: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # confirmed | inferred | regional | unknown
    location_confidence: Mapped[str] = mapped_column(
        String(20), default="unknown", nullable=False
    )

    follower_count: Mapped[int] = mapped_column(Integer, default=0)
    post_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    profile_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    raw_profile: Mapped[dict] = mapped_column(JSONB, default=dict)

    # "primary" | "similar_product"
    discovery_source: Mapped[str] = mapped_column(
        String(20), default="primary", nullable=False
    )
    # Which similar product triggered this user's discovery (NULL for primary).
    similar_product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("similar_products.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Pipeline progress flags
    content_collected: Mapped[bool] = mapped_column(Boolean, default=False)
    nlp_processed: Mapped[bool] = mapped_column(Boolean, default=False)
    ocean_scored: Mapped[bool] = mapped_column(Boolean, default=False)
    matched: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    discovery_job: Mapped["DiscoveryJob"] = relationship(
        "DiscoveryJob", back_populates="discovered_users"
    )
    # Many-to-one: many users can be discovered via one similar product.
    # lazy="select" defers loading until accessed; use selectinload() in queries
    # that need it to avoid N+1.
    similar_product: Mapped["SimilarProduct | None"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "SimilarProduct",
        back_populates="discovered_users",
        foreign_keys=[similar_product_id],
        lazy="select",
    )
    content_items: Mapped[list["UserContent"]] = relationship(
        "UserContent",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    embedding: Mapped["UserEmbedding | None"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "UserEmbedding",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    nlp_features: Mapped["UserNlpFeatures | None"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "UserNlpFeatures",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    ocean_score: Mapped["UserOceanScore | None"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "UserOceanScore",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    lead_matches: Mapped[list["LeadMatch"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "LeadMatch",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    lead_handles: Mapped[list["LeadHandle"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "LeadHandle",
        back_populates="user",
        cascade="all, delete-orphan",
    )


# ── User Content ──────────────────────────────────────────────────────────────

class UserContent(Base):
    """
    One piece of public content from a discovered user.
    Types: bio | post | comment
    This raw text flows directly into the NLP pipeline.
    """
    __tablename__ = "user_content"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("discovered_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    content_type: Mapped[str] = mapped_column(String(20), nullable=False)
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    engagement: Mapped[int] = mapped_column(Integer, default=0)
    posted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["DiscoveredUser"] = relationship(
        "DiscoveredUser", back_populates="content_items"
    )
