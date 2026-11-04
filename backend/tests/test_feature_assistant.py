"""Temporal isolation, confirmation, ownership, and numerical regression tests."""

from copy import deepcopy
from datetime import date, timedelta
import random

import numpy as np
import pytest

from backend.db_models import Dataset
from backend.models import AssistedForecastRequest, DatasetForecastTask, ForecastRequest
from backend.services.feature_service import (
    _ridge_predictor, _series, assisted_forecast, recommend_features,
)
from backend.services.forecast_service import ForecastValidationError, run_forecast


def dataset(count=120):
    rng = random.Random(125)
    signal = [rng.uniform(-10, 10) for _ in range(count)]
    rows = [{"Date": (date(2025, 1, 1) + timedelta(days=i)).isoformat(),
             "Price": 100 + 3 * signal[max(0, i - 1)], "Demand": signal[i],
             "OrderID": i, "NextPrice": signal[i], "Constant": 1,
             "Product": "A", "Sparse": None if i % 2 else i,
             "TargetCopy": 100 + 3 * signal[max(0, i - 1)]}
            for i in range(count)]
    return Dataset(id=1, owner_id=1, filename="features.csv", rows=count,
                   columns=list(rows[0]), data=rows, raw_data=deepcopy(rows))


def task(**kwargs):
    return DatasetForecastTask(time_column="Date", target_column="Price", **kwargs)


def confirmed(data, **kwargs):
    config = task(**kwargs)
    review = recommend_features(data, config)
    return AssistedForecastRequest(**config.model_dump(), selected_features=["Demand"],
                                   confirmed=True, review_token=review["review_token"])


def test_training_review_reasons_and_no_test_peeking():
    data = dataset()
    result = recommend_features(data, task())
    candidates = {item["column"]: item for item in result["candidates"]}
    assert candidates["Demand"]["lag1_correlation"] == pytest.approx(1.0)
    assert candidates["Demand"]["suggested"]
    for column, reason in {"OrderID": "identifier", "NextPrice": "futureRisk", "Constant": "constant",
                           "Product": "nonNumeric", "Sparse": "missing", "TargetCopy": "targetCopy"}.items():
        assert candidates[column]["reason"] == reason
        assert not candidates[column]["eligible"]
    for row in data.data[99:]:  # both validation windows AND test
        row.update(Price=9876, Demand=None, Constant=77, Product=123)
    changed = recommend_features(data, task())
    assert changed["candidates"] == result["candidates"]
    assert result["training_end"] == "2025-04-09"


def test_ridge_beats_baselines_on_known_lagged_signal():
    data = dataset(200)
    result = assisted_forecast(data, confirmed(data, horizon=1))
    assert len(result["comparison"]) == 4
    assert result["selected_model"] == "ridge_lagged"
    assert result["test_metrics"]["mae"] < result["naive_test_metrics"]["mae"]
    assert result["model_parameters"]["strategy"] == "direct_multi_output"
    assert result["feature_plan"]["used_by_selected_model"] == ["Demand"]


def test_holdout_values_never_change_selection_or_test_predictions():
    data = dataset(200)
    config = confirmed(data, horizon=7)
    result = assisted_forecast(data, config)
    for row in data.data[-7:]:
        row["Price"] += 999
        row["Demand"] = 888
    changed = assisted_forecast(data, config)
    assert result["comparison"] == changed["comparison"]
    assert result["selected_model"] == changed["selected_model"]
    assert [p["predicted"] for p in result["backtest"]] == [p["predicted"] for p in changed["backtest"]]
    assert result["test_metrics"] != changed["test_metrics"]


def test_ridge_fixed_origin_features_and_preprocessing_never_see_future():
    rng = random.Random(42)
    values = [rng.uniform(50, 100) for _ in range(90)]
    features = {"x": [None if i % 9 == 0 else rng.uniform(0, 100) for i in range(100)]}
    result, parameters = _ridge_predictor(features, ["x"])(values[:60], 7, 0)
    features["x"][60:] = [1e20] * 40
    changed, _ = _ridge_predictor(features, ["x"])(values[:60], 7, 0)
    assert result == changed
    assert parameters["training_samples"] == 47
    assert np.isfinite(result).all()


@pytest.mark.parametrize("changes", [{"confirmed": False}, {"review_token": None},
                                   {"review_token": "bad"}, {"horizon": 8}])
def test_selected_features_require_current_confirmation(changes):
    data = dataset()
    config = confirmed(data).model_copy(update=changes)
    with pytest.raises(ForecastValidationError, match="confirm"):
        assisted_forecast(data, config)


def test_dataset_revision_invalidates_review():
    data = dataset()
    config = confirmed(data)
    data.updated_at += timedelta(seconds=1)
    with pytest.raises(ForecastValidationError, match="confirm"):
        assisted_forecast(data, config)


