"""Datasets: upload a CSV, then list, read, update and delete the saved copy."""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import defer
from sqlmodel import Session, select

from backend.config import MAX_FILE_SIZE
from backend.database import SessionDep
from backend.db_models import Dataset, DatasetPublic, DatasetSummary, DatasetUpdate, utc_now
from backend.services.csv_service import CsvValidationError, parse_csv


router = APIRouter(prefix="/datasets", tags=["datasets"])
NOT_FOUND = {404: {"description": "Dataset not found"}}


def get_dataset_or_404(session: Session, dataset_id: int) -> Dataset:
    dataset = session.get(Dataset, dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return dataset


@router.post(
    "",
    response_model=DatasetPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a CSV and save it as a dataset",
    responses={400: {"description": "Not a valid, non-empty CSV"}, 413: {"description": "File too large"}},
)
def create_dataset(session: SessionDep, file: UploadFile = File(...)) -> Dataset:
    """Validate and parse a CSV file, store it, and return the saved dataset."""

    filename = file.filename or ""
    if not filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported.")

    # Read one byte past the limit so an oversized upload is rejected without loading all of it.
    contents = file.file.read(MAX_FILE_SIZE + 1)
    if not contents:
        raise HTTPException(status_code=400, detail="CSV file is empty.")
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="CSV file is too large (maximum 10 MB).")

    try:
        columns, records, raw_records, profiles = parse_csv(contents)
    except CsvValidationError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    dataset = Dataset(
        filename=filename,
        rows=len(records),
        columns=columns,
        data=records,
        raw_data=raw_records,
        profiles=profiles,
    )
    session.add(dataset)
    session.commit()
    session.refresh(dataset)
    return dataset


@router.get("", response_model=list[DatasetSummary], summary="List saved datasets, newest first")
def list_datasets(
    session: SessionDep,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[Dataset]:
    # Skip loading the row data: the list only needs names, sizes and dates.
    query = (
        select(Dataset)
        .options(defer(Dataset.data), defer(Dataset.raw_data), defer(Dataset.profiles), defer(Dataset.semantic_model))
        .order_by(Dataset.created_at.desc(), Dataset.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return session.exec(query).all()


@router.get("/{dataset_id}", response_model=DatasetPublic, summary="Get one dataset", responses=NOT_FOUND)
def read_dataset(dataset_id: int, session: SessionDep) -> Dataset:
    return get_dataset_or_404(session, dataset_id)


@router.patch(
    "/{dataset_id}",
    response_model=DatasetPublic,
    summary="Update the semantic review or replace cleaned rows",
    responses={**NOT_FOUND, 400: {"description": "Unknown column"}},
)
def update_dataset(dataset_id: int, dataset_in: DatasetUpdate, session: SessionDep) -> Dataset:
    dataset = get_dataset_or_404(session, dataset_id)
    changes = dataset_in.model_dump(exclude_unset=True)
    known = set(dataset.columns)

    if "semantic_model" in changes:
        unknown = set(changes["semantic_model"]) - known
        if unknown:
            raise HTTPException(status_code=400, detail=f"Unknown column in semantic model: {sorted(unknown)[0]}")
        dataset.semantic_model = changes["semantic_model"]

    if "data" in changes:
        for index, row in enumerate(changes["data"], start=1):
            unknown = set(row) - known
            if unknown:
                raise HTTPException(status_code=400, detail=f"Row {index} has an unknown column: {sorted(unknown)[0]}")
        dataset.data = changes["data"]
        dataset.rows = len(changes["data"])

    dataset.updated_at = utc_now()
    session.add(dataset)
    session.commit()
    session.refresh(dataset)
    return dataset


@router.delete(
    "/{dataset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a dataset and its saved visuals",
    responses=NOT_FOUND,
)
def delete_dataset(dataset_id: int, session: SessionDep) -> None:
    session.delete(get_dataset_or_404(session, dataset_id))
    session.commit()
