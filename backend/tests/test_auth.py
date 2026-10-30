"""Registration, login and token validation: an auth system is defined by what it refuses."""

import base64
import json
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from sqlmodel import select

from backend.config import SECRET_KEY
from backend.db_models import Role, User
from backend.security import ALGORITHM

REGISTER, TOKEN, ME = "/api/v1/register", "/api/v1/token", "/api/v1/me"


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_register_stores_only_a_salted_hash(client, session):
    first = client.post(REGISTER, json={"username": "Alice", "password": "password123"})
    second = client.post(REGISTER, json={"username": "bob", "password": "password123"})

    assert first.status_code == 201
    assert first.json()["username"] == "alice", "usernames are case-insensitive"
    assert first.json()["role"] == "user"
    assert "password" not in first.json() and "hashed_password" not in first.json()
    hashes = [user.hashed_password for user in session.exec(select(User)).all()]
    assert all(value.startswith("$2b$") and "password123" not in value for value in hashes)
    assert hashes[0] != hashes[1], "same password, different salts"
    assert second.status_code == 201


def test_register_cannot_choose_the_admin_role(client):
    response = client.post(REGISTER, json={"username": "mallory", "password": "password123", "role": "admin"})

    assert response.status_code == 201
    assert response.json()["role"] == "user"


def test_duplicate_username_is_409(client):
    client.post(REGISTER, json={"username": "alice", "password": "password123"})

    response = client.post(REGISTER, json={"username": "ALICE", "password": "different-password"})

    assert response.status_code == 409
    assert response.json() == {"detail": "Username already taken"}


@pytest.mark.parametrize("body", [
    {"username": "al", "password": "password123"},
    {"username": "a" * 31, "password": "password123"},
    {"username": "alice smith", "password": "password123"},
    {"username": "alice", "password": "short"},
    {"username": "alice", "password": "ể" * 25},  # 25 characters but 75 bytes: over bcrypt's 72-byte limit
    {"username": "alice"},
])
def test_register_validation(client, body):
    assert client.post(REGISTER, json=body).status_code == 422


def test_login_returns_a_bearer_token_for_me(client, make_user):
    user = make_user("alice", "password123")

    response = client.post(TOKEN, data={"username": "Alice", "password": "password123"})

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
    token = response.json()["access_token"]
    payload = json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "=="))
    assert set(payload) == {"sub", "exp"}, "the readable payload carries no secrets"
    assert payload["sub"] == str(user.id)
    me = client.get(ME, headers=bearer(token))
    assert me.status_code == 200
    assert me.json()["username"] == "alice"


def test_wrong_password_and_unknown_user_get_the_same_401(client, make_user):
    make_user("alice", "password123")

    wrong_password = client.post(TOKEN, data={"username": "alice", "password": "Password123"})
    unknown_user = client.post(TOKEN, data={"username": "nobody", "password": "password123"})

    assert wrong_password.status_code == unknown_user.status_code == 401
    assert wrong_password.json() == unknown_user.json() == {"detail": "Incorrect username or password"}


def test_login_needs_form_fields(client):
    assert client.post(TOKEN, json={"username": "alice", "password": "password123"}).status_code == 422


def test_me_without_a_token(client):
    response = client.get(ME)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_expired_tampered_and_foreign_tokens_are_401(client, make_user):
    user = make_user()
    expired = jwt.encode(
        {"sub": str(user.id), "exp": datetime.now(timezone.utc) - timedelta(minutes=1)}, SECRET_KEY, algorithm=ALGORITHM,
    )
    valid = jwt.encode({"sub": str(user.id), "exp": datetime.now(timezone.utc) + timedelta(minutes=5)}, SECRET_KEY, algorithm=ALGORITHM)
    header, _payload, signature = valid.split(".")
    forged_payload = base64.urlsafe_b64encode(json.dumps({"sub": "2", "exp": 9999999999}).encode()).decode().rstrip("=")
    tampered = f"{header}.{forged_payload}.{signature}"
    other_key = jwt.encode({"sub": str(user.id), "exp": datetime.now(timezone.utc) + timedelta(minutes=5)}, "another-key-of-sufficient-length!", algorithm=ALGORITHM)
    no_expiry = jwt.encode({"sub": str(user.id)}, SECRET_KEY, algorithm=ALGORITHM)

    for token in [expired, tampered, other_key, no_expiry, "not-a-jwt"]:
        assert client.get(ME, headers=bearer(token)).status_code == 401, token
    assert client.get(ME, headers=bearer(valid)).status_code == 200


def test_deleted_user_is_locked_out(client, session, make_user):
    user = make_user()
    token = client.post(TOKEN, data={"username": "alice", "password": "password123"}).json()["access_token"]

    session.delete(user)
    session.commit()

    assert client.get(ME, headers=bearer(token)).status_code == 401


def test_role_comes_from_the_database(client, login):
    headers = login("root", role=Role.admin)

    assert client.get(ME, headers=headers).json()["role"] == "admin"
