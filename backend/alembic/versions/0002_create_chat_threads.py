"""create chat threads

Revision ID: 0002_create_chat_threads
Revises: 0001_create_final_reports
Create Date: 2026-10-24 01:15:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_create_chat_threads"
down_revision: str | None = "0001_create_final_reports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chat_threads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column(
            "title",
            sa.String(length=200),
            server_default=sa.text("'New chat'"),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chat_threads")),
    )
    op.create_index(
        op.f("ix_chat_threads_user_id"),
        "chat_threads",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_chat_threads_user_updated",
        "chat_threads",
        ["user_id", "updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_chat_threads_user_updated", table_name="chat_threads")
    op.drop_index(op.f("ix_chat_threads_user_id"), table_name="chat_threads")
    op.drop_table("chat_threads")
