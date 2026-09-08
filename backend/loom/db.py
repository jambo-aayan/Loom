from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from loom.models import Base
from loom.settings import get_settings


def make_engine(database_url: str | None = None):
    url = database_url or get_settings().database_url
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args)


_engine = None
_SessionLocal: sessionmaker | None = None


def init_db(database_url: str | None = None) -> None:
    global _engine, _SessionLocal
    _engine = make_engine(database_url)
    _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    # sqlite only: local dev/tests want a ready schema with no separate migration step. A real
    # deployment (Postgres) must go through Alembic as the sole source of truth for schema — this
    # ran unconditionally once, and a freshly deployed Cloud Run service's first request created
    # the whole schema (including enum types) directly via create_all() *before* `alembic upgrade
    # head` ever got a chance to run against the same database, so Alembic found its target
    # objects already existing and failed. See docs/deployment.md's migration step.
    if _engine.dialect.name == "sqlite":
        Base.metadata.create_all(_engine)


def get_session() -> Generator[Session, None, None]:
    if _SessionLocal is None:
        init_db()
    assert _SessionLocal is not None
    session = _SessionLocal()
    try:
        yield session
    finally:
        session.close()
