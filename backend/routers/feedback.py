"""Public feedback submission and administrator-only review."""

from fastapi import APIRouter, Query, status
from sqlmodel import select

from backend.database import SessionDep
from backend.db_models import Feedback, FeedbackCreate, FeedbackPublic, FeedbackReceipt
from backend.security import AdminUser


router = APIRouter(tags=["feedback"])


@router.post(
    "/feedback",
    response_model=FeedbackReceipt,
    status_code=status.HTTP_201_CREATED,
    summary="Submit feedback from the public landing page",
)
def submit_feedback(payload: FeedbackCreate, session: SessionDep) -> Feedback:
    feedback = Feedback.model_validate(payload.model_dump())
    session.add(feedback)
    session.commit()
    session.refresh(feedback)
    return feedback


@router.get(
    "/admin/feedback",
    response_model=list[FeedbackPublic],
    summary="Review submitted feedback (admins only)",
)
def list_feedback(
    session: SessionDep,
    _admin: AdminUser,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
) -> list[Feedback]:
    query = select(Feedback).order_by(Feedback.created_at.desc(), Feedback.id.desc()).offset(offset).limit(limit)
    return session.exec(query).all()
