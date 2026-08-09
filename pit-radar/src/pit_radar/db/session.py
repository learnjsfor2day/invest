from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import Session, sessionmaker

from pit_radar.config import get_settings


def create_db_engine(database_url: str | None = None) -> Engine:
    settings = get_settings()
    url = database_url or settings.database_url
    connect_args = {"timeout": 60} if make_url(url).get_backend_name() == "sqlite" else {}
    engine = create_engine(url, future=True, connect_args=connect_args)
    _attach_sqlite_schemas(engine, url)
    return engine


def create_session_factory(engine: Engine | None = None) -> sessionmaker[Session]:
    return sessionmaker(bind=engine or create_db_engine(), expire_on_commit=False, future=True)


@contextmanager
def session_scope(factory: sessionmaker[Session] | None = None) -> Iterator[Session]:
    session = (factory or SessionLocal)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def create_schemas(engine: Engine) -> None:
    if engine.dialect.name == "sqlite":
        return
    with engine.begin() as conn:
        for schema in ("core", "raw", "pit"):
            conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))


def _attach_sqlite_schemas(engine: Engine, database_url: str) -> None:
    if engine.dialect.name != "sqlite":
        return

    schema_paths = _sqlite_schema_paths(database_url)

    @event.listens_for(engine, "connect")
    def attach_schemas(dbapi_conn, _) -> None:
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA busy_timeout = 60000")
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA database_list")
        attached = {row[1] for row in cursor.fetchall()}
        for schema, path in schema_paths.items():
            if schema in attached:
                continue
            escaped = str(path).replace("'", "''")
            cursor.execute(f"ATTACH DATABASE '{escaped}' AS {schema}")
        cursor.close()


def _sqlite_schema_paths(database_url: str) -> dict[str, str]:
    url = make_url(database_url)
    database = url.database
    if not database or database == ":memory:":
        return {schema: ":memory:" for schema in ("core", "raw", "pit")}

    db_path = Path(database).expanduser().resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    suffix = db_path.suffix or ".sqlite"
    return {schema: str(db_path.with_name(f"{db_path.stem}_{schema}{suffix}")) for schema in ("core", "raw", "pit")}


SessionLocal = create_session_factory()
