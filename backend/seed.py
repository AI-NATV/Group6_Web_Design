"""Load sample CSV files into the database: python -m backend.seed [file.csv ...]

Without arguments it loads sample_sales.csv from the project root. A file whose
name is already stored is skipped, so the script can be run more than once.
"""

from __future__ import annotations

import sys
from pathlib import Path

from sqlmodel import Session, select

from backend.database import create_db_and_tables, engine
from backend.db_models import Dataset
from backend.services.csv_service import parse_csv

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def seed(paths: list[Path]) -> None:
    create_db_and_tables()
    with Session(engine) as session:
        for path in paths:
            if session.exec(select(Dataset).where(Dataset.filename == path.name)).first():
                print(f"skip  {path.name} (already stored)")
                continue
            columns, records, raw_records, profiles = parse_csv(path.read_bytes())
            session.add(Dataset(
                filename=path.name, rows=len(records), columns=columns,
                data=records, raw_data=raw_records, profiles=profiles,
            ))
            print(f"added {path.name} ({len(records)} rows)")
        session.commit()


if __name__ == "__main__":
    seed([Path(argument) for argument in sys.argv[1:]] or [PROJECT_ROOT / "sample_sales.csv"])
