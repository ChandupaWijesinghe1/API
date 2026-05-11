"""Set DB URL before app import; isolate DB per test run."""

import os
import tempfile
from pathlib import Path
import sys
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

_fd, _TMP_DB = tempfile.mkstemp(suffix=".sqlite")
os.close(_fd)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{Path(_TMP_DB).as_posix()}")
sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from app import models as _models  # noqa: E402, F401 — register ORM metadata
from app.database import Base, engine  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402


@pytest.fixture(autouse=True)
def reset_db() -> Generator[None, None, None]:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(fastapi_app) as c:
        yield c
