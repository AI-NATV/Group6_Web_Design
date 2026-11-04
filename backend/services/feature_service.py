"""Explainable, local feature review and fixed-origin multi-output Ridge.

The review sees only the initial training window. Each supervised sample uses
a historical snapshot to predict the entire following horizon. Imputation and
scaling are fitted anew within each training prefix, never on held-out data.
No LLM, external API, future regressors, or causal claims are involved.
"""

import hashlib
import json
import math
import re
from statistics import fmean

import numpy as np
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from backend.models import DatasetForecastTask, ForecastRequest
from backend.services.forecast_service import (
    ForecastValidationError, _date, _number, _prepare, run_forecast,
)

LOOKBACK = 7
MIN_SAMPLES = 12
MAX_COLUMNS = 100


def _prepared(dataset, task):
    known = set(dataset.columns)
    if task.time_column not in known or task.target_column not in known:
        raise ForecastValidationError("Choose time and target columns from this dataset.")
    if len(dataset.data) > 50000:
        raise ForecastValidationError("Forecasting supports up to 50,000 rows. Use a smaller dataset.")
    rows = dataset.data
    if task.series_column:
        if task.series_column not in known or task.series_column in (task.time_column, task.target_column):
            raise ForecastValidationError("Choose a separate product/category column to filter one series.")
        rows = [row for row in rows if row.get(task.series_column) == task.series_value
                and isinstance(row.get(task.series_column), bool) == isinstance(task.series_value, bool)]
    if not rows:
        raise ForecastValidationError("No rows match this series. Choose another product/category.")
    request = ForecastRequest(**task.model_dump(include=set(ForecastRequest.model_fields) - {"observations"}),
                              observations=[{"date": row.get(task.time_column), "value": row.get(task.target_column)} for row in rows])
    dates, values, _, _, quality = _prepare(request)
    groups = {}
    for row in rows:
        day = _date(row.get(task.time_column))
        if day is not None and _number(row.get(task.target_column)) is not None:
            groups.setdefault(day, []).append(row)
    return request, dates, values, groups, quality


def _series(groups, dates, column, policy):
    result = []
    for day in dates:
        numbers = [_number(row.get(column)) for row in groups[day]]
        # Never silently sum/average a partially missing group.
        if any(value is None for value in numbers):
            result.append(None)
        else:
            result.append(math.fsum(numbers) if policy == "sum" else fmean(numbers))
    return result


def _review_token(dataset, task):
    payload = {"id": dataset.id, "revision": str(dataset.updated_at),
               "task": DatasetForecastTask(**task.model_dump()).model_dump(), "version": 1}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def _correlation(left, right):
    pairs = [(x, y) for x, y in zip(left, right) if x is not None]
    if len(pairs) < MIN_SAMPLES:
        return None
    x, y = np.array(pairs, dtype=float).T
    # Normalize before moments to keep large finite values numerically safe.
    x, y = x / max(1.0, max(abs(x))), y / max(1.0, max(abs(y)))
    if np.std(x) < 1e-14 or np.std(y) < 1e-14:
        return None
    return float(np.clip(np.corrcoef(x, y)[0, 1], -1, 1))


def recommend_features(dataset, task):
    if len(dataset.columns) > MAX_COLUMNS:
        raise ForecastValidationError("Feature review supports up to 100 columns. Use a smaller dataset or run baselines only.")
    _, dates, values, groups, quality = _prepared(dataset, task)
    end = len(values) - 3 * task.horizon
    train_dates, target = dates[:end], values[:end]
    samples = end - task.horizon - LOOKBACK + 1
    enough = samples >= MIN_SAMPLES
    candidates = []
    for column in dataset.columns:
        if column in (task.time_column, task.target_column, task.series_column):
            continue
        series = _series(groups, train_dates, column, task.duplicate_policy)
        present = [v for v in series if v is not None]
        missing = 1 - len(present) / end
        corr = _correlation(series[:-1], target[1:])
        semantic = (dataset.semantic_model or {}).get(column, {})
        role = semantic.get("role") if isinstance(semantic, dict) else None
        name = re.sub(r"([a-z])([A-Z])", r"\1_\2", column).lower()
        tokens = set(re.findall(r"[a-z0-9]+", name))
        if role == "identifier" or tokens & {"id", "uuid", "sku", "email", "phone", "password", "token", "address"}:
            reason = "identifier"
        elif tokens & {"future", "next", "lead", "predicted", "prediction", "forecast"}:
            reason = "futureRisk"
        elif not present:
            reason = "nonNumeric"
        elif missing > 0.2:
            reason = "missing"
        elif len(set(present)) < 2:
            reason = "constant"
        elif all(x is not None and x == y for x, y in zip(series, target)):
            reason = "targetCopy"
        elif not enough:
            reason = "shortTraining"
        else:
            reason = "laggedSignal" if corr is not None and abs(corr) >= 0.2 else "weakSignal"
        eligible = reason in ("laggedSignal", "weakSignal")
        candidates.append({"column": column, "eligible": eligible, "reason": reason,
                           "suggested": False, "missing_fraction": missing,
                           "lag1_correlation": corr, "training_dates": end})
    ranked = sorted((c for c in candidates if c["eligible"] and c["reason"] == "laggedSignal"),
                    key=lambda c: -abs(c["lag1_correlation"]))
    for candidate in ranked[:3]:
        candidate["suggested"] = True
    return {"method": "rules_and_training_statistics", "review_token": _review_token(dataset, task),
            "training_start": dates[0].isoformat(), "training_end": dates[end - 1].isoformat(),
            "training_dates": end, "supervised_samples": max(0, samples), "ridge_available": enough,
            "candidates": candidates, "quality": quality,
            "feature_policy": "historical_snapshot", "max_features": 8}


