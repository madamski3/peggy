from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class ProfileFieldInput(BaseModel):
    field_key: str
    value: Any


class ProfileSaveRequest(BaseModel):
    fields: list[ProfileFieldInput]


class ProfileFactResponse(BaseModel):
    id: UUID
    category: str
    key: str
    value: Any
    provenance: str
    confidence: float
    evidence: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProfileSectionData(BaseModel):
    """Current values for a profile section, keyed by field_key."""
    fields: dict[str, Any]


class ProfileResponse(BaseModel):
    identity: ProfileSectionData
    contact: ProfileSectionData
    household: ProfileSectionData
    preferences: ProfileSectionData
    career: ProfileSectionData
    aspirations: ProfileSectionData
    schedule: ProfileSectionData
