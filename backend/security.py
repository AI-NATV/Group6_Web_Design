"""Password hashing, JWT access tokens and the dependencies that protect routes.

Authentication ("who are you?") fails with 401; authorization ("may you do
this?") fails with 403.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pwdlib import PasswordHash
from pwdlib.hashers.bcrypt import BcryptHasher

from backend import config
from backend.database import SessionDep
from backend.db_models import Dataset, Role, User

ALGORITHM = "HS256"

# bcrypt: one-way, salted (a new random salt per hash, stored inside it) and deliberately slow.
password_hash = PasswordHash((BcryptHasher(),))
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/token")


def hash_password(plain: str) -> str:
    return password_hash.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return password_hash.verify(plain, hashed)


# Checked against when the username does not exist, so a login attempt takes
# about as long whether or not the account exists.
_DUMMY_HASH = hash_password("not-a-real-password")


def authenticate(user: User | None, password: str) -> bool:
    if user is None:
        verify_password(password, _DUMMY_HASH)
        return False
    return verify_password(password, user.hashed_password)


def require_secret_key() -> str:
    """Return SECRET_KEY, refusing to run without one (called at startup)."""

    if not config.SECRET_KEY:
        raise RuntimeError(
            "SECRET_KEY is not set. Generate one with "
            "python -c \"import secrets; print(secrets.token_hex(32))\" "
            "and set it as an environment variable before starting the server."
        )
    return config.SECRET_KEY


def create_access_token(subject: str, expires_delta: timedelta | None = None) -> str:
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=config.ACCESS_TOKEN_EXPIRE_MINUTES))
    # The payload is only Base64-encoded, not encrypted: never put secrets in it.
    return jwt.encode({"sub": subject, "exp": expire}, require_secret_key(), algorithm=ALGORITHM)


CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(token: Annotated[str, Depends(oauth2_scheme)], session: SessionDep) -> User:
    """Turn the Bearer token into a User, or answer 401 before the endpoint runs."""

    try:
        payload = jwt.decode(token, require_secret_key(), algorithms=[ALGORITHM], options={"require": ["exp", "sub"]})
        user_id = int(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise CREDENTIALS_ERROR
    # Reload from the database: deleted users are locked out and the role comes from the DB, not the token.
    user = session.get(User, user_id)
    if user is None:
        raise CREDENTIALS_ERROR
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_admin(user: CurrentUser) -> User:
    if user.role != Role.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admins only")
    return user


AdminUser = Annotated[User, Depends(require_admin)]


def check_owner(dataset: Dataset, user: User) -> None:
    if dataset.owner_id != user.id and user.role != Role.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only access your own datasets")


AUTH_ERRORS = {
    401: {"description": "Not logged in, or the token is invalid or expired"},
    403: {"description": "The dataset belongs to another user"},
}
