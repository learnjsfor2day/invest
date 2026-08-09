"""add dataset coverage state

Revision ID: 20260715_0006
Revises: 20260714_0005
Create Date: 2026-07-15
"""

from __future__ import annotations

from alembic import op

from pit_radar.db.models import DatasetCoverage

revision = "20260715_0006"
down_revision = "20260714_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    DatasetCoverage.__table__.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    DatasetCoverage.__table__.drop(bind=bind, checkfirst=True)
