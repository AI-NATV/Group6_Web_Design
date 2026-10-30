import os

# Point the app at an in-memory database before it is imported, so no test can touch data/app.db.
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SECRET_KEY"] = "test-only-secret-key-not-for-production-use"

import pytest
from fastapi.testclient import TestClient
from pwdlib import PasswordHash
from pwdlib.hashers.bcrypt import BcryptHasher
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel

from backend import db_models  # noqa: F401  (registers the tables)
from backend import security
from backend.database import get_session, make_engine
from backend.db_models import Role, User
from backend.main import app
from backend.security import hash_password

# bcrypt is slow on purpose (12 rounds). Tests use 4 rounds; each hash records its own cost, so verification is unchanged.
security.password_hash = PasswordHash((BcryptHasher(rounds=4),))


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
    """An anonymous client (no token)."""

    app.dependency_overrides[get_session] = lambda: session
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def make_user(session):
    def _make(username="alice", password="password123", role=Role.user) -> User:
        user = User(username=username, hashed_password=hash_password(password), role=role)
        session.add(user)
        session.commit()
        session.refresh(user)
        return user
    return _make


@pytest.fixture
def login(client, make_user):
    """Factory: login("bob") or login("root", role=Role.admin) returns Bearer headers."""

    def _login(username="alice", password="password123", role=Role.user) -> dict:
        make_user(username, password, role)
        response = client.post("/api/v1/token", data={"username": username, "password": password})  # a form, not JSON
        return {"Authorization": f"Bearer {response.json()['access_token']}"}
    return _login


@pytest.fixture
def alice(client, login):
    """A client logged in as the ordinary user alice."""

    return TestClient(app, headers=login("alice"))
