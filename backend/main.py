"""FastAPI application for the Revenue Analytics dashboard."""

from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.config import ALLOWED_ORIGINS, MAX_FILE_SIZE
from backend.models import DatasetUploadResponse, ForecastRequest, ForecastResponse, HealthResponse
from backend.services.csv_service import CsvValidationError, parse_csv
from backend.services.forecast_service import ForecastValidationError, run_forecast


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("revenue_analytics")
FRONTEND_DIRECTORY = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(
    title="Revenue Analytics API",
    version="0.4.0",
    description="CSV analytics and univariate forecasts with chronological validation and held-out testing.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
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
    "/upload",
    response_model=DatasetUploadResponse,
    tags=["datasets"],
    summary="Upload and validate a CSV dataset",
)
async def upload_dataset(file: UploadFile = File(...)) -> DatasetUploadResponse:
    filename = file.filename or ""
    if not filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported.")

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="CSV file is empty.")
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="CSV file is too large (maximum 10 MB).")

    try:
        columns, records, raw_records, profiles = parse_csv(contents)
    except CsvValidationError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return DatasetUploadResponse(
        filename=filename,
        rows=len(records),
        columns=columns,
        data=records,
        raw_data=raw_records,
        profiles=profiles,
    )


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


# Same-origin local development option: http://127.0.0.1:8000/app/
app.mount("/app", StaticFiles(directory=str(FRONTEND_DIRECTORY), html=True), name="frontend")
