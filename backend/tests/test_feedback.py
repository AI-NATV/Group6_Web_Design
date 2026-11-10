"""Public feedback submission and administrator-only review."""

import pytest
from fastapi.testclient import TestClient
from sqlmodel import select

from backend.db_models import Feedback, Role
from backend.main import app


FEEDBACK = "/api/v1/feedback"
ADMIN_FEEDBACK = "/api/v1/admin/feedback"
MESSAGE = {"full_name": "  Mai Nguyen  ", "email": "  MAI@example.com ", "message": "  Please add a product comparison view.  "}


def test_public_feedback_is_normalized_and_persisted(client, session):
    response = client.post(FEEDBACK, json=MESSAGE)

    assert response.status_code == 201
    receipt = response.json()
    assert set(receipt) == {"id", "created_at"}
    saved = session.exec(select(Feedback)).one()
    assert saved.full_name == "Mai Nguyen"
    assert saved.email == "mai@example.com"
    assert saved.message == "Please add a product comparison view."


@pytest.mark.parametrize("changes", [
    {"full_name": "   "},
    {"email": "not-an-email"},
    {"message": "short"},
    {"message": " " * 12},
    {"full_name": "x" * 101},
    {"message": "x" * 2001},
])
def test_feedback_rejects_invalid_fields(client, changes):
    response = client.post(FEEDBACK, json={**MESSAGE, **changes})

    assert response.status_code == 422


def test_only_admins_can_review_feedback(client, alice, login):
    submitted = client.post(FEEDBACK, json=MESSAGE)
    assert submitted.status_code == 201
    assert client.get(ADMIN_FEEDBACK).status_code == 401
    assert alice.get(ADMIN_FEEDBACK).status_code == 403

    admin = TestClient(app, headers=login("root", role=Role.admin))
    response = admin.get(ADMIN_FEEDBACK, params={"limit": 1})

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["email"] == "mai@example.com"
    assert response.json()[0]["message"] == "Please add a product comparison view."
