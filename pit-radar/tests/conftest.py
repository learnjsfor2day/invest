from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from pit_radar.db.base import Base
from pit_radar.db.models import *  # noqa: F401,F403
from pit_radar.storage.local import LocalRawObjectStore


@pytest.fixture()
def engine():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def attach_schemas(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        for schema in ("core", "raw", "pit"):
            cursor.execute(f"ATTACH DATABASE ':memory:' AS {schema}")
        cursor.close()

    Base.metadata.create_all(engine)
    return engine


@pytest.fixture()
def session(engine):
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with factory() as session:
        yield session


@pytest.fixture()
def store(tmp_path: Path):
    return LocalRawObjectStore(tmp_path / "raw")
