"""Visuals: charts saved on a dataset's dashboard, kept in a user-defined order."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlmodel import Session

from backend.database import SessionDep
from backend.db_models import User, Visual, VisualCreate, VisualPublic, VisualUpdate
from backend.routers.datasets import NOT_FOUND as DATASET_NOT_FOUND
from backend.routers.datasets import get_owned_dataset
from backend.security import AUTH_ERRORS, CurrentUser, check_owner


router = APIRouter(tags=["visuals"], responses={401: AUTH_ERRORS[401]})
VISUAL_NOT_FOUND = {404: {"description": "Visual not found"}, 403: AUTH_ERRORS[403]}


def get_owned_visual(session: Session, visual_id: int, user: User) -> Visual:
    """A visual belongs to whoever owns its dataset."""

    visual = session.get(Visual, visual_id)
    if not visual:
        raise HTTPException(status_code=404, detail="Visual not found")
    check_owner(visual.dataset, user)
    return visual


def renumber(visuals: list[Visual]) -> None:
    for position, visual in enumerate(visuals):
        visual.position = position


@router.get(
    "/datasets/{dataset_id}/visuals",
    response_model=list[VisualPublic],
    summary="List a dataset's saved visuals in dashboard order",
    responses=DATASET_NOT_FOUND,
)
def list_visuals(dataset_id: int, session: SessionDep, user: CurrentUser) -> list[Visual]:
    return get_owned_dataset(session, dataset_id, user).visuals


@router.post(
    "/datasets/{dataset_id}/visuals",
    response_model=VisualPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Save a visual at the end of a dataset's dashboard",
    responses={**DATASET_NOT_FOUND, 400: {"description": "Field is not a column of this dataset"}},
)
def create_visual(dataset_id: int, visual_in: VisualCreate, session: SessionDep, user: CurrentUser) -> Visual:
    dataset = get_owned_dataset(session, dataset_id, user)
    missing = [column for column in visual_in.fields.values() if column not in dataset.columns]
    if missing:
        raise HTTPException(status_code=400, detail=f"Column {missing[0]!r} does not exist in this dataset")
    visual = Visual.model_validate(visual_in, update={"dataset_id": dataset.id, "position": len(dataset.visuals)})
    session.add(visual)
    session.commit()
    session.refresh(visual)
    return visual


@router.patch(
    "/visuals/{visual_id}",
    response_model=VisualPublic,
    summary="Move a visual to another position on its dashboard",
    responses=VISUAL_NOT_FOUND,
)
def move_visual(visual_id: int, visual_in: VisualUpdate, session: SessionDep, user: CurrentUser) -> Visual:
    visual = get_owned_visual(session, visual_id, user)
    siblings = [item for item in visual.dataset.visuals if item.id != visual.id]
    siblings.insert(min(visual_in.position, len(siblings)), visual)
    renumber(siblings)
    session.add_all(siblings)
    session.commit()
    session.refresh(visual)
    return visual


@router.delete(
    "/visuals/{visual_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a visual from its dashboard",
    responses=VISUAL_NOT_FOUND,
)
def delete_visual(visual_id: int, session: SessionDep, user: CurrentUser) -> None:
    visual = get_owned_visual(session, visual_id, user)
    dataset = visual.dataset
    session.delete(visual)
    renumber([item for item in dataset.visuals if item.id != visual.id])
    session.commit()
