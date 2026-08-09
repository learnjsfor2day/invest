"""add macro event snapshots

Revision ID: 20260714_0005
Revises: 20260714_0004
Create Date: 2026-07-14
"""

from __future__ import annotations

from alembic import op

from pit_radar.db.models import MacroEventSnapshot

revision = "20260714_0005"
down_revision = "20260714_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    MacroEventSnapshot.__table__.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    MacroEventSnapshot.__table__.drop(bind=bind, checkfirst=True)
