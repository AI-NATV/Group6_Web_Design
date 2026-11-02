"""Alembic environment for the Revenue Analytics SQLModel schema."""

from __future__ import annotations

from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlmodel import SQLModel

from backend.config import DATABASE_URL
from backend import db_models  # noqa: F401  -- register SQLModel table metadata


config = context.config
config.set_main_option("sqlalchemy.url", DATABASE_URL.replace("%", "%%"))
database_url = config.get_main_option("sqlalchemy.url")

parsed_url = make_url(database_url)
if parsed_url.drivername.startswith("sqlite") and parsed_url.database not in (None, "", ":memory:"):
    Path(parsed_url.database).parent.mkdir(parents=True, exist_ok=True)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(database_url)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