def _ridge_predictor(feature_values, columns):
    def predict(prefix, horizon, _season_length):
        end = len(prefix)
        # Row at origin o contains ONLY values with indices < o.
        def snapshot(origin):
            return [prefix[origin - lag] for lag in (1, 2, 3, 7)] + [fmean(prefix[origin - 7:origin])] + [
                feature_values[column][origin - 1] for column in columns]

        origins = range(LOOKBACK, end - horizon + 1)
        if len(origins) < MIN_SAMPLES:
            raise ForecastValidationError("Not enough training samples for Ridge. Use fewer forecast periods or more history.")
        x = np.array([snapshot(origin) for origin in origins], dtype=float)
        y = np.array([prefix[origin:origin + horizon] for origin in origins], dtype=float)
        pipeline = make_pipeline(SimpleImputer(strategy="median", keep_empty_features=True),
                                 StandardScaler(), Ridge(alpha=1.0, solver="svd"))
        pipeline.fit(x, y)
        prediction = np.asarray(pipeline.predict(np.array([snapshot(end)], dtype=float))).reshape(-1)
        if not np.all(np.isfinite(prediction)):
            raise ForecastValidationError("Ridge produced non-finite values. Review the numeric scale of this dataset.")
        return prediction.tolist(), {"alpha": 1.0, "strategy": "direct_multi_output",
                                     "target_lags": [1, 2, 3, 7], "target_rolling_mean": 7,
                                     "feature_lag": 1, "features": columns,
                                     "feature_policy": "historical_snapshot",
                                     "imputation": "training_median", "training_samples": len(origins)}
    return predict


def _insights(dates, values, future):
    minimum = min(range(len(values)), key=values.__getitem__)
    maximum = max(range(len(values)), key=values.__getitem__)
    changes = [abs(b - a) for a, b in zip(values, values[1:])]
    largest = max(range(len(changes)), key=changes.__getitem__)
    window = min(7, len(changes))
    # 'Most volatile' is explicitly mean absolute change, not financial volatility.
    start = max(range(len(changes) - window + 1), key=lambda i: fmean(changes[i:i + window]))
    change = future[-1]["predicted"] - values[-1]
    return {"minimum": {"date": dates[minimum].isoformat(), "value": values[minimum]},
            "maximum": {"date": dates[maximum].isoformat(), "value": values[maximum]},
            "largest_change": {"from": dates[largest].isoformat(), "to": dates[largest + 1].isoformat(),
                               "absolute_change": changes[largest], "change": values[largest + 1] - values[largest]},
            "volatile_window": {"from": dates[start].isoformat(), "to": dates[start + window].isoformat(),
                                "transitions": window, "mean_absolute_change": fmean(changes[start:start + window])},
            "outlook": {"last_actual": values[-1], "final_prediction": future[-1]["predicted"],
                        "change": change, "percent_change": 100 * change / abs(values[-1]) if values[-1] else None}}


def assisted_forecast(dataset, task):
    selected = task.selected_features
    if len(set(selected)) != len(selected):
        raise ForecastValidationError("Select each feature only once.")
    if selected:
        review = recommend_features(dataset, task)
        if not task.confirmed or task.review_token != review["review_token"]:
            raise ForecastValidationError("Review the current dataset/settings and confirm the feature plan before training.")
        allowed = {c["column"] for c in review["candidates"] if c["eligible"]}
        if not set(selected) <= allowed:
            raise ForecastValidationError("One or more selected features are unavailable. Review the feature suggestions again.")
    request, dates, values, groups, _ = _prepared(dataset, task)
    features = {c: _series(groups, dates, c, task.duplicate_policy) for c in selected}
    extra = {"ridge_lagged": _ridge_predictor(features, selected)} if selected else {}
    try:
        result = run_forecast(request, extra_predictors=extra)
    except (ValueError, ArithmeticError, np.linalg.LinAlgError) as error:
        if isinstance(error, ForecastValidationError):
            raise
        raise ForecastValidationError("Could not fit the selected features. Review their numeric scale or run baselines only.") from error
    result["feature_plan"] = {"method": "rules_and_training_statistics", "selected_features": selected,
                              "feature_policy": "historical_snapshot", "confirmed": bool(selected and task.confirmed),
                              "used_by_selected_model": selected if result["selected_model"] == "ridge_lagged" else [],
                              "review_training_end": review["training_end"] if selected else None,
                              "series_column": task.series_column, "series_value": task.series_value}
    result["insights"] = _insights(dates, values, result["forecast"])
    return result
