from __future__ import annotations

from pathlib import Path


class LocalRawObjectStore:
    def __init__(self, root: Path):
        self.root = root

    def put_bytes(self, path: str, data: bytes) -> str:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_bytes(data)
        return str(target)

    def get_bytes(self, uri: str) -> bytes:
        return Path(uri).read_bytes()

    def exists(self, uri: str) -> bool:
        return Path(uri).exists()
