import os

# Point the app at an in-memory database before it is imported, so no test can touch data/app.db.
os.environ["DATABASE_URL"] = "sqlite://"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel

from backend import db_models  # noqa: F401  (registers the tables)
from backend.database import get_session, make_engine
from backend.main import app


# Tests use an in-memory SQLite database by default. Set TEST_DATABASE_URL to a
# separate, disposable PostgreSQL database to run them there; its tables are dropped.
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "sqlite://")


@pytest.fixture(name="session")
def session_fixture():
    """A fresh, empty database for every test."""

    in_memory = TEST_DATABASE_URL == "sqlite://"
    engine = make_engine(TEST_DATABASE_URL, **({"poolclass": StaticPool} if in_memory else {}))
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


@pytest.fixture(name="client")
def client_fixture(session):
    app.dependency_overrides[get_session] = lambda: session
    yield TestClient(app)
    app.dependency_overrides.clear()
