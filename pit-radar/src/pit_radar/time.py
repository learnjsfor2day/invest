from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

NY_TZ = ZoneInfo("America/New_York")


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def parse_datetime(value: str) -> datetime:
    normalized = value.strip().replace("Z", "+00:00")
    return ensure_utc(datetime.fromisoformat(normalized))


def to_new_york(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return ensure_utc(value).astimezone(NY_TZ)
