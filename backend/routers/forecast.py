"""Owner-checked feature review, forecasts on saved datasets, and the saved forecast runs."""

from fastapi import APIRouter, HTTPException, status
from sqlmodel import select

from backend.database import SessionDep
from backend.db_models import ForecastRun, ForecastRunPublic, ForecastRunSummary, Role, User
from backend.models import AssistedForecastRequest, AssistedForecastResponse, DatasetForecastTask
from backend.routers.datasets import get_owned_dataset
from backend.security import CurrentUser
from backend.services.feature_service import assisted_forecast, recommend_features
from backend.services.forecast_service import ForecastValidationError

router = APIRouter(prefix="/datasets", tags=["forecast"])
runs_router = APIRouter(prefix="/forecast-runs", tags=["forecast"])


@router.post("/{dataset_id}/feature-review", summary="Review numeric features using initial training history only")
def feature_review(dataset_id: int, payload: DatasetForecastTask, session: SessionDep, user: CurrentUser):
    dataset = get_owned_dataset(session, dataset_id, user)
    try:
        return recommend_features(dataset, payload)
    except ForecastValidationError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/{dataset_id}/forecast", response_model=AssistedForecastResponse,
             summary="Compare confirmed historical features against forecasting baselines and save the run")
def forecast_dataset(dataset_id: int, payload: AssistedForecastRequest, session: SessionDep, user: CurrentUser):
    dataset = get_owned_dataset(session, dataset_id, user)
    try:
        result = assisted_forecast(dataset, payload)
    except ForecastValidationError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    data = result if isinstance(result, dict) else result.model_dump()
    # Keep the run for the dataset owner; the long history series is not stored again.
    stored = {key: value for key, value in data.items() if key != "history"}
    run = ForecastRun(
        owner_id=dataset.owner_id,
        dataset_id=dataset.id,
        time_column=payload.time_column,
        target_column=payload.target_column,
        horizon=payload.horizon,
        selected_model=data["selected_model"],
        features=list(payload.selected_features),
        result=stored,
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    data["run_id"] = run.id
    return data


@router.get("/{dataset_id}/forecast-runs", response_model=list[ForecastRunSummary],
            summary="List the saved forecast runs of a dataset, newest first")
def list_forecast_runs(dataset_id: int, session: SessionDep, user: CurrentUser) -> list[ForecastRun]:
    get_owned_dataset(session, dataset_id, user)
    query = (select(ForecastRun).where(ForecastRun.dataset_id == dataset_id)
             .order_by(ForecastRun.created_at.desc(), ForecastRun.id.desc()).limit(50))
    return session.exec(query).all()


def _owned_run(session, run_id: int, user: User) -> ForecastRun:
    run = session.get(ForecastRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Forecast run not found")
    if run.owner_id != user.id and user.role != Role.admin:
        raise HTTPException(status_code=403, detail="You can only access your own forecast runs")
    return run


@runs_router.get("/{run_id}", response_model=ForecastRunPublic, summary="Read one saved forecast run")
def read_forecast_run(run_id: int, session: SessionDep, user: CurrentUser) -> ForecastRun:
    return _owned_run(session, run_id, user)


@runs_router.delete("/{run_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete one saved forecast run")
def delete_forecast_run(run_id: int, session: SessionDep, user: CurrentUser) -> None:
    session.delete(_owned_run(session, run_id, user))
    session.commit()
