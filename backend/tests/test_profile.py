"""Profile fields, avatar, account deletion, and case-insensitive sign-in for legacy accounts."""

import base64

import pytest
from sqlmodel import select

from backend.db_models import Dataset, User
from backend.security import hash_password

TOKEN, ME = "/api/v1/token", "/api/v1/me"
PNG = "data:image/png;base64," + base64.b64encode(b"\x89PNG fake image bytes").decode()


def test_legacy_account_with_capitals_can_sign_in_with_any_case(client, session):
    # Accounts created before usernames were normalized still contain capital letters.
    session.add(User(username="Tuan", hashed_password=hash_password("password123")))
    session.commit()

    for name in ("Tuan", "tuan", "TUAN"):
        response = client.post(TOKEN, data={"username": name, "password": "password123"})
        assert response.status_code == 200, name


def test_patch_me_updates_display_name_and_phone_but_not_username(alice):
    response = alice.patch("/api/v1/me", json={"display_name": "  Tuấn  ", "phone": "+84 912 345 678", "username": "hacker"})

    assert response.status_code == 200
    body = response.json()
    assert body["display_name"] == "Tuấn"
    assert body["phone"] == "+84 912 345 678"
    assert body["username"] == "alice", "username is not editable through the profile"


@pytest.mark.parametrize("phone", ["abc", "123", "12345678901234567890123", "+84 91 x"])
def test_patch_me_rejects_invalid_phone(alice, phone):
    assert alice.patch("/api/v1/me", json={"phone": phone}).status_code == 422


def test_empty_optional_fields_are_stored_as_none(alice):
    alice.patch("/api/v1/me", json={"display_name": "   ", "phone": ""})

    body = alice.get("/api/v1/me").json()
    assert body["display_name"] is None and body["phone"] is None


def test_avatar_accepts_only_supported_image_data_urls(alice):
    assert alice.put("/api/v1/me/avatar", json={"avatar": PNG}).status_code == 200
    assert alice.get("/api/v1/me").json()["avatar"] == PNG

    assert alice.put("/api/v1/me/avatar", json={"avatar": "data:text/html;base64,PHNjcmlwdD4="}).status_code == 422
    assert alice.put("/api/v1/me/avatar", json={"avatar": "https://example.com/a.png"}).status_code == 422
    assert alice.put("/api/v1/me/avatar", json={"avatar": PNG + "A" * 200_000}).status_code == 422


def test_delete_me_needs_the_current_password_and_removes_datasets(alice, session, make_user):
    me = session.exec(select(User).where(User.username == "alice")).one()
    session.add(Dataset(owner_id=me.id, filename="a.csv", rows=0, columns=[], data=[], raw_data=[]))
    session.commit()

    assert alice.request("DELETE", "/api/v1/me", json={"password": "wrong-password"}).status_code == 403
    assert session.exec(select(User).where(User.username == "alice")).first() is not None

    assert alice.request("DELETE", "/api/v1/me", json={"password": "password123"}).status_code == 204
    session.expire_all()
    assert session.exec(select(User).where(User.username == "alice")).first() is None
    assert session.exec(select(Dataset).where(Dataset.owner_id == me.id)).first() is None
