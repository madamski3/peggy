"""People service layer -- CRUD for the contacts directory.

Each person has basic info (name, relationship, description), structured
JSONB fields (contact_info, key_dates, preferences), and free-text notes.

Creating or updating a person also triggers the ingestion pipeline
(services/ingestion.py) to generate ProfileFact rows, so the agent can
query information about people during conversations.

Called by routers/people.py and agent tools (profile_tools.py for reads).
"""
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import Person
from app.services.ingestion import ingest_field_changes


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
    """Create a new person and ingest their data as ProfileFacts."""
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
    await db.flush()  # Get the ID

    # Build field list for ingestion
    fields = [{"field_key": k, "value": v} for k, v in data.items() if v is not None]
    await ingest_field_changes(db, "person", person.id, fields)

    return person


async def update_person(
    db: AsyncSession,
    person_id: uuid.UUID,
    data: dict[str, Any],
) -> Person | None:
    """Update a person and re-ingest changed fields."""
    person = await get_person(db, person_id)
    if person is None:
        return None

    # Update the person record
    for key, value in data.items():
        if hasattr(person, key) and value is not None:
            setattr(person, key, value)
    person.updated_at = datetime.now(timezone.utc)

    # Ingest field changes
    fields = [{"field_key": k, "value": v} for k, v in data.items() if v is not None]
    await ingest_field_changes(db, "person", person.id, fields)

    return person


async def delete_person(db: AsyncSession, person_id: uuid.UUID) -> bool:
    """Delete a person."""
    person = await get_person(db, person_id)
    if person is None:
        return False
    await db.delete(person)
    await db.commit()
    return True
