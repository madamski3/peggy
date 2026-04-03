"""Profile router -- endpoints for the Profile page.

GET /api/profile/  -- returns current profile structured by section (for form population)
POST /api/profile/ -- saves profile fields through the ingestion pipeline
GET /api/profile/facts -- returns raw active ProfileFact rows (for debugging/inspection)
POST /api/profile/consolidate-facts -- one-time migration to consolidated fact format
"""

from sqlalchemy import and_, select

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.tables import ProfileFact
from app.schemas.profile import (
    ProfileFactResponse,
    ProfileSaveRequest,
)
from app.services import people as people_service
from app.services import profile as profile_service
from app.services.embeddings import fact_to_text, get_embedding, get_embeddings_batch
from app.services.people import _build_consolidated_value

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


@router.post("/backfill-embeddings")
async def backfill_embeddings(db: AsyncSession = Depends(get_db)):
    """One-time backfill: generate embeddings for all active facts missing them."""
    facts = await profile_service.get_active_facts(db)
    missing = [f for f in facts if f.embedding is None]
    if not missing:
        return {"backfilled": 0, "message": "All facts already have embeddings"}

    texts = [fact_to_text(f.category, f.key, f.value) for f in missing]
    embeddings = await get_embeddings_batch(texts)
    for fact, emb in zip(missing, embeddings):
        fact.embedding = emb
    await db.commit()
    return {"backfilled": len(missing)}


@router.post("/consolidate-facts")
async def consolidate_facts(db: AsyncSession = Depends(get_db)):
    """One-time migration: consolidate fragmented facts into single records.

    - People: 1 consolidated fact per person (supersedes person.<uuid>.* fragments)
    - Dietary: 1 consolidated fact (supersedes dietary.likes.* and dietary.dislikes.*)

    Idempotent — safe to run multiple times.
    """
    stats = {"people_consolidated": 0, "dietary_consolidated": 0, "facts_superseded": 0}

    # ── People consolidation ────────────────────────────────────
    people = await people_service.list_people(db)
    for person in people:
        fact_key = f"person.{person.id}"

        # Skip if consolidated fact already exists
        existing = await db.execute(
            select(ProfileFact).where(
                ProfileFact.category == "people",
                ProfileFact.key == fact_key,
                ProfileFact.superseded_by.is_(None),
            )
        )
        if existing.scalar_one_or_none() is not None:
            continue

        # Create consolidated fact
        value = _build_consolidated_value(person)
        new_fact = ProfileFact(
            category="people",
            key=fact_key,
            value=value,
            provenance="seeded",
            confidence=1.0,
        )
        db.add(new_fact)
        await db.flush()

        text = fact_to_text("people", fact_key, value)
        new_fact.embedding = await get_embedding(text)

        # Supersede old fragmented facts (person.<uuid>.name, person.<uuid>.relationship, etc.)
        result = await db.execute(
            select(ProfileFact).where(
                and_(
                    ProfileFact.category == "people",
                    ProfileFact.key.startswith(f"person.{person.id}."),
                    ProfileFact.superseded_by.is_(None),
                )
            )
        )
        for old_fact in result.scalars().all():
            old_fact.superseded_by = new_fact.id
            stats["facts_superseded"] += 1

        stats["people_consolidated"] += 1

    # ── Dietary consolidation ───────────────────────────────────
    # Check if consolidated dietary fact already exists
    existing_dietary = await db.execute(
        select(ProfileFact).where(
            ProfileFact.category == "preferences",
            ProfileFact.key == "dietary",
            ProfileFact.superseded_by.is_(None),
        )
    )
    if existing_dietary.scalar_one_or_none() is None:
        # Collect individual dietary facts
        likes_result = await db.execute(
            select(ProfileFact).where(
                and_(
                    ProfileFact.category == "preferences",
                    ProfileFact.key.startswith("dietary.likes."),
                    ProfileFact.superseded_by.is_(None),
                )
            )
        )
        likes_facts = likes_result.scalars().all()

        dislikes_result = await db.execute(
            select(ProfileFact).where(
                and_(
                    ProfileFact.category == "preferences",
                    ProfileFact.key.startswith("dietary.dislikes."),
                    ProfileFact.superseded_by.is_(None),
                )
            )
        )
        dislikes_facts = dislikes_result.scalars().all()

        if likes_facts or dislikes_facts:
            value = {}
            if likes_facts:
                items = []
                for f in likes_facts:
                    # Flatten list values (e.g. fruit_snacks stored as a list)
                    if isinstance(f.value, list):
                        items.extend(str(x) for x in f.value)
                    else:
                        items.append(str(f.value))
                value["likes"] = items
            if dislikes_facts:
                items = []
                for f in dislikes_facts:
                    if isinstance(f.value, list):
                        items.extend(str(x) for x in f.value)
                    else:
                        items.append(str(f.value))
                value["dislikes"] = items

            new_fact = ProfileFact(
                category="preferences",
                key="dietary",
                value=value,
                provenance="seeded",
                confidence=1.0,
            )
            db.add(new_fact)
            await db.flush()

            text = fact_to_text("preferences", "dietary", value)
            new_fact.embedding = await get_embedding(text)

            # Supersede individual facts
            for old_fact in list(likes_facts) + list(dislikes_facts):
                old_fact.superseded_by = new_fact.id
                stats["facts_superseded"] += 1

            stats["dietary_consolidated"] = 1

    # Also supersede any dietary.notes.* facts into the consolidated fact
    notes_result = await db.execute(
        select(ProfileFact).where(
            and_(
                ProfileFact.category == "preferences",
                ProfileFact.key.startswith("dietary.notes."),
                ProfileFact.superseded_by.is_(None),
            )
        )
    )
    notes_facts = notes_result.scalars().all()
    if notes_facts:
        # Find the consolidated dietary fact to use as superseder
        consolidated = await db.execute(
            select(ProfileFact).where(
                ProfileFact.category == "preferences",
                ProfileFact.key == "dietary",
                ProfileFact.superseded_by.is_(None),
            )
        )
        dietary_fact = consolidated.scalar_one_or_none()
        if dietary_fact:
            # Merge notes into the consolidated value
            notes_dict = {f.key.split(".")[-1]: str(f.value) for f in notes_facts}
            if notes_dict:
                current_value = dict(dietary_fact.value) if dietary_fact.value else {}
                current_value["notes"] = notes_dict
                dietary_fact.value = current_value
                dietary_fact.embedding = await get_embedding(
                    fact_to_text("preferences", "dietary", current_value)
                )

            for old_fact in notes_facts:
                old_fact.superseded_by = dietary_fact.id
                stats["facts_superseded"] += 1

    await db.commit()
    return {"success": True, **stats}
