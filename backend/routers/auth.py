"""Accounts: register, log in for an access token, and read the current user."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from backend.database import SessionDep
from backend.db_models import Token, User, UserCreate, UserPublic
from backend.security import CurrentUser, authenticate, create_access_token, hash_password


router = APIRouter(tags=["auth"])


@router.post(
    "/register",
    response_model=UserPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account",
    responses={409: {"description": "Username already taken"}},
)
def register(user_in: UserCreate, session: SessionDep) -> User:
    # The role is never read from the request: admins are created with python -m backend.create_admin.
    user = User(username=user_in.username, hashed_password=hash_password(user_in.password))
    session.add(user)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail="Username already taken")
    session.refresh(user)
    return user


@router.post(
    "/token",
    response_model=Token,
    summary="Log in with a username and password (form fields) to get a Bearer token",
    responses={401: {"description": "Incorrect username or password"}},
)
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], session: SessionDep) -> Token:
    user = session.exec(select(User).where(User.username == form.username.strip().lower())).first()
    if not authenticate(user, form.password):
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password",  # same message for both cases
            headers={"WWW-Authenticate": "Bearer"},
        )
    return Token(access_token=create_access_token(str(user.id)))


@router.get("/me", response_model=UserPublic, summary="The logged-in user", responses={401: {"description": "Not logged in"}})
def read_me(user: CurrentUser) -> User:
    return user
