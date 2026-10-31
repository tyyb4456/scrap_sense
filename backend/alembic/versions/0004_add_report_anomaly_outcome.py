"""add explicit report anomaly outcome

Revision ID: 0004_add_report_anomaly_outcome
Revises: 0003_add_anomaly_review_fields
Create Date: 2026-10-31 00:00:00.000000

Legacy accepted rows are never assumed to have passed Tier 1. The new column
defaults to ``unknown`` for every existing row. Only rows whose stored reason
matches a known deterministic Tier 1 result are backfilled. Raw picker text,
picker attribution, prices, and timestamps are not modified.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_add_report_anomaly_outcome"
down_revision: str | None = "0003_add_anomaly_review_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PASS_REASON_PREFIXES = (
    "Price is within the comparable range%",
    "Price matches the comparable median%",
)

INSUFFICIENT_REASON_PREFIXES = (
    "Not enough comparable historical reports%",
    "Not enough data to evaluate.%",
    "Comparable prices show no dispersion%",
    "Comparable prices could not be summarized.%",
    "A city is required before a report can be compared%",
    "A currency is required before prices can be compared.%",
    "A material is required before prices can be compared.%",
    "Candidate price is not a finite positive value.%",
    "Candidate unit is not kg%",
)

UNAVAILABLE_REASON_PREFIXES = (
    "Historical comparison was unavailable%",
)


def _like_any(column: str, prefixes: tuple[str, ...]) -> str:
    return " OR ".join(f"{column} LIKE '{prefix}'" for prefix in prefixes)


def upgrade() -> None:
    op.add_column(
        "reports",
        sa.Column(
            "anomaly_outcome",
            sa.String(length=30),
            server_default=sa.text("'unknown'"),
            nullable=False,
        ),
    )
    op.create_index(
        op.f("ix_reports_anomaly_outcome"),
        "reports",
        ["anomaly_outcome"],
        unique=False,
    )

    # Conservative backfill from reliable stored deterministic reasons only.
    op.execute(
        sa.text(
            "UPDATE reports SET anomaly_outcome = 'pass' "
            "WHERE status = 'accepted' AND is_anomalous = false "
            "AND anomaly_method = 'mad' AND ("
            + _like_any("anomaly_reason", PASS_REASON_PREFIXES)
            + ")"
        )
    )
    op.execute(
        sa.text(
            "UPDATE reports SET anomaly_outcome = 'insufficient_evidence' "
            "WHERE status = 'accepted' AND is_anomalous = false "
            "AND anomaly_method IN ('mad', 'deterministic') AND ("
            + _like_any("anomaly_reason", INSUFFICIENT_REASON_PREFIXES)
            + ")"
        )
    )
    op.execute(
        sa.text(
            "UPDATE reports SET anomaly_outcome = 'unavailable' "
            "WHERE status = 'accepted' AND is_anomalous = false "
            "AND ("
            + _like_any("anomaly_reason", UNAVAILABLE_REASON_PREFIXES)
            + ")"
        )
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_reports_anomaly_outcome"), table_name="reports")
    op.drop_column("reports", "anomaly_outcome")
