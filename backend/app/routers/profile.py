"""Profile router -- endpoints for the Profile page.

GET /api/profile/  -- returns current profile structured by section (for form population)
POST /api/profile/ -- saves profile fields through the ingestion pipeline
GET /api/profile/facts -- returns raw active ProfileFact rows (for debugging/inspection)
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.profile import (
    ProfileFactResponse,
    ProfileSaveRequest,
)
from app.services import profile as profile_service

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("/")
async def get_profile(db: AsyncSession = Depends(get_db)):
    """Get the current profile structured by section."""
    return await profile_service.get_current_profile(db)


@router.post("/")
async def save_profile(
    request: ProfileSaveRequest,
    db: AsyncSession = Depends(get_db),
):
    """Save profile fields and trigger biography ingestion."""
    fields = [{"field_key": f.field_key, "value": f.value} for f in request.fields]
    created = await profile_service.save_profile(db, fields)
    return {
        "success": True,
        "facts_created": len(created),
        "profile": await profile_service.get_current_profile(db),
    }


@router.get("/facts", response_model=list[ProfileFactResponse])
async def get_facts(
    category: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Get active profile facts, optionally filtered by category."""
    return await profile_service.get_active_facts(db, category)
