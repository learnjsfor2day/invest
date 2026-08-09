"""add news and financial fact snapshots

Revision ID: 20260714_0002
Revises: 20260714_0001
Create Date: 2026-07-14
"""

from __future__ import annotations

from alembic import op

from pit_radar.db.models import FinancialFactSnapshot, NewsItemSnapshot

revision = "20260714_0002"
down_revision = "20260714_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    NewsItemSnapshot.__table__.create(bind=bind, checkfirst=True)
    FinancialFactSnapshot.__table__.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    FinancialFactSnapshot.__table__.drop(bind=bind, checkfirst=True)
    NewsItemSnapshot.__table__.drop(bind=bind, checkfirst=True)
