"""Safe, small-scope CSV parsing helpers."""

from __future__ import annotations

import io
import json
import re
from datetime import datetime
from typing import Any

import pandas as pd


class CsvValidationError(ValueError):
    """An expected validation error that is safe to show to an API caller."""


MISSING_MARKERS = {"", "-", "--", "n/a", "na", "null", "none", "nan"}
CURRENCY_SYMBOLS = "$€£¥₹₫"
ID_COLUMN_PATTERN = re.compile(r"(^|[_\s-])(id|code|key|zip|postal|phone|account)([_\s-]|$)", re.I)


def _clean_cell(value: Any) -> str | None:
    """Return a display-safe raw cell while giving common missing markers one meaning."""

    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    return None if text.lower() in MISSING_MARKERS else text


def _parse_number(value: str) -> tuple[float | None, str | None]:
    """Parse common international numeric notation without silently guessing text.

    The function accepts currency symbols, accounting negatives, percent signs,
    grouping spaces, and either comma or decimal-point notation. A value that
    cannot be interpreted returns ``None`` instead of a misleading zero.
    """

    text = value.strip().replace("\u00a0", " ")
    if not text:
        return None, None
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1].strip()
    currency = next((symbol for symbol in CURRENCY_SYMBOLS if symbol in text), None)
    is_percent = "%" in text
    text = re.sub(r"[$€£¥₹₫%\s]", "", text)
    if not re.fullmatch(r"[+-]?[0-9.,]+", text):
        return None, None

    # When both separators exist, the right-most one is conventionally the
    # decimal separator. A single decimal point stays decimal regardless of
    # precision; stripping it corrupted prices such as $123.456 by 1000x.
    # Comma-only notation retains the importer's existing grouping heuristic.
    if "," in text and "." in text:
        decimal = "," if text.rfind(",") > text.rfind(".") else "."
        grouping = "." if decimal == "," else ","
        text = text.replace(grouping, "").replace(decimal, ".")
    elif "," in text:
        tail = text.rsplit(",", 1)[1]
        text = text.replace(",", "") if len(tail) == 3 else text.replace(",", ".")

    try:
        number = float(text)
    except ValueError:
        return None, None
    if negative:
        number = -abs(number)
    if is_percent:
        number /= 100
        return number, "percentage"
    return number, "currency" if currency else "number"


DATE_FORMATS = (
    ("%Y-%m-%d", "ISO date"),
    ("%Y/%m/%d", "ISO date"),
    ("%Y-%m-%d %H:%M:%S", "ISO datetime"),
    ("%m/%d/%Y", "month/day/year"),
    ("%m-%d-%Y", "month-day-year"),
    ("%d/%m/%Y", "day/month/year"),
    ("%d-%m-%Y", "day-month-year"),
)


def _parse_date(value: str, fmt: str) -> str | None:
    try:
        return datetime.strptime(value, fmt).date().isoformat()
    except ValueError:
        return None