@pytest.mark.parametrize("features", [["missingColumn"], ["Price"], ["NextPrice"], ["Demand", "Demand"]])
def test_unknown_excluded_target_and_duplicate_features_rejected(features):
    data = dataset()
    config = confirmed(data).model_copy(update={"selected_features": features})
    with pytest.raises(ForecastValidationError):
        assisted_forecast(data, config)


def test_baseline_path_matches_legacy_and_supports_wide_datasets():
    data = dataset()
    config = AssistedForecastRequest(**task().model_dump())
    result = assisted_forecast(data, config)
    legacy = run_forecast(ForecastRequest(**task().model_dump(exclude={"series_column", "series_value"}),
        observations=[{"date": row["Date"], "value": row["Price"]} for row in data.data]))
    for key, value in legacy.items():
        assert result[key] == value
    data.columns += [f"extra{i}" for i in range(101)]
    assert assisted_forecast(data, config)["forecast"] == result["forecast"]
    with pytest.raises(ForecastValidationError, match="100 columns"):
        recommend_features(data, task())


def test_short_training_disables_ridge_but_allows_baselines():
    data = dataset(41)
    review = recommend_features(data, task())
    assert not review["ridge_available"]
    assert not any(c["eligible"] for c in review["candidates"])
    result = assisted_forecast(data, AssistedForecastRequest(**task().model_dump()))
    assert len(result["forecast"]) == 7


def test_product_filter_is_applied_before_preparation():
    data = dataset()
    other = [dict(row, Product="B", Price=10000, Demand=-100) for row in data.data]
    expected = assisted_forecast(data, confirmed(data))
    data.data.extend(other)
    with pytest.raises(ForecastValidationError, match="share a date"):
        recommend_features(data, task())
    result = assisted_forecast(data, confirmed(data, series_column="Product", series_value="A"))
    assert result["forecast"] == expected["forecast"]
    assert result["quality"]["input_rows"] == 120
    with pytest.raises(ForecastValidationError, match="No rows match"):
        recommend_features(data, task(series_column="Product", series_value="unknown"))


def test_grouped_feature_sum_mean_and_partial_missing_handling():
    day = date(2025, 1, 1)
    groups = {day: [{"x": 10}, {"x": 20}]}
    assert _series(groups, [day], "x", "sum") == [30]
    assert _series(groups, [day], "x", "mean") == [15]
    groups[day][0]["x"] = None
    assert _series(groups, [day], "x", "sum") == [None]


def test_zero_target_insights_and_no_causal_or_percentage_infinity():
    data = dataset()
    for row in data.data:
        row["Price"] = 0
    result = assisted_forecast(data, confirmed(data))
    assert result["selected_model"] == "naive"
    assert result["insights"]["outlook"]["percent_change"] is None
    assert result["insights"]["volatile_window"]["mean_absolute_change"] == 0
    assert result["feature_plan"]["used_by_selected_model"] == []


def test_insights_have_correct_dates_and_changes():
    data = dataset()
    for i, row in enumerate(data.data):
        row["Price"] = i
    result = assisted_forecast(data, AssistedForecastRequest(**task().model_dump()))
    assert result["insights"]["minimum"] == {"date": "2025-01-01", "value": 0}
    assert result["insights"]["maximum"] == {"date": "2025-04-30", "value": 119}
    assert result["insights"]["volatile_window"]["mean_absolute_change"] == 1
    assert result["insights"]["largest_change"]["change"] == 1


def test_assisted_routes_require_login_and_ownership(alice, client, login):
    data = dataset()
    csv = "Date,Price,Demand\n" + "\n".join(f"{r['Date']},{r['Price']},{r['Demand']}" for r in data.data)
    uploaded = alice.post("/api/v1/datasets", files={"file": ("features.csv", csv, "text/csv")}).json()
    root = f"/api/v1/datasets/{uploaded['id']}"
    config = task(horizon=1).model_dump()
    bob_headers = login("bob")
    for suffix in ("feature-review", "forecast"):
        assert client.post(f"{root}/{suffix}", json=config).status_code == 401
        assert client.post(f"{root}/{suffix}", headers=bob_headers, json=config).status_code == 403
        assert alice.post(f"/api/v1/datasets/99999/{suffix}", json=config).status_code == 404
    review = alice.post(f"{root}/feature-review", json=config)
    assert review.status_code == 200
    config.update(selected_features=["Demand"], confirmed=True, review_token=review.json()["review_token"])
    result = alice.post(f"{root}/forecast", json=config)
    assert result.status_code == 200, result.text
    assert result.json()["selected_model"] == "ridge_lagged"
    assert result.json()["feature_plan"]["confirmed"]
    # Saved data, not browser cache, is the source of truth; updates require review.
    alice.patch(root, json={"semantic_model": {"Demand": {"type": "number", "role": "measure"}}})
    assert alice.post(f"{root}/forecast", json=config).status_code == 400


def test_api_request_limits(alice):
    path = "/api/v1/datasets/1/forecast"
    for change in ({"horizon": 0}, {"horizon": 91}, {"selected_features": [str(i) for i in range(9)]}):
        assert alice.post(path, json={**task().model_dump(), **change}).status_code == 422
