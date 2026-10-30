"""Database tables and the API schemas derived from them.

SQLModel combines SQLAlchemy (tables, sessions, queries) with Pydantic
(validation, JSON). ``table=True`` classes are real tables; the others are
request/response schemas, so the API never exposes more than it intends to.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import field_validator, model_validator
from sqlalchemy import JSON, Column
from sqlmodel import Field, Relationship, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ChartType(str, Enum):
    bar = "bar"
    line = "line"
    pie = "pie"
    scatter = "scatter"


class Role(str, Enum):
    user = "user"
    admin = "admin"


class Aggregation(str, Enum):
    sum = "sum"
    average = "average"
    count = "count"
    min = "min"
    max = "max"


# ---------- Tables ----------

class UserBase(SQLModel):
    username: str = Field(index=True, unique=True, min_length=3, max_length=30)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        # Case-insensitive usernames: "Alice" and "alice" are the same account.
        value = value.strip().lower()
        if not all(character.isascii() and (character.isalnum() or character in "._-") for character in value):
            raise ValueError("use only letters, digits, '.', '_' or '-'")
        return value


class User(UserBase, table=True):
    """An account. Only the bcrypt hash of the password is stored."""

    id: int | None = Field(default=None, primary_key=True)
    hashed_password: str
    role: Role = Role.user
    created_at: datetime = Field(default_factory=utc_now)

    datasets: list["Dataset"] = Relationship(back_populates="owner", sa_relationship_kwargs={"cascade": "all, delete-orphan"})


class Dataset(SQLModel, table=True):
    """One uploaded CSV: parsed rows, the user's semantic review and its visuals."""

    id: int | None = Field(default=None, primary_key=True)
    owner_id: int = Field(foreign_key="user.id", index=True, ondelete="CASCADE")
    filename: str = Field(max_length=255)
    rows: int = Field(ge=0)
    columns: list[str] = Field(sa_column=Column(JSON, nullable=False))
    # ``data`` holds normalized values used for analysis; ``raw_data`` keeps the
    # file's original text so the Data workspace can show exactly what was uploaded.
    data: list[dict[str, Any]] = Field(sa_column=Column(JSON, nullable=False))
    raw_data: list[dict[str, Any]] = Field(sa_column=Column(JSON, nullable=False))
    profiles: dict[str, dict[str, Any]] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    semantic_model: dict[str, dict[str, Any]] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    owner: User | None = Relationship(back_populates="datasets")
    visuals: list["Visual"] = Relationship(
        back_populates="dataset",
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "order_by": "Visual.position"},
    )


class Visual(SQLModel, table=True):
    """A saved dashboard chart. Many visuals belong to one dataset (FK on the "many" side)."""

    id: int | None = Field(default=None, primary_key=True)
    dataset_id: int = Field(foreign_key="dataset.id", index=True, ondelete="CASCADE")
    chart_type: ChartType
    fields: dict[str, str] = Field(sa_column=Column(JSON, nullable=False))
    aggregation: Aggregation = Aggregation.sum
    position: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=utc_now)

    dataset: Dataset | None = Relationship(back_populates="visuals")


def as_utc(value: datetime) -> datetime:
    # SQLite stores datetimes without a time zone; every stored value is UTC.
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


# ---------- Account schemas ----------

class UserCreate(UserBase):
    """Registration body: no role field, so nobody can make themselves an admin."""

    password: str = Field(min_length=8)

    @field_validator("password")
    @classmethod
    def fits_bcrypt(cls, value: str) -> str:
        # bcrypt ignores everything after 72 bytes; Vietnamese letters can take 3 bytes each.
        if len(value.encode("utf-8")) > 72:
            raise ValueError("must be at most 72 bytes")
        return value


class UserPublic(UserBase):
    """What the API returns about an account: never the password or its hash."""

    id: int
    role: Role
    created_at: datetime

    _utc = field_validator("created_at")(as_utc)


class Token(SQLModel):
    access_token: str
    token_type: str = "bearer"


# ---------- Dataset schemas ----------

class DatasetSummary(SQLModel):
    """List view: everything except the (potentially large) row data."""

    id: int
    owner_id: int
    filename: str
    rows: int
    columns: list[str]
    created_at: datetime
    updated_at: datetime

    _utc = field_validator("created_at", "updated_at")(as_utc)


class DatasetPublic(DatasetSummary):
    data: list[dict[str, Any]]
    raw_data: list[dict[str, Any]]
    profiles: dict[str, dict[str, Any]]
    semantic_model: dict[str, dict[str, Any]]


class DatasetUpdate(SQLModel):
    """PATCH body: send only what changed. Fields are optional but never null."""

    semantic_model: dict[str, dict[str, Any]] | None = None
    data: list[dict[str, Any]] | None = None

    @field_validator("semantic_model", "data")
    @classmethod
    def not_null(cls, value):
        # Only runs when the client sends the field.
        if value is None:
            raise ValueError("cannot be null")
        return value


# ---------- Visual schemas ----------

REQUIRED_FIELDS = {
    ChartType.scatter: {"x", "y"},
    ChartType.bar: {"dimension", "measure"},
    ChartType.line: {"dimension", "measure"},
    ChartType.pie: {"dimension", "measure"},
}


class VisualCreate(SQLModel):
    chart_type: ChartType
    fields: dict[str, str] = Field(schema_extra={"examples": [{"dimension": "region", "measure": "revenue"}]})
    aggregation: Aggregation = Aggregation.sum

    @model_validator(mode="after")
    def fields_match_chart_type(self):
        expected = REQUIRED_FIELDS[self.chart_type]
        if set(self.fields) != expected:
            raise ValueError(f"{self.chart_type.value} charts need exactly these fields: {', '.join(sorted(expected))}")
        if any(not column.strip() for column in self.fields.values()):
            raise ValueError("field names cannot be blank")
        return self


class VisualPublic(VisualCreate):
    id: int
    dataset_id: int
    position: int
    created_at: datetime

    _utc = field_validator("created_at")(as_utc)


class VisualUpdate(SQLModel):
    """Move a visual to a new zero-based position on its dashboard."""

    position: int = Field(ge=0)
