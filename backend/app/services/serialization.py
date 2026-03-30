"""Utilities for converting SQLAlchemy models to JSON-serializable dicts.

model_to_dict() is used throughout the services layer to convert ORM
instances into plain dicts before returning them to tool handlers or
routers. It handles UUIDs, datetimes, Decimals, and nested structures.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import DeclarativeBase


def model_to_dict(instance: DeclarativeBase, exclude: set[str] | None = None) -> dict[str, Any]:
    """Convert a SQLAlchemy model instance to a JSON-serializable dict.

    Handles UUIDs, datetimes, Decimals, and JSONB fields.
    Excludes SQLAlchemy internal state and any keys in `exclude`.
    """
    exclude = exclude or set()
    result: dict[str, Any] = {}

    for col in instance.__table__.columns:
        if col.name in exclude:
            continue
        value = getattr(instance, col.name)
        result[col.name] = _serialize_value(value)

    return result


def _serialize_value(value: Any) -> Any:
    """Recursively serialize a value for JSON output."""
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, list):
        return [_serialize_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items()}
    return value
