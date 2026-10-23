"""Create reports table.

Revision ID: 0001_create_reports
Revises:
Create Date: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001_create_reports"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("reporter_id", sa.String(length=128), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("material", sa.String(length=100), nullable=True),
        sa.Column("price_per_kg", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("quantity_kg", sa.Numeric(precision=12, scale=3), nullable=True),
        sa.Column(
            "currency",
            sa.String(length=3),
            server_default=sa.text("'PKR'"),
            nullable=False,
        ),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("area", sa.String(length=100), nullable=True),
        sa.Column("reported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "price_per_kg IS NULL OR price_per_kg > 0",
            name=op.f("ck_reports_price_per_kg_positive"),
        ),
        sa.CheckConstraint(
            "quantity_kg IS NULL OR quantity_kg > 0",
            name=op.f("ck_reports_quantity_kg_positive"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reports")),
    )
    op.create_index(op.f("ix_reports_city_material"), "reports", ["city", "material"], unique=False)
    op.create_index(op.f("ix_reports_reported_at"), "reports", ["reported_at"], unique=False)
    op.create_index(op.f("ix_reports_reporter_id"), "reports", ["reporter_id"], unique=False)
    op.create_index(op.f("ix_reports_status"), "reports", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_reports_status"), table_name="reports")
    op.drop_index(op.f("ix_reports_reporter_id"), table_name="reports")
    op.drop_index(op.f("ix_reports_reported_at"), table_name="reports")
    op.drop_index(op.f("ix_reports_city_material"), table_name="reports")
    op.drop_table("reports")
