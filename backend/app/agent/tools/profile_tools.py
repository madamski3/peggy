"""Profile tool definitions for the agent.

Gives the agent read/write access to the unified personal knowledge base
(ProfileFacts). This is the single search surface for ALL personal
information — identity, preferences, people/contacts, career, etc.

Registered tools:
  - search_profile      (READ_ONLY)  -- semantic vector search across all facts
  - add_profile_fact    (LOW_STAKES) -- add a new fact (auto-supersedes existing)
  - update_profile_fact (LOW_STAKES) -- create a new version of an existing fact
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools.registry import ActionTier, tool
from app.models.tables import ProfileFact
from app.services.embeddings import fact_to_text, get_embedding
from app.services.serialization import model_to_dict


ProfileCategory = Literal[
    "identity", "household", "preferences", "career",
    "aspirations", "schedule", "people",
]
Provenance = Literal["seeded", "explicit", "inferred"]


class AddProfileFactInput(BaseModel):
    category: ProfileCategory
    key: str
    value: Any
    provenance: Provenance = "explicit"
    evidence: str | None = None
    confidence: float = 1.0


class UpdateProfileFactInput(BaseModel):
    fact_id: str
    new_value: Any
    provenance: str | None = None


class SearchProfileInput(BaseModel):
    query: str = Field(
        ...,
        description="Natural language search query, e.g. 'dietary preferences' or 'work schedule'",
    )
    limit: int = Field(5, description="Max results to return (default 5)")


@tool(
    tier=ActionTier.LOW_STAKES,
    category="profile",
    embedding_text=(
        "profile: add_profile_fact — remember, save, store personal information, "
        "preferences, people, contacts, facts about me. Remember that I prefer X. "
        "Save this person's info. Note that my anniversary is on June 5th."
    ),
)
async def add_profile_fact(db: AsyncSession, input: AddProfileFactInput) -> dict:
    """Add a profile fact; auto-supersedes existing fact with same category+key.

    For people, use category='people' with key='person.<name>' and value as a
    JSON object with name, relationship_type, description, key_dates, etc.
    """
    fact = ProfileFact(
        category=input.category,
        key=input.key,
        value=input.value,
        provenance=input.provenance,
        confidence=input.confidence,
        evidence=input.evidence,
    )

    existing = await db.execute(
        select(ProfileFact).where(
            ProfileFact.category == input.category,
            ProfileFact.key == input.key,
            ProfileFact.superseded_by.is_(None),
        )
    )
    old_fact = existing.scalar_one_or_none()

    db.add(fact)
    await db.flush()

    text = fact_to_text(fact.category, fact.key, fact.value)
    fact.embedding = await get_embedding(text)

    if old_fact is not None:
        old_fact.superseded_by = fact.id
        old_fact.updated_at = datetime.now(timezone.utc)
        await db.flush()

    return model_to_dict(fact)


@tool(
    tier=ActionTier.LOW_STAKES,
    category="profile",
    embedding_text=(
        "profile: update_profile_fact — update, change, correct personal information "
        "or a stored fact. Actually my birthday is in March. Update my job title."
    ),
)
async def update_profile_fact(db: AsyncSession, input: UpdateProfileFactInput) -> dict:
    """Update a profile fact's value, creating a new version."""
    fact_id = uuid.UUID(input.fact_id)
    result = await db.execute(select(ProfileFact).where(ProfileFact.id == fact_id))
    old_fact = result.scalar_one_or_none()
    if old_fact is None:
        return {"error": "Profile fact not found"}

    new_fact = ProfileFact(
        category=old_fact.category,
        key=old_fact.key,
        value=input.new_value,
        provenance=input.provenance or old_fact.provenance,
        confidence=old_fact.confidence,
    )
    db.add(new_fact)
    await db.flush()

    text = fact_to_text(new_fact.category, new_fact.key, new_fact.value)
    new_fact.embedding = await get_embedding(text)

    old_fact.superseded_by = new_fact.id
    old_fact.updated_at = datetime.now(timezone.utc)
    await db.flush()

    return model_to_dict(new_fact)


@tool(
    tier=ActionTier.READ_ONLY,
    category="profile",
    embedding_text=(
        "profile: search_profile — look up, find, recall personal information, "
        "people, contacts, family, preferences, household, career, identity. "
        "What's my wife's name? Do I have any dietary restrictions? "
        "Who is John? What do you know about me?"
    ),
)
async def search_profile(db: AsyncSession, input: SearchProfileInput) -> dict:
    """Search the user's personal knowledge base.

    This is the single source for ALL personal information — people/contacts/family,
    preferences, schedule, identity, household, career, etc. Returns the most
    relevant facts ranked by similarity.
    """
    query_embedding = await get_embedding(input.query)

    results = await db.execute(
        select(ProfileFact)
        .where(
            ProfileFact.superseded_by.is_(None),
            ProfileFact.embedding.isnot(None),
        )
        .order_by(ProfileFact.embedding.cosine_distance(query_embedding))
        .limit(input.limit)
    )
    facts = results.scalars().all()
    return {
        "source": "user_database",
        "facts": [model_to_dict(f, exclude={"embedding"}) for f in facts],
        "count": len(facts),
    }
