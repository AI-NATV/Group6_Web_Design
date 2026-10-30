"""Saved datasets and dashboard visuals, against an in-memory test database."""

import pytest
from sqlmodel import select

from backend.config import MAX_FILE_SIZE
from backend.db_models import Dataset, Visual

DATASETS = "/api/v1/datasets"
VISUALS = "/api/v1/visuals"
CSV = b"date,region,revenue\n2026-09-01,North,100\n2026-09-02,South,250\n2026-09-02,South,250\n"
BAR = {"chart_type": "bar", "fields": {"dimension": "region", "measure": "revenue"}, "aggregation": "sum"}


def upload(client, name="sales.csv", contents=CSV):
    response = client.post(DATASETS, files={"file": (name, contents, "text/csv")})
    assert response.status_code == 201, response.text
    return response.json()


def test_upload_saves_the_dataset(client, session):
    created = upload(client)

    assert created["id"] == 1
    assert created["rows"] == 3
    assert created["columns"] == ["date", "region", "revenue"]
    assert created["semantic_model"] == {}
    stored = session.get(Dataset, created["id"])
    assert stored.filename == "sales.csv"
    assert stored.data[0]["revenue"] == 100


def test_upload_rejects_a_file_over_the_size_limit(client):
    response = client.post(DATASETS, files={"file": ("big.csv", b"a" * (MAX_FILE_SIZE + 1), "text/csv")})

    assert response.status_code == 413
    assert client.get(DATASETS).json() == []


def test_list_is_newest_first_without_row_data(client):
    upload(client, "first.csv")
    upload(client, "second.csv")

    listed = client.get(DATASETS).json()

    assert [item["filename"] for item in listed] == ["second.csv", "first.csv"]
    assert "data" not in listed[0] and "raw_data" not in listed[0]
    assert [item["filename"] for item in client.get(DATASETS, params={"offset": 1, "limit": 1}).json()] == ["first.csv"]


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1}])
def test_list_paging_is_bounded(client, params):
    assert client.get(DATASETS, params=params).status_code == 422


def test_read_one_dataset_and_missing_dataset(client):
    created = upload(client)

    assert client.get(f"{DATASETS}/{created['id']}").json()["raw_data"][0]["region"] == "North"
    missing = client.get(f"{DATASETS}/999")
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Dataset not found"}


def test_patch_saves_semantic_review_and_cleaned_rows(client):
    created = upload(client)
    semantic = {"region": {"type": "text", "role": "category", "confidence": "user-reviewed"}}

    response = client.patch(f"{DATASETS}/{created['id']}", json={"semantic_model": semantic, "data": created["data"][:2]})

    assert response.status_code == 200
    updated = client.get(f"{DATASETS}/{created['id']}").json()
    assert updated["semantic_model"] == semantic
    assert updated["rows"] == 2 and len(updated["data"]) == 2
    assert len(updated["raw_data"]) == 3, "raw rows stay as uploaded"


@pytest.mark.parametrize("body, status", [
    ({"semantic_model": {"unknown": {"type": "text"}}}, 400),
    ({"data": [{"unknown": 1}]}, 400),
    ({"semantic_model": None}, 422),
    ({"data": None}, 422),
    ({"data": "not rows"}, 422),
])
def test_patch_rejects_invalid_changes(client, body, status):
    created = upload(client)

    assert client.patch(f"{DATASETS}/{created['id']}", json=body).status_code == status
    assert client.get(f"{DATASETS}/{created['id']}").json()["rows"] == 3


def test_delete_removes_the_dataset_and_its_visuals(client, session):
    created = upload(client)
    client.post(f"{DATASETS}/{created['id']}/visuals", json=BAR)

    assert client.delete(f"{DATASETS}/{created['id']}").status_code == 204
    assert client.get(f"{DATASETS}/{created['id']}").status_code == 404
    assert session.exec(select(Visual)).all() == []
    assert client.delete(f"{DATASETS}/{created['id']}").status_code == 404


def test_visuals_are_saved_in_dashboard_order(client):
    dataset_id = upload(client)["id"]
    scatter = {"chart_type": "scatter", "fields": {"x": "revenue", "y": "revenue"}}

    first = client.post(f"{DATASETS}/{dataset_id}/visuals", json=BAR)
    second = client.post(f"{DATASETS}/{dataset_id}/visuals", json=scatter)

    assert first.status_code == 201 and second.status_code == 201
    assert [first.json()["position"], second.json()["position"]] == [0, 1]
    assert second.json()["aggregation"] == "sum"
    listed = client.get(f"{DATASETS}/{dataset_id}/visuals").json()
    assert [visual["chart_type"] for visual in listed] == ["bar", "scatter"]


@pytest.mark.parametrize("body", [
    {"chart_type": "bar", "fields": {"x": "revenue", "y": "revenue"}},
    {"chart_type": "scatter", "fields": {"dimension": "region", "measure": "revenue"}},
    {"chart_type": "area", "fields": {"dimension": "region", "measure": "revenue"}},
    {**BAR, "aggregation": "median"},
    {"chart_type": "bar", "fields": {"dimension": " ", "measure": "revenue"}},
])
def test_visual_body_must_match_its_chart_type(client, body):
    dataset_id = upload(client)["id"]

    assert client.post(f"{DATASETS}/{dataset_id}/visuals", json=body).status_code == 422


def test_visual_fields_must_be_dataset_columns(client):
    dataset_id = upload(client)["id"]
    body = {**BAR, "fields": {"dimension": "country", "measure": "revenue"}}

    response = client.post(f"{DATASETS}/{dataset_id}/visuals", json=body)

    assert response.status_code == 400
    assert "country" in response.json()["detail"]
    assert client.post(f"{DATASETS}/999/visuals", json=BAR).status_code == 404


def test_move_and_delete_keep_positions_contiguous(client):
    dataset_id = upload(client)["id"]
    ids = [client.post(f"{DATASETS}/{dataset_id}/visuals", json=BAR).json()["id"] for _ in range(3)]

    moved = client.patch(f"{VISUALS}/{ids[2]}", json={"position": 0})
    assert moved.status_code == 200 and moved.json()["position"] == 0
    order = [visual["id"] for visual in client.get(f"{DATASETS}/{dataset_id}/visuals").json()]
    assert order == [ids[2], ids[0], ids[1]]

    assert client.delete(f"{VISUALS}/{ids[0]}").status_code == 204
    remaining = client.get(f"{DATASETS}/{dataset_id}/visuals").json()
    assert [(visual["id"], visual["position"]) for visual in remaining] == [(ids[2], 0), (ids[1], 1)]


def test_missing_visual_and_invalid_position(client):
    dataset_id = upload(client)["id"]
    visual_id = client.post(f"{DATASETS}/{dataset_id}/visuals", json=BAR).json()["id"]

    assert client.patch(f"{VISUALS}/999", json={"position": 0}).status_code == 404
    assert client.delete(f"{VISUALS}/999").status_code == 404
    assert client.patch(f"{VISUALS}/{visual_id}", json={"position": -1}).status_code == 422
