"""Database engine, table creation and the per-request session dependency."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Annotated

from fastapi import Depends
from sqlalchemy import event, inspect
from sqlmodel import Session, SQLModel, create_engine

from backend.config import DATABASE_URL


def make_engine(url: str, **options):
    """Create an engine; SQLite needs cross-thread access and explicit foreign keys."""

    is_sqlite = url.startswith("sqlite")
    engine = create_engine(url, connect_args={"check_same_thread": False} if is_sqlite else {}, **options)
    if is_sqlite:
        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(connection, _record):
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    return engine


engine = make_engine(DATABASE_URL)


def create_db_and_tables() -> None:
    """Create missing tables. Schema changes to existing tables need a migration (e.g. Alembic)."""

    # Importing the table models registers them on SQLModel.metadata.
    from backend import db_models  # noqa: F401

    if engine.url.drivername.startswith("sqlite") and engine.url.database not in (None, "", ":memory:"):
        Path(engine.url.database).parent.mkdir(parents=True, exist_ok=True)
    SQLModel.metadata.create_all(engine)
    check_schema()


def check_schema() -> None:
    """Stop with a clear message if an existing table lacks columns the code expects."""

    inspector = inspect(engine)
    for table in SQLModel.metadata.sorted_tables:
        existing = {column["name"] for column in inspector.get_columns(table.name)}
        missing = [column.name for column in table.columns if column.name not in existing]
        if missing:
            raise RuntimeError(
                f"Table {table.name!r} is missing column(s) {', '.join(missing)}: the database was created by an "
                "older version of the app. In development, delete data/app.db and restart; otherwise migrate it."
            )


def get_session() -> Iterator[Session]:
    """One session (unit of work) per request; closed after the response is sent."""

    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
