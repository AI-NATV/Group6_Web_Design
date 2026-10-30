"""Load sample CSV files into the database for an existing user:

    python -m backend.seed --owner USERNAME [file.csv ...]

Without files it loads sample_sales.csv from the project root. A file the
owner already has (same name) is skipped, so the script can be run more than once.
Create the user first by registering in the app or with python -m backend.create_admin.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlmodel import Session, select

from backend.database import create_db_and_tables, engine
from backend.db_models import Dataset, User
from backend.services.csv_service import parse_csv

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def seed(owner: str, paths: list[Path]) -> None:
    create_db_and_tables()
    with Session(engine) as session:
        user = session.exec(select(User).where(User.username == owner.strip().lower())).first()
        if user is None:
            sys.exit(f"User {owner!r} does not exist. Register in the app or run python -m backend.create_admin first.")
        for path in paths:
            already = select(Dataset).where(Dataset.owner_id == user.id, Dataset.filename == path.name)
            if session.exec(already).first():
                print(f"skip  {path.name} (already stored for {user.username})")
                continue
            columns, records, raw_records, profiles = parse_csv(path.read_bytes())
            session.add(Dataset(
                owner_id=user.id, filename=path.name, rows=len(records), columns=columns,
                data=records, raw_data=raw_records, profiles=profiles,
            ))
            print(f"added {path.name} ({len(records)} rows) for {user.username}")
        session.commit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load CSV files into the database for a user.")
    parser.add_argument("--owner", required=True, help="username that will own the datasets")
    parser.add_argument("files", nargs="*", type=Path, help="CSV files (default: sample_sales.csv)")
    arguments = parser.parse_args()
    seed(arguments.owner, arguments.files or [PROJECT_ROOT / "sample_sales.csv"])
