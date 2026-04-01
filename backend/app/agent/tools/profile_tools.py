"""Profile and people tool definitions for the agent.

Gives the agent read/write access to the user's profile knowledge base
(ProfileFacts) and read access to the people directory.

Registered tools:
  - get_profile_facts   (READ_ONLY)  -- query facts by category/key pattern
  - add_profile_fact    (LOW_STAKES) -- add a new fact (auto-supersedes existing)
  - update_profile_fact (LOW_STAKES) -- create a new version of an existing fact
  - get_people          (READ_ONLY)  -- query contacts by relationship/name
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools.registry import ActionTier, ToolDefinition, register_tool
from app.models.tables import ProfileFact
from app.services.people import list_people
from app.services.profile import get_active_facts
from app.services.serialization import model_to_dict


# ── Handlers ──────────────────────────────────────────────────────


async def handle_get_profile_facts(db: AsyncSession, **kwargs: Any) -> dict:
    filters = kwargs.get("filters", {})
    category = filters.get("category")
    facts = await get_active_facts(db, category=category)

    # Optional key_pattern filtering
    key_pattern = filters.get("key_pattern")
    if key_pattern:
        facts = [f for f in facts if key_pattern.lower() in f.key.lower()]

    return {
        "facts": [model_to_dict(f) for f in facts],
        "count": len(facts),
    }


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

    old_fact.superseded_by = new_fact.id
    old_fact.updated_at = datetime.now(timezone.utc)
    await db.flush()

    return model_to_dict(new_fact)


async def handle_get_people(db: AsyncSession, **kwargs: Any) -> dict:
    filters = kwargs.get("filters", {})
    relationship = filters.get("relationship")
    name_filter = filters.get("name")

    people = await list_people(db, relationship_type=relationship)

    if name_filter:
        people = [p for p in people if name_filter.lower() in p.name.lower()]

    return {
        "people": [model_to_dict(p) for p in people],
        "count": len(people),
    }


# ── Tool Definitions ─────────────────────────────────────────────

register_tool(ToolDefinition(
    name="get_profile_facts",
    description="Get the user's profile facts, optionally filtered by category or key pattern. Use to look up preferences, personal info, schedule, etc.",
    input_schema={
        "type": "object",
        "properties": {
            "filters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "Filter by category (identity, household, preferences, career, aspirations, schedule)."},
                    "key_pattern": {"type": "string", "description": "Filter facts whose key contains this substring."},
                },
            },
        },
    },
    tier=ActionTier.READ_ONLY,
    handler=handle_get_profile_facts,
    category="profile",
))

register_tool(ToolDefinition(
    name="add_profile_fact",
    description="Add a new profile fact. If a fact with the same category+key already exists, it will be superseded by the new one.",
    input_schema={
        "type": "object",
        "properties": {
            "category": {"type": "string", "description": "Fact category (identity, household, preferences, career, aspirations, schedule)."},
            "key": {"type": "string", "description": "Fact key (e.g., 'dietary.likes.pizza', 'name')."},
            "value": {"description": "The fact value (string, number, object, or array)."},
            "provenance": {"type": "string", "description": "How the fact was learned (seeded, explicit, inferred). Default: explicit."},
            "evidence": {"type": "string", "description": "Evidence for inferred facts."},
            "confidence": {"type": "number", "description": "Confidence score 0-1. Default: 1.0."},
        },
        "required": ["category", "key", "value"],
    },
    tier=ActionTier.LOW_STAKES,
    handler=handle_add_profile_fact,
    category="profile",
))

register_tool(ToolDefinition(
    name="update_profile_fact",
    description="Update the value of an existing profile fact. Creates a new fact that supersedes the old one, preserving history.",
    input_schema={
        "type": "object",
        "properties": {
            "fact_id": {"type": "string", "description": "UUID of the existing fact to update."},
            "new_value": {"description": "The new value for the fact."},
            "provenance": {"type": "string", "description": "Provenance for the update."},
        },
        "required": ["fact_id", "new_value"],
    },
    tier=ActionTier.LOW_STAKES,
    handler=handle_update_profile_fact,
    category="profile",
))

register_tool(ToolDefinition(
    name="get_people",
    description="Get the user's people/contacts, optionally filtered by relationship type or name.",
    input_schema={
        "type": "object",
        "properties": {
            "filters": {
                "type": "object",
                "properties": {
                    "relationship": {"type": "string", "description": "Filter by relationship type (partner, family, friend, coworker, etc.)."},
                    "name": {"type": "string", "description": "Filter by name (substring match)."},
                },
            },
        },
    },
    tier=ActionTier.READ_ONLY,
    handler=handle_get_people,
    category="profile",
))
