"""People service layer -- CRUD for the contacts directory.

Each person has basic info (name, relationship, description), structured
JSONB fields (contact_info, key_dates, preferences), and free-text notes.

Creating or updating a person also syncs a consolidated ProfileFact row
so the agent can find people via search_profile alongside all other
personal knowledge.

Called by routers/people.py and agent tools (profile_tools.py for reads).
"""
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import Person, ProfileFact, SeedFieldVersion
from app.services.embeddings import fact_to_text, get_embedding, person_to_text


# ── Internal helpers ────────────────────────────────────────────


def _build_consolidated_value(person: Person) -> dict:
    """Build the consolidated ProfileFact value from a Person record."""
    value: dict[str, Any] = {"name": person.name}
    if person.relationship_type:
        value["relationship_type"] = person.relationship_type
    if person.description:
        value["description"] = person.description
    if person.contact_info:
        value["contact_info"] = person.contact_info
    if person.key_dates:
        value["key_dates"] = person.key_dates
    if person.preferences:
        value["preferences"] = person.preferences
    if person.notes:
        value["notes"] = person.notes
    return value


async def _sync_person_profile_fact(db: AsyncSession, person: Person) -> ProfileFact | None:
    """Create or update the consolidated ProfileFact for a person.

    Returns the new fact, or None if nothing changed since last sync.
    """
    fact_key = f"person.{person.id}"
    value = _build_consolidated_value(person)
    serialized = json.dumps(value, sort_keys=True, default=str)

    # Diff check via SeedFieldVersion
    latest = await db.execute(
        select(SeedFieldVersion)
        .where(
            SeedFieldVersion.entity_type == "person",
            SeedFieldVersion.entity_id == person.id,
            SeedFieldVersion.field_key == "__consolidated__",
        )
        .order_by(SeedFieldVersion.edited_at.desc())
        .limit(1)
    )
    latest_version = latest.scalar_one_or_none()
    if latest_version is not None and latest_version.value == serialized:
        return None  # No change

    # Track the new version
    db.add(SeedFieldVersion(
        entity_type="person",
        entity_id=person.id,
        field_key="__consolidated__",
        value=serialized,
    ))

    # Create consolidated ProfileFact
    new_fact = ProfileFact(
        category="people",
        key=fact_key,
        value=value,
        provenance="seeded",
        confidence=1.0,
    )
    db.add(new_fact)
    await db.flush()

    # Generate embedding from rich text
    text = fact_to_text(new_fact.category, new_fact.key, new_fact.value)
    new_fact.embedding = await get_embedding(text)

    # Supersede previous consolidated fact (if any)
    result = await db.execute(
        select(ProfileFact).where(
            ProfileFact.category == "people",
            ProfileFact.key == fact_key,
            ProfileFact.superseded_by.is_(None),
            ProfileFact.id != new_fact.id,
        )
    )
    for old_fact in result.scalars().all():
        old_fact.superseded_by = new_fact.id
        old_fact.updated_at = datetime.now(timezone.utc)

    return new_fact


# ── Public API ──────────────────────────────────────────────────


async def list_people(
    db: AsyncSession,
    relationship_type: str | None = None,
) -> list[Person]:
    """List all people, optionally filtered by relationship type."""
    query = select(Person).order_by(Person.name)
    if relationship_type:
        query = query.where(Person.relationship_type == relationship_type)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_person(db: AsyncSession, person_id: uuid.UUID) -> Person | None:
    """Get a single person by ID."""
    result = await db.execute(select(Person).where(Person.id == person_id))
    return result.scalar_one_or_none()


async def create_person(db: AsyncSession, data: dict[str, Any]) -> Person:
    """Create a new person and sync a consolidated ProfileFact."""
    person = Person(
        name=data["name"],
        relationship_type=data.get("relationship_type"),
        description=data.get("description"),
        contact_info=data.get("contact_info"),
        key_dates=data.get("key_dates"),
        preferences=data.get("preferences"),
        notes=data.get("notes"),
    )
    db.add(person)
    await db.flush()

    # Generate Person table embedding
    text = person_to_text(person.name, person.relationship_type,
                          person.description, person.notes, person.preferences)
    person.embedding = await get_embedding(text)

    # Sync consolidated ProfileFact for search_profile
    await _sync_person_profile_fact(db, person)
    await db.commit()

    return person


async def update_person(
    db: AsyncSession,
    person_id: uuid.UUID,
    data: dict[str, Any],
) -> Person | None:
    """Update a person and re-sync the consolidated ProfileFact."""
    person = await get_person(db, person_id)
    if person is None:
        return None

    for key, value in data.items():
        if hasattr(person, key) and value is not None:
            setattr(person, key, value)
    person.updated_at = datetime.now(timezone.utc)

    # Regenerate Person table embedding
    text = person_to_text(person.name, person.relationship_type,
                          person.description, person.notes, person.preferences)
    person.embedding = await get_embedding(text)

    # Re-sync consolidated ProfileFact
    await _sync_person_profile_fact(db, person)
    await db.commit()

    return person


async def delete_person(db: AsyncSession, person_id: uuid.UUID) -> bool:
    """Delete a person and supersede their consolidated ProfileFact."""
    person = await get_person(db, person_id)
    if person is None:
        return False

    # Supersede the consolidated ProfileFact
    fact_key = f"person.{person.id}"
    result = await db.execute(
        select(ProfileFact).where(
            ProfileFact.category == "people",
            ProfileFact.key == fact_key,
            ProfileFact.superseded_by.is_(None),
        )
    )
    for fact in result.scalars().all():
        fact.superseded_by = fact.id  # self-reference marks deletion

    await db.delete(person)
    await db.commit()
    return True
