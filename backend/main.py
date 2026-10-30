"""FastAPI application for the Revenue Analytics dashboard."""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.config import ALLOWED_ORIGINS
from backend.database import create_db_and_tables
from backend.models import ForecastRequest, ForecastResponse, HealthResponse
from backend.routers import datasets, visuals
from backend.services.forecast_service import ForecastValidationError, run_forecast


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("revenue_analytics")
FRONTEND_DIRECTORY = Path(__file__).resolve().parent.parent / "frontend"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    create_db_and_tables()
    yield


app = FastAPI(
    title="Revenue Analytics API",
    version="0.5.0",
    description="Saved CSV datasets and dashboards, plus univariate forecasts with chronological validation and held-out testing.",
    lifespan=lifespan,
    openapi_tags=[
        {"name": "datasets", "description": "Upload CSV files and manage the saved datasets."},
        {"name": "visuals", "description": "Charts saved on a dataset's dashboard."},
        {"name": "forecast", "description": "Stateless forecasts computed from the posted observations."},
        {"name": "health", "description": "Service status."},
    ],
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "X-Request-ID"],
)


@app.middleware("http")
async def request_logging(request: Request, call_next):
    """Attach a request id and log concise request timing without request data."""

    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    started_at = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - started_at) * 1000
    response.headers["X-Request-ID"] = request_id
    logger.info("%s %s -> %s in %.1fms", request.method, request.url.path, response.status_code, elapsed_ms)
    return response


@app.get("/", response_model=HealthResponse, tags=["health"], summary="API status")
def home() -> HealthResponse:
    return HealthResponse()


@app.get("/health", response_model=HealthResponse, tags=["health"], summary="Health check")
def health_check() -> HealthResponse:
    return HealthResponse()


@app.post(
    "/forecast",
    response_model=ForecastResponse,
    tags=["forecast"],
    summary="Compare forecasts on validation windows, evaluate on held-out data, and forecast ahead",
)
def forecast(payload: ForecastRequest) -> ForecastResponse:
    try:
        return ForecastResponse(**run_forecast(payload))
    except ForecastValidationError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


app.include_router(datasets.router, prefix="/api/v1")
app.include_router(visuals.router, prefix="/api/v1")

# Same-origin local development option: http://127.0.0.1:8000/app/
app.mount("/app", StaticFiles(directory=str(FRONTEND_DIRECTORY), html=True), name="frontend")
