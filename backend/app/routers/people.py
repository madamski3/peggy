"""People router -- REST CRUD for the contacts directory.

Provides standard list/create/get/update/delete endpoints at /api/people/.
Used by the People page in the frontend. Creating or updating a person
triggers the ingestion pipeline (via the people service) to generate
ProfileFacts that the agent can query.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.people import (
    PersonCreate,
    PersonListResponse,
    PersonResponse,
    PersonUpdate,
)
from app.services import people as people_service

router = APIRouter(prefix="/people", tags=["people"])


@router.get("/", response_model=PersonListResponse)
async def list_people(
    relationship: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """List all people, optionally filtered by relationship type."""
    people = await people_service.list_people(db, relationship)
    return PersonListResponse(people=people)


@router.post("/", response_model=PersonResponse, status_code=201)
async def create_person(
    data: PersonCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new person."""
    person = await people_service.create_person(db, data.model_dump())
    return person


@router.get("/{person_id}", response_model=PersonResponse)
async def get_person(
    person_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get a person by ID."""
    person = await people_service.get_person(db, person_id)
    if person is None:
        raise HTTPException(status_code=404, detail="Person not found")
    return person


@router.put("/{person_id}", response_model=PersonResponse)
async def update_person(
    person_id: uuid.UUID,
    data: PersonUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a person."""
    person = await people_service.update_person(
        db, person_id, data.model_dump(exclude_unset=True)
    )
    if person is None:
        raise HTTPException(status_code=404, detail="Person not found")
    return person


@router.delete("/{person_id}")
async def delete_person(
    person_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Delete a person."""
    deleted = await people_service.delete_person(db, person_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Person not found")
    return {"success": True}
