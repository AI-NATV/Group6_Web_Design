"""Univariate forecasting with chronological validation and an untouched test set.

Only observations available at each forecast origin are supplied to a model.
The final horizon is reserved for testing, never for model selection.
"""

import calendar
import math
import re
from datetime import date, timedelta
from statistics import fmean

from backend.models import ForecastRequest


class ForecastValidationError(ValueError):
    pass


def _number(value):
    # Normalization belongs to import: do not guess currency/locale here.
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, str) and not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", value.strip()):
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) and abs(result) <= 1e100 else None
    except (TypeError, ValueError, OverflowError):
        return None


def _date(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _month_after(day, offset, month_end=False):
    month_index = day.year * 12 + day.month - 1 + offset
    year, month = divmod(month_index, 12)
    month += 1
    last = calendar.monthrange(year, month)[1]
    return date(year, month, last if month_end else min(day.day, last))


def _prepare(request):
    if request.time_column == request.target_column:
        raise ForecastValidationError("Choose different time and target columns.")
    if request.season_length == 1:
        raise ForecastValidationError("Season length must be 0 (disabled) or at least 2 observations.")
    groups = {}
    invalid_rows = []
    for index, point in enumerate(request.observations, start=1):
        day, value = _date(point.date), _number(point.value)
        if day is None or value is None:
            invalid_rows.append(index)
            continue
        groups.setdefault(day, []).append(value)
    if invalid_rows and request.missing_policy == "error":
        raise ForecastValidationError(
            f"{len(invalid_rows)} rows have invalid/missing dates or target values "
            f"(data rows {', '.join(map(str, invalid_rows[:5]))}). Dates must be YYYY-MM-DD "
            "and targets finite normalized numbers. Review Data or explicitly choose Skip invalid rows."
        )
    duplicates = sum(len(values) - 1 for values in groups.values())
    if duplicates and request.duplicate_policy == "error":
        raise ForecastValidationError(
            f"{duplicates} extra rows share a date. Select a single series first, or explicitly "
            "choose Sum / Mean per date if combining those records matches your target."
        )
    dates = sorted(groups)
    values = [math.fsum(groups[day]) if request.duplicate_policy == "sum" else fmean(groups[day]) for day in dates]
    minimum_train = max(20, 2 * request.season_length)
    required = max(40, minimum_train + 3 * request.horizon)
    if len(values) < required:
        raise ForecastValidationError(
            f"Need at least {required} usable distinct dates for horizon {request.horizon} "
            f"and season length {request.season_length}; found {len(values)}. "
            "Use a shorter horizon/season or upload more history."
        )
    warnings = []
    if invalid_rows:
        warnings.append(f"Skipped {len(invalid_rows)} invalid rows by your choice; no values were filled in.")
    if duplicates:
        warnings.append(f"Combined {duplicates} extra rows using {request.duplicate_policy} per date.")
    frequency = _frequency(dates, request.frequency)
    if frequency == "observations":
        warnings.append("Horizon counts observations, not calendar days. Gaps are not filled; future trading/event dates are not inferred.")
    if max(values) == min(values):
        warnings.append("The target is constant. A flat forecast is expected.")
    warnings.append("Point forecasts only; prediction intervals are not estimated in this version.")
    return dates, values, frequency, warnings, {
        "input_rows": len(request.observations), "usable_dates": len(values),
        "dropped_rows": len(invalid_rows), "duplicate_rows": duplicates,
        "missing_policy": request.missing_policy, "duplicate_policy": request.duplicate_policy,
        "minimum_required": required,
    }


def _frequency(dates, requested):
    daily = all((right - left).days == 1 for left, right in zip(dates, dates[1:]))
    weekly = all((right - left).days == 7 for left, right in zip(dates, dates[1:]))
    month_end = all(day.day == calendar.monthrange(day.year, day.month)[1] for day in dates)
    same_day = len({day.day for day in dates}) == 1
    monthly = (month_end or same_day) and all(
        right.year * 12 + right.month - left.year * 12 - left.month == 1
        for left, right in zip(dates, dates[1:])
    )
    regular = {"daily": daily, "weekly": weekly, "monthly": monthly}
    if requested == "auto":
        return next((name for name, matches in regular.items() if matches), "observations")
    if requested != "observations" and not regular[requested]:
        raise ForecastValidationError(
            f"Dates do not form a complete {requested} sequence. Review gaps/frequency in Data "
            "or choose Observation steps. Missing periods are never silently filled."
        )
    return requested


def _holt_state(values, alpha, beta, phi):
    level, trend = values[0], values[1] - values[0]
    errors = []
    for value in values[1:]:
        estimate = level + phi * trend
        errors.append((value - estimate) ** 2)
        previous_level = level
        level = alpha * value + (1 - alpha) * estimate
        trend = beta * (level - previous_level) + (1 - beta) * phi * trend
    return level, trend, fmean(errors)


def predict(name, values, horizon, season_length=0):
    """Fit on the supplied prefix only; return a fixed-origin multi-step forecast."""
    if name == "naive":
        return [values[-1]] * horizon, {}
    if name == "moving_average":
        window = min(7, len(values))
        return [fmean(values[-window:])] * horizon, {"window": window}
    if name == "seasonal_naive":
        return [values[-season_length + step % season_length] for step in range(horizon)], {"season_length": season_length}
    if name != "holt_damped":
        raise ValueError("Unknown forecasting method")
    # Small deterministic grid: smoothing parameters fit to training residuals,
    # never to validation/test observations. Initial level/trend use first 2 rows.
    best = None
    for alpha in (0.2, 0.5, 0.8):
        for beta in (0.05, 0.2):
            for phi in (0.9, 0.98):
                level, trend, loss = _holt_state(values, alpha, beta, phi)
                if best is None or loss < best[0]:
                    best = (loss, level, trend, alpha, beta, phi)
    _, level, trend, alpha, beta, phi = best
    predictions = [level + trend * sum(phi ** i for i in range(1, step + 1)) for step in range(1, horizon + 1)]
    return predictions, {"alpha": alpha, "beta": beta, "phi": phi, "fit": "training residual grid search"}


def metrics(actual, predicted):
    errors = [a - p for a, p in zip(actual, predicted)]
    return {"mae": fmean(abs(error) for error in errors), "rmse": math.sqrt(fmean(error ** 2 for error in errors))}


def run_forecast(request: ForecastRequest):
    dates, values, frequency, warnings, quality = _prepare(request)
    horizon = request.horizon
    train_end = len(values) - 3 * horizon
    test_start = len(values) - horizon
    models = ["naive", "moving_average", "holt_damped"]
    if request.season_length:
        models.append("seasonal_naive")
    comparison = []
    for name in models:
        actual, predicted, folds = [], [], []
        for origin in (train_end, train_end + horizon):
            forecast, _ = predict(name, values[:origin], horizon, request.season_length)
            actual.extend(values[origin:origin + horizon])
            predicted.extend(forecast)
            folds.append({"train_start": dates[0].isoformat(), "train_end": dates[origin - 1].isoformat(),
                          "validation_start": dates[origin].isoformat(), "validation_end": dates[origin + horizon - 1].isoformat(),
                          **metrics(values[origin:origin + horizon], forecast)})
        comparison.append({"model": name, "validation": metrics(actual, predicted), "folds": folds})
    # Stable ties favor the simplest baseline, Naive.
    selected = min(comparison, key=lambda item: item["validation"]["mae"])["model"]
    test_predictions, _ = predict(selected, values[:test_start], horizon, request.season_length)
    naive_test, _ = predict("naive", values[:test_start], horizon)
    test_metrics = metrics(values[test_start:], test_predictions)
    naive_metrics = metrics(values[test_start:], naive_test)
    if test_metrics["mae"] >= naive_metrics["mae"] and selected != "naive":
        warnings.append("The selected model did not beat Naive on the held-out test. Selection still uses validation only.")
    future, parameters = predict(selected, values, horizon, request.season_length)
    month_end = all(day.day == calendar.monthrange(day.year, day.month)[1] for day in dates)
    forecast_points = []
    try:
        for step, value in enumerate(future, start=1):
            next_date = None
            if frequency in ("daily", "weekly"):
                next_date = dates[-1] + timedelta(days=step * (7 if frequency == "weekly" else 1))
            elif frequency == "monthly":
                next_date = _month_after(dates[-1], step, month_end)
            forecast_points.append({"step": step, "date": next_date.isoformat() if next_date else None, "predicted": value})
    except (OverflowError, ValueError) as error:
        raise ForecastValidationError("Future dates fall outside the supported calendar range.") from error
    return {
        "time_column": request.time_column, "target_column": request.target_column,
        "horizon": horizon, "frequency": frequency, "selected_model": selected,
        "model_parameters": parameters, "comparison": comparison,
        "test_metrics": test_metrics, "naive_test_metrics": naive_metrics,
        "splits": {"initial_train_start": dates[0].isoformat(), "initial_train_end": dates[train_end - 1].isoformat(),
                   "initial_train_count": train_end, "validation_start": dates[train_end].isoformat(),
                   "validation_end": dates[test_start - 1].isoformat(), "validation_folds": 2,
                   "test_start": dates[test_start].isoformat(), "test_end": dates[-1].isoformat(),
                   "test_count": horizon, "refit_count": len(values)},
        "quality": quality, "warnings": warnings,
        "history": [{"date": day.isoformat(), "actual": value} for day, value in zip(dates[-200:], values[-200:])],
        "backtest": [{"date": day.isoformat(), "actual": actual, "predicted": predicted, "naive": naive}
                     for day, actual, predicted, naive in zip(dates[test_start:], values[test_start:], test_predictions, naive_test)],
        "forecast": forecast_points,
    }
