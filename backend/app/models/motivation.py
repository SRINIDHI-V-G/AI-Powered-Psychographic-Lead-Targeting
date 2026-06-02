import uuid
from datetime import datetime
from sqlalchemy import String, Text, DateTime, ForeignKey, Integer, Float, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.models.base import Base


class MotivationCategory(Base):
    __tablename__ = "motivation_categories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Audit trail: which enrichment signals contributed to this category's
    # generation. Populated when motivation generation uses enrichment context.
    # e.g. {"sources": ["amazon"], "top_signals": ["durability", "family"],
    #        "signal_count": 12}
    # Empty dict when generated without enrichment (most Phase A products).
    enrichment_context: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    ocean_profile: Mapped["MotivationOceanProfile | None"] = relationship(
        "MotivationOceanProfile",
        back_populates="motivation_category",
        uselist=False,
        cascade="all, delete-orphan",
    )


class MotivationOceanProfile(Base):
    __tablename__ = "motivation_ocean_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    motivation_category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("motivation_categories.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    openness: Mapped[float] = mapped_column(Float, nullable=False)
    conscientiousness: Mapped[float] = mapped_column(Float, nullable=False)
    extraversion: Mapped[float] = mapped_column(Float, nullable=False)
    agreeableness: Mapped[float] = mapped_column(Float, nullable=False)
    emotional_stability: Mapped[float] = mapped_column(Float, nullable=False)
    interest_tags: Mapped[list] = mapped_column(JSONB, default=list)
    search_keywords: Mapped[list] = mapped_column(JSONB, default=list)
    hashtags: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    motivation_category: Mapped["MotivationCategory"] = relationship(
        "MotivationCategory", back_populates="ocean_profile"
    )
