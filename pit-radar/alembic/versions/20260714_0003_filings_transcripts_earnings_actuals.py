"""add filings, transcripts, and earnings actual fields

Revision ID: 20260714_0003
Revises: 20260714_0002
Create Date: 2026-07-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from pit_radar.db.models import EarningTranscriptSnapshot, SecFilingSnapshot

revision = "20260714_0003"
down_revision = "20260714_0002"
branch_labels = None
depends_on = None


EARNINGS_COLUMNS = [
    sa.Column("actual_eps", sa.Numeric(24, 6), nullable=True, comment="实际EPS"),
    sa.Column("actual_revenue", sa.Numeric(24, 6), nullable=True, comment="实际营收"),
    sa.Column("eps_surprise", sa.Numeric(24, 6), nullable=True, comment="EPS超预期值"),
    sa.Column("eps_surprise_percent", sa.Numeric(18, 8), nullable=True, comment="EPS超预期百分比"),
    sa.Column("revenue_surprise", sa.Numeric(24, 6), nullable=True, comment="营收超预期值"),
    sa.Column("revenue_surprise_percent", sa.Numeric(18, 8), nullable=True, comment="营收超预期百分比"),
]


def upgrade() -> None:
    bind = op.get_bind()
    existing = _columns(bind, "earnings_calendar_snapshot")
    for column in EARNINGS_COLUMNS:
        if column.name not in existing:
            op.add_column("earnings_calendar_snapshot", column.copy(), schema="pit")

    SecFilingSnapshot.__table__.create(bind=bind, checkfirst=True)
    EarningTranscriptSnapshot.__table__.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    EarningTranscriptSnapshot.__table__.drop(bind=bind, checkfirst=True)
    SecFilingSnapshot.__table__.drop(bind=bind, checkfirst=True)

    existing = _columns(bind, "earnings_calendar_snapshot")
    for column in reversed(EARNINGS_COLUMNS):
        if column.name in existing:
            op.drop_column("earnings_calendar_snapshot", column.name, schema="pit")


def _columns(bind, table_name: str) -> set[str]:
    inspector = sa.inspect(bind)
    return {column["name"] for column in inspector.get_columns(table_name, schema="pit")}
