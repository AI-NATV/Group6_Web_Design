"""Saved forecast runs: saved on every assisted forecast, listed and read by the owner only."""

from datetime import date, timedelta

DATASETS = "/api/v1/datasets"
RUNS = "/api/v1/forecast-runs"


def daily_csv(rows=60) -> bytes:
    start = date(2026, 1, 1)
    lines = ["date,revenue"] + [f"{(start + timedelta(days=i)).isoformat()},{100 + i % 7}" for i in range(rows)]
    return ("\n".join(lines) + "\n").encode()


def upload_dataset(client):
    response = client.post(DATASETS, files={"file": ("daily.csv", daily_csv(), "text/csv")})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def forecast_body(**overrides):
    body = {"time_column": "date", "target_column": "revenue", "horizon": 7, "frequency": "auto",
            "selected_features": [], "confirmed": False}
    body.update(overrides)
    return body


def test_a_forecast_is_saved_and_returned_with_its_run_id(alice):
    dataset_id = upload_dataset(alice)

    response = alice.post(f"{DATASETS}/{dataset_id}/forecast", json=forecast_body())

    assert response.status_code == 200, response.text
    run_id = response.json()["run_id"]
    assert isinstance(run_id, int)
    listed = alice.get(f"{DATASETS}/{dataset_id}/forecast-runs").json()
    assert [item["id"] for item in listed] == [run_id]
    assert listed[0]["selected_model"] == response.json()["selected_model"]


def test_a_saved_run_keeps_the_forecast_but_not_the_history_series(alice):
    dataset_id = upload_dataset(alice)
    run_id = alice.post(f"{DATASETS}/{dataset_id}/forecast", json=forecast_body()).json()["run_id"]

    run = alice.get(f"{RUNS}/{run_id}")

    assert run.status_code == 200
    body = run.json()
    assert body["horizon"] == 7 and body["time_column"] == "date"
    assert len(body["result"]["forecast"]) == 7
    assert "history" not in body["result"]


def test_runs_are_private_to_their_owner(alice, login, client):
    dataset_id = upload_dataset(alice)
    run_id = alice.post(f"{DATASETS}/{dataset_id}/forecast", json=forecast_body()).json()["run_id"]
    bob = login("bob")

    assert client.get(f"{RUNS}/{run_id}", headers=bob).status_code == 403
    assert client.delete(f"{RUNS}/{run_id}", headers=bob).status_code == 403
    assert client.get(f"{DATASETS}/{dataset_id}/forecast-runs", headers=bob).status_code == 403


def test_owner_can_delete_a_run_and_missing_runs_are_404(alice):
    dataset_id = upload_dataset(alice)
    run_id = alice.post(f"{DATASETS}/{dataset_id}/forecast", json=forecast_body()).json()["run_id"]

    assert alice.delete(f"{RUNS}/{run_id}").status_code == 204
    assert alice.get(f"{RUNS}/{run_id}").status_code == 404
    assert alice.get(f"{DATASETS}/{dataset_id}/forecast-runs").json() == []
    assert alice.delete(f"{RUNS}/999").status_code == 404


def test_deleting_a_dataset_removes_its_runs(alice):
    dataset_id = upload_dataset(alice)
    run_id = alice.post(f"{DATASETS}/{dataset_id}/forecast", json=forecast_body()).json()["run_id"]

    assert alice.delete(f"{DATASETS}/{dataset_id}").status_code == 204
    assert alice.get(f"{RUNS}/{run_id}").status_code == 404


def test_failed_forecasts_are_not_saved(alice):
    dataset_id = upload_dataset(alice)

    response = alice.post(f"{DATASETS}/{dataset_id}/forecast", json=forecast_body(horizon=0))

    assert response.status_code == 422
    assert alice.get(f"{DATASETS}/{dataset_id}/forecast-runs").json() == []
