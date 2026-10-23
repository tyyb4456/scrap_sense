"""create final reports

Revision ID: 0001_create_final_reports
Revises:
Create Date: 2026-10-24 00:52:30.417760
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001_create_final_reports"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("picker_id", sa.String(length=128), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("material", sa.String(length=100), nullable=False),
        sa.Column("price_per_kg", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("quantity_kg", sa.Numeric(precision=12, scale=3), nullable=False),
        sa.Column(
            "currency",
            sa.String(length=3),
            server_default=sa.text("'PKR'"),
            nullable=False,
        ),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("area", sa.String(length=100), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column(
            "is_anomalous",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("anomaly_reason", sa.Text(), nullable=False),
        sa.Column("anomaly_method", sa.String(length=20), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default=sa.text("'accepted'"),
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
            "price_per_kg > 0",
            name=op.f("ck_reports_price_per_kg_positive"),
        ),
        sa.CheckConstraint(
            "quantity_kg > 0",
            name=op.f("ck_reports_quantity_kg_positive"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reports")),
    )
    op.create_index(
        op.f("ix_reports_picker_created"),
        "reports",
        ["picker_id", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_reports_picker_id"),
        "reports",
        ["picker_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_reports_status"),
        "reports",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_reports_status"), table_name="reports")
    op.drop_index(op.f("ix_reports_picker_id"), table_name="reports")
    op.drop_index(op.f("ix_reports_picker_created"), table_name="reports")
    op.drop_table("reports")
