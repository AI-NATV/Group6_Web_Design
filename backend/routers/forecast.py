"""Owner-checked feature review and forecasts on saved, normalized datasets."""

from fastapi import APIRouter, HTTPException

from backend.database import SessionDep
from backend.models import AssistedForecastRequest, AssistedForecastResponse, DatasetForecastTask
from backend.routers.datasets import get_owned_dataset
from backend.security import CurrentUser
from backend.services.feature_service import assisted_forecast, recommend_features
from backend.services.forecast_service import ForecastValidationError

router = APIRouter(prefix="/datasets", tags=["forecast"])


@router.post("/{dataset_id}/feature-review", summary="Review numeric features using initial training history only")
def feature_review(dataset_id: int, payload: DatasetForecastTask, session: SessionDep, user: CurrentUser):
    dataset = get_owned_dataset(session, dataset_id, user)
    try:
        return recommend_features(dataset, payload)
    except ForecastValidationError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/{dataset_id}/forecast", response_model=AssistedForecastResponse,
             summary="Compare confirmed historical features against forecasting baselines")
def forecast_dataset(dataset_id: int, payload: AssistedForecastRequest, session: SessionDep, user: CurrentUser):
    dataset = get_owned_dataset(session, dataset_id, user)
    try:
        return assisted_forecast(dataset, payload)
    except ForecastValidationError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
