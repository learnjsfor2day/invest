from __future__ import annotations

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB

JSONBType = JSON().with_variant(JSONB, "postgresql")
