"""add source document snapshots

Revision ID: 20260714_0004
Revises: 20260714_0003
Create Date: 2026-07-14
"""

from __future__ import annotations

from alembic import op

from pit_radar.db.models import SourceDocumentSnapshot

revision = "20260714_0004"
down_revision = "20260714_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    SourceDocumentSnapshot.__table__.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    SourceDocumentSnapshot.__table__.drop(bind=bind, checkfirst=True)
