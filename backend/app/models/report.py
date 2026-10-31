import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    Index,
    Numeric,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Report(Base):
    """A finalized scrap-sale report produced by the intake pipeline."""

    __tablename__ = "reports"
    __table_args__ = (
        CheckConstraint("price_per_kg > 0", name="price_per_kg_positive"),
        CheckConstraint("quantity_kg > 0", name="quantity_kg_positive"),
        Index("ix_reports_picker_created", "picker_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    picker_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)

    material: Mapped[str] = mapped_column(String(100), nullable=False)
    price_per_kg: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    quantity_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="PKR", server_default="PKR"
    )
    city: Mapped[str | None] = mapped_column(String(100))
    area: Mapped[str | None] = mapped_column(String(100))
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confidence: Mapped[float | None] = mapped_column(Float)

    is_anomalous: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    anomaly_reason: Mapped[str] = mapped_column(Text, nullable=False)
    anomaly_method: Mapped[str] = mapped_column(String(20), nullable=False)
    anomaly_outcome: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="unknown",
        server_default="unknown",
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="accepted", server_default="accepted", index=True
    )

    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[str | None] = mapped_column(String(128))

    @property
    def effective_observed_at(self) -> datetime:
        """Use the reported sale time when present, else the save time."""
        return self.observed_at or self.created_at

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
