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
    # Which provider ran this job — free-form string, not a DB enum,
    # so adding new providers never requires a migration.
    provider_name: Mapped[str] = mapped_column(String(50), nullable=False)

    # Job lifecycle: queued → running → collecting → completed | failed | cancelled
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False)

    # JSON list of platform sources requested, e.g. ["reddit"]
    sources: Mapped[list] = mapped_column(JSONB, default=list)

    # Full config passed to the orchestrator for this job
    search_config: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Requested upper bound
    max_users: Mapped[int] = mapped_column(Integer, default=150)

    # Running counters updated as the job progresses
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
        # Prevent the same user from being added twice to the same job
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

    # Platform where the user was found (display value): "reddit", "youtube", etc.
    platform: Mapped[str] = mapped_column(String(30), nullable=False)

    # Provider that found this user — free-form string, extensible without migration.
    # Examples: "reddit", "youtube_data_api", "discourse_forum"
    source_provider: Mapped[str] = mapped_column(String(50), nullable=False)

    # The platform's own stable identifier for this user (e.g. Reddit user.id)
    platform_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Public-facing username / handle
    username: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Bio / "about" text from their public profile
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Inferred location text (e.g., "Chennai") — NOT guaranteed accurate
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # How confident are we that the location is correct?
    # confirmed — city name explicitly in bio
    # inferred  — found via a city-specific subreddit/channel
    # regional  — country-level signal only (e.g., r/india participation)
    # unknown   — no geographic signals detected
    location_confidence: Mapped[str] = mapped_column(
        String(20), default="unknown", nullable=False
    )

    # Engagement proxy. For Reddit: link_karma + comment_karma.
    # NOT follower count (Reddit doesn't expose that). Named generically so
    # the matching engine doesn't need to know the platform's metric name.
    follower_count: Mapped[int] = mapped_column(Integer, default=0)

    # post_count intentionally omitted for Reddit — Reddit's API does not
    # expose actual post count, only karma totals. Storing an unreliable
    # estimate creates false precision. Set explicitly by providers that
    # DO have reliable post counts (e.g., YouTube subscriber video count).
    post_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Full public URL to the user's profile
    profile_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # Raw provider-specific data — kept for debugging, not used by pipeline
    raw_profile: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Pipeline progress flags
    content_collected: Mapped[bool] = mapped_column(Boolean, default=False)
    nlp_processed: Mapped[bool] = mapped_column(Boolean, default=False)
    ocean_scored: Mapped[bool] = mapped_column(Boolean, default=False)
    matched: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    discovery_job: Mapped["DiscoveryJob"] = relationship(
        "DiscoveryJob", back_populates="discovered_users"
    )
    content_items: Mapped[list["UserContent"]] = relationship(
        "UserContent",
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

    # bio | post | comment
    content_type: Mapped[str] = mapped_column(String(20), nullable=False)

    # The actual text. This feeds the NLP pipeline.
    content_text: Mapped[str] = mapped_column(Text, nullable=False)

    # Original URL (subreddit post URL, YouTube video URL, etc.)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # Engagement metric appropriate to platform (Reddit: score/upvotes, YouTube: likes)
    engagement: Mapped[int] = mapped_column(Integer, default=0)

    # When the content was originally posted (if available from the API)
    posted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationship
    user: Mapped["DiscoveredUser"] = relationship(
        "DiscoveredUser", back_populates="content_items"
    )
