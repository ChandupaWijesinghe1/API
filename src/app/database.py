import os
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

# Set before importing app (e.g. in tests) to force DB URL.
# Docker Compose passes postgresql://...
_DEFAULT_SQLITE = "sqlite:///./api.sqlite"


def _database_url() -> str:
    return os.environ.get("DATABASE_URL", _DEFAULT_SQLITE)


def _make_engine(url: str):
    if url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
        if ":memory:" in url or url.rstrip("/") == "sqlite://":
            return create_engine(
                url,
                connect_args=connect_args,
                poolclass=StaticPool,
            )
        return create_engine(url, connect_args=connect_args)
    return create_engine(url, pool_pre_ping=True)


DATABASE_URL = _database_url()
engine = _make_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
