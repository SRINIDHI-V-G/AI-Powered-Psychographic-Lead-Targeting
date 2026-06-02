import uuid
import enum
from datetime import datetime
from sqlalchemy import String, Text, DateTime, ForeignKey, Integer, Enum as SAEnum, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.models.base import Base


class PriceRange(str, enum.Enum):
    budget = "budget"
    mid_range = "mid_range"
    premium = "premium"
    luxury = "luxury"


class ProductStatus(str, enum.Enum):
    pending = "pending"
    analyzing = "analyzing"
    motivations_generated = "motivations_generated"
    discovering = "discovering"
    nlp_processing = "nlp_processing"
    ocean_scoring = "ocean_scoring"
    matching = "matching"
    ranked = "ranked"
    completed = "completed"
    failed = "failed"


class Product(Base):
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    subcategory: Mapped[str | None] = mapped_column(String(100), nullable=True)
    price_range: Mapped[PriceRange] = mapped_column(
        SAEnum(PriceRange, native_enum=False, length=20),
        nullable=False,
    )
    target_location: Mapped[str] = mapped_column(String(255), nullable=False)
    target_city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    target_country: Mapped[str] = mapped_column(String(100), default="India")
    keywords: Mapped[list] = mapped_column(JSONB, default=list)
    status: Mapped[ProductStatus] = mapped_column(
        SAEnum(ProductStatus, native_enum=False, length=30),
        default=ProductStatus.pending,
    )
    pipeline_step: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Tracks whether enrichment signals have been extracted for this product.
    # Values: none | processing | ready | failed
    # Populated by the enrichment pipeline (Phase B3).
    enrichment_status: Mapped[str] = mapped_column(
        String(20), default="none", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    company: Mapped["Company"] = relationship("Company", back_populates="products")
