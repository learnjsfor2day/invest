"""initial point-in-time schemas

Revision ID: 20260714_0001
Revises:
Create Date: 2026-07-14
"""

from __future__ import annotations

from alembic import op

from pit_radar.db.base import Base
from pit_radar.db.models import *  # noqa: F401,F403

revision = "20260714_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.exec_driver_sql("CREATE SCHEMA IF NOT EXISTS core")
    bind.exec_driver_sql("CREATE SCHEMA IF NOT EXISTS raw")
    bind.exec_driver_sql("CREATE SCHEMA IF NOT EXISTS pit")
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
    bind.exec_driver_sql("DROP SCHEMA IF EXISTS pit CASCADE")
    bind.exec_driver_sql("DROP SCHEMA IF EXISTS raw CASCADE")
    bind.exec_driver_sql("DROP SCHEMA IF EXISTS core CASCADE")
