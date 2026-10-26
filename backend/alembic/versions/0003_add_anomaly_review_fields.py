"""add observed-at and review fields

Revision ID: 0003_add_anomaly_review_fields
Revises: 0002_create_chat_threads
Create Date: 2026-10-26 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_add_anomaly_review_fields"
down_revision: str | None = "0002_create_chat_threads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "reports",
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "reports",
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "reports",
        sa.Column("reviewed_by", sa.String(length=128), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("reports", "reviewed_by")
    op.drop_column("reports", "reviewed_at")
    op.drop_column("reports", "observed_at")
