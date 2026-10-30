from copy import deepcopy
from datetime import date, timedelta

import pytest

from backend.models import ForecastRequest
from backend.services.forecast_service import metrics, predict, run_forecast



def payload(count=100, horizon=7):
    return {
        "time_column": "Date", "target_column": "Revenue", "horizon": horizon,
        "observations": [{"date": (date(2025, 1, 1) + timedelta(days=i)).isoformat(), "value": 100 + i}
                         for i in range(count)],
    }


def test_real_forecast_is_sorted_and_has_disjoint_splits(client):
    body = payload()
    body["observations"].reverse()
    response = client.post("/forecast", json=body)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["frequency"] == "daily"
    assert result["selected_model"] == "holt_damped"
    split = result["splits"]
    assert split["initial_train_end"] < split["validation_start"] <= split["validation_end"] < split["test_start"]
    assert len(result["backtest"]) == len(result["forecast"]) == 7
    assert result["forecast"][0]["date"] > split["test_end"]
    assert result["test_metrics"]["mae"] < result["naive_test_metrics"]["mae"]
    assert result["history"][0]["actual"] == 100


def test_changing_test_values_cannot_change_selection_or_test_predictions():
    body = payload()
    baseline = run_forecast(ForecastRequest(**body))
    changed = deepcopy(body)
    for point in changed["observations"][-7:]:
        point["value"] = 10000
    updated = run_forecast(ForecastRequest(**changed))
    assert baseline["selected_model"] == updated["selected_model"]
    assert baseline["comparison"] == updated["comparison"]
    assert [p["predicted"] for p in baseline["backtest"]] == [p["predicted"] for p in updated["backtest"]]
    assert baseline["test_metrics"] != updated["test_metrics"]
    assert baseline["forecast"] != updated["forecast"]  # final fit uses the full observed history


def test_each_validation_fold_predicts_from_its_own_prefix():
    result = run_forecast(ForecastRequest(**payload()))
    naive = next(item for item in result["comparison"] if item["model"] == "naive")
    assert naive["validation"]["mae"] == 4
    for fold in naive["folds"]:
        assert fold["train_end"] < fold["validation_start"]
        assert fold["mae"] == 4  # fixed-origin 7-step errors = 1,...,7, not 7 one-step forecasts


def test_seasonal_naive_wins_repeating_pattern():
    body = payload(count=120, horizon=8)
    body["season_length"] = 4
    for i, point in enumerate(body["observations"]):
        point["value"] = [10, 70, 25, 100][i % 4]
    result = run_forecast(ForecastRequest(**body))
    assert result["selected_model"] == "seasonal_naive"
    assert result["test_metrics"] == {"mae": 0, "rmse": 0}
    assert [point["predicted"] for point in result["forecast"]] == [10, 70, 25, 100] * 2


def test_zero_series_has_finite_metrics_and_naive_tie_break(client):
    body = payload()
    for point in body["observations"]:
        point["value"] = 0
    result = client.post("/forecast", json=body).json()
    assert result["selected_model"] == "naive"
    assert result["test_metrics"] == {"mae": 0, "rmse": 0}
    assert all(point["predicted"] == 0 for point in result["forecast"])


@pytest.mark.parametrize("value", [None, "", "$12.00", "1,234", "nan", "Infinity", True, {}, [], 1e101])
def test_invalid_targets_stop_unless_user_explicitly_drops(client, value):
    body = payload()
    body["observations"][5]["value"] = value
    response = client.post("/forecast", json=body)
    assert response.status_code == 400
    assert "data rows 6" in response.json()["detail"]
    body["missing_policy"] = "drop"
    response = client.post("/forecast", json=body)
    assert response.status_code == 200, response.text
    assert response.json()["quality"]["dropped_rows"] == 1
    assert response.json()["frequency"] == "observations"


@pytest.mark.parametrize("day", ["03/04/2025", "2025-02-30", None, 123, "2025-01-01T12:00:00"])
def test_invalid_or_ambiguous_dates_are_not_guessed(client, day):
    body = payload()
    body["observations"][0]["date"] = day
    assert client.post("/forecast", json=body).status_code == 400


def test_duplicates_require_explicit_aggregation(client):
    body = payload()
    body["observations"].append(deepcopy(body["observations"][0]))
    assert client.post("/forecast", json=body).status_code == 400
    body["duplicate_policy"] = "sum"
    result = client.post("/forecast", json=body).json()
    assert result["quality"]["duplicate_rows"] == 1
    assert result["history"][0]["actual"] == 200
    body["duplicate_policy"] = "mean"
    assert client.post("/forecast", json=body).json()["history"][0]["actual"] == 100


def test_irregular_dates_are_observation_steps_without_invented_future_dates(client):
    body = payload()
    del body["observations"][10]
    result = client.post("/forecast", json=body).json()
    assert result["frequency"] == "observations"
    assert all(point["date"] is None for point in result["forecast"])
    body["frequency"] = "daily"
    assert client.post("/forecast", json=body).status_code == 400


def test_month_end_and_weekly_calendars(client):
    import calendar
    body = payload(48)
    for i, point in enumerate(body["observations"]):
        year, month = 2021 + i // 12, i % 12 + 1
        point["date"] = date(year, month, calendar.monthrange(year, month)[1]).isoformat()
    result = client.post("/forecast", json=body).json()
    assert result["frequency"] == "monthly"
    assert result["forecast"][0]["date"] == "2025-01-31"
    assert result["forecast"][1]["date"] == "2025-02-28"
    body = payload()
    for i, point in enumerate(body["observations"]):
        point["date"] = (date(2023, 1, 1) + timedelta(weeks=i)).isoformat()
    result = client.post("/forecast", json=body).json()
    assert result["frequency"] == "weekly"
    assert date.fromisoformat(result["forecast"][0]["date"]) - date.fromisoformat(body["observations"][-1]["date"]) == timedelta(days=7)


def test_insufficient_data_and_invalid_configuration(client):
    assert client.post("/forecast", json=payload(12)).status_code == 400
    assert client.post("/forecast", json=payload(horizon=90)).status_code == 400
    for field, value, status in [("horizon", 0, 422), ("horizon", 91, 422), ("horizon", 1.5, 422),
                                  ("season_length", 1, 400), ("season_length", 60, 400),
                                  ("target_column", "Date", 400), ("frequency", "hourly", 422)]:
        body = payload()
        body[field] = value
        assert client.post("/forecast", json=body).status_code == status


def test_baseline_math_and_metrics():
    assert predict("naive", [1, 2, 3], 2)[0] == [3, 3]
    assert predict("moving_average", list(range(1, 9)), 2)[0] == [5, 5]
    assert metrics([1, 3], [2, 2]) == {"mae": 1, "rmse": 1}


def test_upload_to_forecast_uses_normalized_currency(client):
    rows = [f"{date(2025, 1, 1) + timedelta(days=i)},${100 + i}.125" for i in range(60)]
    uploaded = client.post("/api/v1/datasets", files={"file": ("prices.csv", ("Date,Close\n" + "\n".join(rows)).encode(), "text/csv")}).json()
    body = payload()
    body["target_column"] = "Close"
    body["observations"] = [{"date": row["Date"], "value": row["Close"]} for row in uploaded["data"]]
    response = client.post("/forecast", json=body)
    assert response.status_code == 200, response.text
    assert response.json()["history"][0]["actual"] == 100.125
