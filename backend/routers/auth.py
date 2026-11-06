"""Accounts: register, log in for an access token, and read the current user."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from backend.database import SessionDep
from backend.db_models import AccountDelete, AvatarUpdate, Token, User, UserCreate, UserPublic, UserUpdate
from backend.security import CurrentUser, authenticate, create_access_token, hash_password, verify_password


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
    # Compare case-insensitively on both sides, so accounts stored before usernames were
    # normalized (for example "Tuan") can still sign in with any letter case.
    name = form.username.strip().lower()
    user = session.exec(select(User).where(func.lower(User.username) == name)).first()
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


@router.patch(
    "/me",
    response_model=UserPublic,
    summary="Update optional profile fields (display name, phone)",
    responses={401: {"description": "Not logged in"}, 422: {"description": "Invalid value"}},
)
def update_me(update: UserUpdate, session: SessionDep, user: CurrentUser) -> User:
    # Username and email are not editable here; only the optional profile fields are.
    changes = update.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(user, field, value)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@router.put(
    "/me/avatar",
    response_model=UserPublic,
    summary="Set the profile picture (PNG, JPEG or WebP data URL)",
    responses={401: {"description": "Not logged in"}, 422: {"description": "Not an image or too large"}},
)
def set_avatar(body: AvatarUpdate, session: SessionDep, user: CurrentUser) -> User:
    user.avatar = body.avatar
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@router.delete(
    "/me",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete your account and all its datasets (requires the current password)",
    responses={401: {"description": "Not logged in"}, 403: {"description": "Password is incorrect"}},
)
def delete_me(body: AccountDelete, session: SessionDep, user: CurrentUser) -> None:
    if not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=403, detail="Password is incorrect")
    # Datasets and visuals are removed by the ORM cascade configured on the models.
    session.delete(user)
    session.commit()
