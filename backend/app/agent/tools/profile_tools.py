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
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools.registry import ActionTier, ToolDefinition, register_tool
from app.models.tables import ProfileFact
from app.services.embeddings import fact_to_text, get_embedding
from app.services.serialization import model_to_dict


# ── Handlers ──────────────────────────────────────────────────────


async def handle_add_profile_fact(db: AsyncSession, **kwargs: Any) -> dict:
    # Unlike the ingestion pipeline (which handles form data), this handler
    # lets the agent directly add/supersede facts during conversation.
    # If a fact with the same category+key already exists, the old one gets
    # superseded by the new one, preserving the edit chain.
    fact = ProfileFact(
        category=kwargs["category"],
        key=kwargs["key"],
        value=kwargs["value"],
        provenance=kwargs.get("provenance", "explicit"),
        confidence=kwargs.get("confidence", 1.0),
        evidence=kwargs.get("evidence"),
    )

    # Check for existing active fact with same category+key
    existing = await db.execute(
        select(ProfileFact).where(
            ProfileFact.category == kwargs["category"],
            ProfileFact.key == kwargs["key"],
            ProfileFact.superseded_by.is_(None),
        )
    )
    old_fact = existing.scalar_one_or_none()

    db.add(fact)
    await db.flush()

    # Generate embedding
    text = fact_to_text(fact.category, fact.key, fact.value)
    fact.embedding = await get_embedding(text)

    # Supersede old fact if it exists
    if old_fact is not None:
        old_fact.superseded_by = fact.id
        old_fact.updated_at = datetime.now(timezone.utc)
        await db.flush()

    return model_to_dict(fact)


async def handle_update_profile_fact(db: AsyncSession, **kwargs: Any) -> dict:
    fact_id = uuid.UUID(kwargs["fact_id"])
    result = await db.execute(select(ProfileFact).where(ProfileFact.id == fact_id))
    old_fact = result.scalar_one_or_none()
    if old_fact is None:
        return {"error": "Profile fact not found"}

    # Create new fact that supersedes the old one
    new_fact = ProfileFact(
        category=old_fact.category,
        key=old_fact.key,
        value=kwargs["new_value"],
        provenance=kwargs.get("provenance", old_fact.provenance),
        confidence=old_fact.confidence,
    )
    db.add(new_fact)
    await db.flush()

    # Generate embedding
    text = fact_to_text(new_fact.category, new_fact.key, new_fact.value)
    new_fact.embedding = await get_embedding(text)

    old_fact.superseded_by = new_fact.id
    old_fact.updated_at = datetime.now(timezone.utc)
    await db.flush()

    return model_to_dict(new_fact)


# ── Tool Definitions ─────────────────────────────────────────────

register_tool(ToolDefinition(
    name="add_profile_fact",
    description=(
        "Add a profile fact; auto-supersedes existing fact with same category+key. "
        "For people, use category='people' with key='person.<name>' and value as a "
        "JSON object with name, relationship_type, description, key_dates, etc."
    ),
    embedding_text=(
        "profile: add_profile_fact — remember, save, store personal information, "
        "preferences, people, contacts, facts about me. Remember that I prefer X. "
        "Save this person's info. Note that my anniversary is on June 5th."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "category": {"type": "string", "enum": ["identity", "household", "preferences", "career", "aspirations", "schedule", "people"]},
            "key": {"type": "string"},
            "value": {},
            "provenance": {"type": "string", "enum": ["seeded", "explicit", "inferred"]},
            "evidence": {"type": "string"},
            "confidence": {"type": "number"},
        },
        "required": ["category", "key", "value"],
    },
    tier=ActionTier.LOW_STAKES,
    handler=handle_add_profile_fact,
    category="profile",
))

register_tool(ToolDefinition(
    name="update_profile_fact",
    description="Update a profile fact's value, creating a new version.",
    embedding_text=(
        "profile: update_profile_fact — update, change, correct personal information "
        "or a stored fact. Actually my birthday is in March. Update my job title."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "fact_id": {"type": "string"},
            "new_value": {},
            "provenance": {"type": "string"},
        },
        "required": ["fact_id", "new_value"],
    },
    tier=ActionTier.LOW_STAKES,
    handler=handle_update_profile_fact,
    category="profile",
))



# ── Semantic Search ──────────────────────────────────────────────


async def handle_search_profile(db: AsyncSession, **kwargs: Any) -> dict:
    query_text = kwargs["query"]
    limit = kwargs.get("limit", 5)
    query_embedding = await get_embedding(query_text)

    results = await db.execute(
        select(ProfileFact)
        .where(
            ProfileFact.superseded_by.is_(None),
            ProfileFact.embedding.isnot(None),
        )
        .order_by(ProfileFact.embedding.cosine_distance(query_embedding))
        .limit(limit)
    )
    facts = results.scalars().all()
    return {
        "source": "user_database",
        "facts": [model_to_dict(f, exclude={"embedding"}) for f in facts],
        "count": len(facts),
    }


register_tool(ToolDefinition(
    name="search_profile",
    description=(
        "Search the user's personal knowledge base. This is the single source for ALL "
        "personal information — people/contacts/family, preferences, schedule, identity, "
        "household, career, etc. Returns the most relevant facts ranked by similarity."
    ),
    embedding_text=(
        "profile: search_profile — look up, find, recall personal information, "
        "people, contacts, family, preferences, household, career, identity. "
        "What's my wife's name? Do I have any dietary restrictions? "
        "Who is John? What do you know about me?"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Natural language search query, e.g. 'dietary preferences' or 'work schedule'",
            },
            "limit": {
                "type": "integer",
                "description": "Max results to return (default 5)",
            },
        },
        "required": ["query"],
    },
    tier=ActionTier.READ_ONLY,
    handler=handle_search_profile,
    category="profile",
))
