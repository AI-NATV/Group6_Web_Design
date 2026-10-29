"""Pydantic response contracts exposed by the FastAPI application."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "revenue-analytics-api"


class DatasetUploadResponse(BaseModel):
    filename: str
    rows: int = Field(ge=0)
    columns: list[str]
    # ``data`` is the analysis-ready representation. ``raw_data`` is retained
    # so the Data workspace can show users exactly what was in their file.
    data: list[dict[str, Any]]
    raw_data: list[dict[str, Any]]
    profiles: dict[str, dict[str, Any]]


class ForecastObservation(BaseModel):
    date: Any = None
    value: Any = None


class ForecastRequest(BaseModel):
    time_column: str = Field(min_length=1, max_length=200)
    target_column: str = Field(min_length=1, max_length=200)
    observations: list[ForecastObservation] = Field(min_length=1, max_length=50000)
    horizon: int = Field(default=7, ge=1, le=90)
    frequency: Literal["auto", "daily", "weekly", "monthly", "observations"] = "auto"
    missing_policy: Literal["error", "drop"] = "error"
    duplicate_policy: Literal["error", "sum", "mean"] = "error"
    season_length: int = Field(default=0, ge=0, le=365)


class ForecastMetrics(BaseModel):
    mae: float
    rmse: float


class ForecastPoint(BaseModel):
    step: int
    date: str | None
    predicted: float


class BacktestPoint(BaseModel):
    date: str
    actual: float
    predicted: float
    naive: float


class ForecastResponse(BaseModel):
    time_column: str
    target_column: str
    horizon: int
    frequency: str
    selected_model: str
    model_parameters: dict[str, Any]
    comparison: list[dict[str, Any]]
    test_metrics: ForecastMetrics
    naive_test_metrics: ForecastMetrics
    splits: dict[str, Any]
    quality: dict[str, Any]
    warnings: list[str]
    history: list[dict[str, Any]]
    backtest: list[BacktestPoint]
    forecast: list[ForecastPoint]
