"""Create an admin account, or promote an existing user: python -m backend.create_admin USERNAME

Admins are never created through the public API. The password is typed at a
hidden prompt so it does not end up in the shell history.
"""

from __future__ import annotations

import getpass
import sys

from pydantic import ValidationError
from sqlmodel import Session, select

from backend.database import create_db_and_tables, engine
from backend.db_models import Role, User, UserCreate
from backend.security import hash_password


def create_admin(username: str, password: str | None = None) -> User:
    create_db_and_tables()
    with Session(engine) as session:
        existing = session.exec(select(User).where(User.username == username.strip().lower())).first()
        if existing:
            existing.role = Role.admin
            user = existing
        else:
            if password is None:
                password = getpass.getpass("Password (8+ characters): ")
                if getpass.getpass("Repeat password: ") != password:
                    sys.exit("Passwords do not match.")
            try:
                account = UserCreate(username=username, password=password)
            except ValidationError as error:
                sys.exit(f"Invalid account: {error.errors()[0]['loc'][0]} {error.errors()[0]['msg']}")
            user = User(username=account.username, hashed_password=hash_password(account.password), role=Role.admin)
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: python -m backend.create_admin USERNAME")
    admin = create_admin(sys.argv[1])
    print(f"{admin.username} is now an admin (id {admin.id}).")
