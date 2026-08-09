from __future__ import annotations

from typing import Protocol


class RawObjectStore(Protocol):
    def put_bytes(self, path: str, data: bytes) -> str: ...

    def get_bytes(self, uri: str) -> bytes: ...

    def exists(self, uri: str) -> bool: ...
