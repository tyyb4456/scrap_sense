import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    Numeric,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ReportStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    FLAGGED = "flagged"
    REJECTED = "rejected"


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (
        CheckConstraint(
            "price_per_kg IS NULL OR price_per_kg > 0",
            name="price_per_kg_positive",
        ),
        CheckConstraint(
            "quantity_kg IS NULL OR quantity_kg > 0",
            name="quantity_kg_positive",
        ),
        Index("ix_reports_city_material", "city", "material"),
        Index("ix_reports_reported_at", "reported_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    reporter_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)

    material: Mapped[str | None] = mapped_column(String(100))
    price_per_kg: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    quantity_kg: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="PKR", server_default="PKR"
    )
    city: Mapped[str | None] = mapped_column(String(100))
    area: Mapped[str | None] = mapped_column(String(100))
    reported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=ReportStatus.PENDING.value,
        server_default=ReportStatus.PENDING.value,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