def _profile_column(column: str, values: list[str | None]) -> tuple[dict[str, Any], list[Any]]:
    non_missing = [value for value in values if value is not None]
    missing_count = len(values) - len(non_missing)
    parsed = [_parse_number(value) for value in non_missing]
    numeric_count = sum(number is not None for number, _ in parsed)
    numeric_ratio = numeric_count / len(non_missing) if non_missing else 0
    date_candidates = [
        (fmt, label, [_parse_date(value, fmt) for value in non_missing])
        for fmt, label in DATE_FORMATS
    ]
    valid_date_candidates = [
        candidate for candidate in date_candidates
        if non_missing and sum(value is not None for value in candidate[2]) / len(non_missing) >= 0.8
    ]
    is_identifier = bool(ID_COLUMN_PATTERN.search(column))

    profile: dict[str, Any] = {
        "detected_type": "text",
        "analysis_type": "text",
        "confidence": "low",
        "missing_count": missing_count,
        "invalid_count": 0,
        "normalized_count": 0,
    }
    normalized: list[Any] = list(values)

    if valid_date_candidates:
        # A slash-form date such as 03/04/2026 can legitimately be either
        # month/day/year or day/month/year. Only normalize it when one format
        # has clearly more valid rows; otherwise retain the raw text and let
        # the user choose a locale rather than silently changing its meaning.
        valid_date_candidates.sort(key=lambda candidate: sum(value is not None for value in candidate[2]), reverse=True)
        fmt, label, date_values = valid_date_candidates[0]
        best_count = sum(value is not None for value in date_values)
        second_count = sum(value is not None for value in valid_date_candidates[1][2]) if len(valid_date_candidates) > 1 else -1
        unambiguous = best_count > second_count or label.startswith("ISO")
    else:
        unambiguous = False

    if unambiguous:
        profile.update({
            "detected_type": "date",
            "analysis_type": "date",
            "confidence": "high" if best_count == len(non_missing) else "medium",
            "invalid_count": len(non_missing) - best_count,
            "normalized_count": best_count,
            "date_format": label,
        })
        normalized = [_parse_date(value, fmt) if value is not None else None for value in values]
    elif non_missing and numeric_ratio >= 0.8 and not is_identifier:
        kinds = [kind for number, kind in parsed if number is not None]
        detected = "currency" if kinds.count("currency") >= max(1, len(kinds) * 0.5) else (
            "percentage" if kinds.count("percentage") >= max(1, len(kinds) * 0.5) else "number"
        )
        profile.update({
            "detected_type": detected,
            "analysis_type": "number",
            "confidence": "high" if numeric_ratio == 1 else "medium",
            "invalid_count": len(non_missing) - numeric_count,
            "normalized_count": numeric_count,
        })
        normalized = [(_parse_number(value)[0] if value is not None else None) for value in values]
    elif is_identifier:
        profile.update({"detected_type": "identifier", "analysis_type": "text", "confidence": "high"})

    return profile, normalized


def parse_csv(contents: bytes) -> tuple[list[str], list[dict[str, Any]], list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Parse a CSV into immutable raw values and analysis-ready normalized values."""

    try:
        dataframe = pd.read_csv(io.BytesIO(contents), dtype=object, keep_default_na=False)
    except UnicodeDecodeError:
        try:
            dataframe = pd.read_csv(io.BytesIO(contents), encoding="latin-1", dtype=object, keep_default_na=False)
        except (pd.errors.EmptyDataError, pd.errors.ParserError, UnicodeDecodeError):
            raise CsvValidationError("CSV could not be decoded or parsed.") from None
    except pd.errors.EmptyDataError:
        raise CsvValidationError("CSV contains no readable columns.") from None
    except pd.errors.ParserError:
        raise CsvValidationError("CSV is malformed and could not be parsed.") from None
    except Exception:
        raise CsvValidationError("CSV could not be read.") from None

    if len(dataframe.columns) == 0:
        raise CsvValidationError("CSV contains no columns.")
    if dataframe.columns.duplicated().any():
        raise CsvValidationError("CSV column names must be unique.")

    columns = [str(column).strip() for column in dataframe.columns]
    if any(not column for column in columns):
        raise CsvValidationError("CSV column names cannot be blank.")
    if len(set(columns)) != len(columns):
        raise CsvValidationError("CSV column names must be unique after trimming spaces.")
    if dataframe.empty:
        raise CsvValidationError("CSV contains no data rows.")

    dataframe.columns = columns
    raw_records = [
        {column: _clean_cell(row[column]) for column in columns}
        for _, row in dataframe.iterrows()
    ]
    profiles: dict[str, dict[str, Any]] = {}
    normalized_columns: dict[str, list[Any]] = {}
    for column in columns:
        profile, normalized = _profile_column(column, [row[column] for row in raw_records])
        profiles[column] = profile
        normalized_columns[column] = normalized
    records = [
        {column: normalized_columns[column][index] for column in columns}
        for index in range(len(raw_records))
    ]
    # Guard against accidental NaN/Infinity values before FastAPI serializes.
    records = json.loads(json.dumps(records, allow_nan=False))
    return columns, records, raw_records, profiles
