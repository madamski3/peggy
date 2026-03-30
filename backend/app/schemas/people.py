from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class PersonCreate(BaseModel):
    name: str
    relationship_type: str | None = None
    description: str | None = None
    contact_info: dict[str, Any] | None = None
    key_dates: dict[str, Any] | None = None
    preferences: dict[str, Any] | None = None
    notes: str | None = None


class PersonUpdate(BaseModel):
    name: str | None = None
    relationship_type: str | None = None
    description: str | None = None
    contact_info: dict[str, Any] | None = None
    key_dates: dict[str, Any] | None = None
    preferences: dict[str, Any] | None = None
    notes: str | None = None


class PersonResponse(BaseModel):
    id: UUID
    name: str
    relationship_type: str | None = None
    description: str | None = None
    contact_info: dict[str, Any] | None = None
    key_dates: dict[str, Any] | None = None
    preferences: dict[str, Any] | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PersonListResponse(BaseModel):
    people: list[PersonResponse]
