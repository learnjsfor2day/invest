from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Protocol


@dataclass(frozen=True)
class CollectionContext:
    collection_mode: str
    symbols: list[str]
    fetched_at: datetime
    from_date: date | None = None
    to_date: date | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RawCollectionItem:
    request_key: str
    data: dict[str, Any]
    source_published_at: datetime | None = None
    http_status: int | None = 200
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CollectionResult:
    items: list[RawCollectionItem]
    errors: list[str] = field(default_factory=list)


class DataCollector(Protocol):
    dataset_code: str
    source_code: str

    async def collect(self, context: CollectionContext) -> CollectionResult: ...
