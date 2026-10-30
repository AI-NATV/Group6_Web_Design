"""Who may do what: 401 without a token, 403 on someone else's dataset, admins may access all."""

import pytest

from backend.db_models import Role

DATASETS, VISUALS = "/api/v1/datasets", "/api/v1/visuals"
CSV = b"region,revenue\nNorth,100\nSouth,250\n"
BAR = {"chart_type": "bar", "fields": {"dimension": "region", "measure": "revenue"}}


def upload(client, headers, name="sales.csv"):
    response = client.post(DATASETS, files={"file": (name, CSV, "text/csv")}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize("method, url", [
    ("get", DATASETS),
    ("post", DATASETS),
    ("get", f"{DATASETS}/1"),
    ("patch", f"{DATASETS}/1"),
    ("delete", f"{DATASETS}/1"),
    ("get", f"{DATASETS}/1/visuals"),
    ("post", f"{DATASETS}/1/visuals"),
    ("patch", f"{VISUALS}/1"),
    ("delete", f"{VISUALS}/1"),
])
def test_every_dataset_route_needs_login(client, method, url):
    response = client.request(method, url)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_public_routes_stay_public(client):
    assert client.get("/health").status_code == 200
    assert client.get("/app/").status_code == 200


def test_upload_is_owned_by_the_token_user(client, login):
    alice = login("alice")

    created = upload(client, alice)
    me = client.get("/api/v1/me", headers=alice).json()

    assert created["owner_id"] == me["id"]


def test_users_only_list_their_own_datasets(client, login):
    alice, bob = login("alice"), login("bob")
    upload(client, alice, "alice.csv")
    upload(client, bob, "bob.csv")

    assert [item["filename"] for item in client.get(DATASETS, headers=alice).json()] == ["alice.csv"]
    assert [item["filename"] for item in client.get(DATASETS, headers=bob).json()] == ["bob.csv"]


def test_other_user_gets_403_on_every_dataset_action(client, login):
    alice, bob = login("alice"), login("bob")
    dataset_id = upload(client, alice)["id"]
    visual_id = client.post(f"{DATASETS}/{dataset_id}/visuals", json=BAR, headers=alice).json()["id"]

    attempts = [
        client.get(f"{DATASETS}/{dataset_id}", headers=bob),
        client.patch(f"{DATASETS}/{dataset_id}", json={"data": []}, headers=bob),
        client.delete(f"{DATASETS}/{dataset_id}", headers=bob),
        client.get(f"{DATASETS}/{dataset_id}/visuals", headers=bob),
        client.post(f"{DATASETS}/{dataset_id}/visuals", json=BAR, headers=bob),
        client.patch(f"{VISUALS}/{visual_id}", json={"position": 0}, headers=bob),
        client.delete(f"{VISUALS}/{visual_id}", headers=bob),
    ]

    assert [response.status_code for response in attempts] == [403] * len(attempts)
    assert attempts[0].json() == {"detail": "You can only access your own datasets"}
    still_there = client.get(f"{DATASETS}/{dataset_id}", headers=alice).json()
    assert still_there["rows"] == 2
    assert len(client.get(f"{DATASETS}/{dataset_id}/visuals", headers=alice).json()) == 1


def test_missing_dataset_is_404_before_403(client, login):
    assert client.get(f"{DATASETS}/999", headers=login("bob")).status_code == 404


def test_admin_can_see_and_manage_every_dataset(client, login):
    alice, root = login("alice"), login("root", role=Role.admin)
    dataset_id = upload(client, alice)["id"]

    assert [item["id"] for item in client.get(DATASETS, headers=root).json()] == [dataset_id]
    assert client.get(f"{DATASETS}/{dataset_id}", headers=root).status_code == 200
    assert client.delete(f"{DATASETS}/{dataset_id}", headers=root).status_code == 204
    assert client.get(f"{DATASETS}/{dataset_id}", headers=alice).status_code == 404
