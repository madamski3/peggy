"""Profile service layer -- reading and writing the user's profile.

Two representations of the profile exist:
  1. SeedFieldVersions -- the raw form field values (what the Profile page
     reads and writes). get_current_profile() returns these, structured by section.
  2. ProfileFacts -- the normalized knowledge base that the agent queries.
     save_profile() triggers the ingestion pipeline to sync (1) into (2).

get_active_facts() is the primary read path for the agent -- it returns
all non-superseded facts, which get injected into the system prompt context.

Called by routers/profile.py and agent tools (profile_tools.py).
"""
import json
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import ProfileFact, SeedFieldVersion
from app.services.field_mappings import PROFILE_FIELD_MAPPINGS
from app.services.ingestion import ingest_field_changes


# Which field_keys belong to each section
SECTION_FIELDS: dict[str, list[str]] = {
    "identity": ["name", "date_of_birth", "location", "timezone", "living_situation"],
    "contact": ["contacts"],
    "household": ["partner_name", "pets", "vehicles"],
    "preferences": ["dietary_likes", "dietary_dislikes", "communication_style"],
    "career": ["roles", "professional_skills"],
    "hobbies": ["hobbies", "interests"],
    "aspirations": ["aspirations"],
    "schedule": ["waking_hours", "preferred_work_hours", "preferred_errand_time"],
}


async def get_current_profile(db: AsyncSession) -> dict[str, dict[str, Any]]:
    """Get the current profile structured by section.

    Returns the latest SeedFieldVersion value for each profile field.
    """
    profile: dict[str, dict[str, Any]] = {}

    for section, field_keys in SECTION_FIELDS.items():
        fields: dict[str, Any] = {}
        for field_key in field_keys:
            result = await db.execute(
                select(SeedFieldVersion)
                .where(
                    and_(
                        SeedFieldVersion.entity_type == "profile",
                        SeedFieldVersion.entity_id.is_(None),
                        SeedFieldVersion.field_key == field_key,
                    )
                )
                .order_by(SeedFieldVersion.edited_at.desc())
                .limit(1)
            )
            version = result.scalar_one_or_none()
            if version is not None:
                try:
                    fields[field_key] = json.loads(version.value)
                except (json.JSONDecodeError, TypeError):
                    fields[field_key] = version.value
            else:
                fields[field_key] = None
        profile[section] = {"fields": fields}

    return profile


async def save_profile(
    db: AsyncSession,
    fields: list[dict[str, Any]],
) -> list:
    """Save profile fields, triggering the ingestion pipeline."""
    return await ingest_field_changes(db, "profile", None, fields)


async def get_primary_email(db: AsyncSession) -> str | None:
    """Return the primary email address from profile contacts, or None.

    Reads from SeedFieldVersion (the raw form data) to get the contacts
    array, then finds the first entry with type="email" and primary=True.
    """
    result = await db.execute(
        select(SeedFieldVersion)
        .where(
            and_(
                SeedFieldVersion.entity_type == "profile",
                SeedFieldVersion.entity_id.is_(None),
                SeedFieldVersion.field_key == "contacts",
            )
        )
        .order_by(SeedFieldVersion.edited_at.desc())
        .limit(1)
    )
    version = result.scalar_one_or_none()
    if version is None:
        return None

    try:
        contacts = json.loads(version.value)
    except (json.JSONDecodeError, TypeError):
        return None

    if not isinstance(contacts, list):
        return None

    for contact in contacts:
        if (
            isinstance(contact, dict)
            and contact.get("type") == "email"
            and contact.get("primary") is True
            and contact.get("value")
        ):
            return contact["value"].strip().lower()

    return None


async def get_active_facts(
    db: AsyncSession,
    category: str | None = None,
) -> list[ProfileFact]:
    """Get active (non-superseded) profile facts, optionally filtered by category."""
    query = select(ProfileFact).where(ProfileFact.superseded_by.is_(None))
    if category:
        query = query.where(ProfileFact.category == category)
    query = query.order_by(ProfileFact.category, ProfileFact.key)
    result = await db.execute(query)
    return list(result.scalars().all())
