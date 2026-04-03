"""Biography ingestion pipeline.

This is the bridge between the form-based UI and the agent's knowledge base.
When a user saves the Profile or People form, this pipeline converts form
field values into ProfileFact rows that the agent can query.

The pipeline runs per-field through ingest_field_changes():
  1. Diff detection -- compare the new value against the latest SeedFieldVersion.
     If unchanged, skip. This prevents duplicate facts on re-saves.
  2. Version creation -- write a new SeedFieldVersion row to track the edit.
  3. Fact generation -- use field_mappings.py to convert the field value into
     one or more ProfileFact dicts. A single field (e.g. "pets") may produce
     multiple facts (one per pet).
  4. Conflict resolution -- supersede existing active facts with the same
     category+key. For list fields, also supersede facts for items that were
     removed (e.g. a pet that was deleted from the form).

Used by both services/profile.py and services/people.py.
"""
import json
import uuid
from typing import Any, Literal

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import ProfileFact, SeedFieldVersion
from app.services.embeddings import fact_to_text, get_embedding
from app.services.field_mappings import PEOPLE_FIELD_MAPPINGS, PROFILE_FIELD_MAPPINGS


async def _get_latest_version(
    db: AsyncSession,
    entity_type: str,
    entity_id: uuid.UUID | None,
    field_key: str,
) -> SeedFieldVersion | None:
    """Get the most recent SeedFieldVersion for a field."""
    conditions = [
        SeedFieldVersion.entity_type == entity_type,
        SeedFieldVersion.field_key == field_key,
    ]
    if entity_id is not None:
        conditions.append(SeedFieldVersion.entity_id == entity_id)
    else:
        conditions.append(SeedFieldVersion.entity_id.is_(None))

    result = await db.execute(
        select(SeedFieldVersion)
        .where(and_(*conditions))
        .order_by(SeedFieldVersion.edited_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def _serialize_value(value: Any) -> str:
    """Serialize a field value to string for SeedFieldVersion storage."""
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, default=str)


def _generate_facts_from_field(
    field_key: str,
    value: Any,
    mapping: dict,
    entity_id: uuid.UUID | None = None,
) -> list[dict]:
    """Generate ProfileFact dicts from a field value using its mapping."""
    facts = []
    field_type = mapping["type"]

    if field_type == "single":
        if mapping.get("key_suffix"):
            key = f"person.{entity_id}.{mapping['key_suffix']}"
        else:
            key = mapping["key"]
        if value is not None and value != "":
            facts.append({
                "category": mapping["category"],
                "key": key,
                "value": value if isinstance(value, (dict, list)) else str(value),
            })

    elif field_type == "list":
        items = value if isinstance(value, list) else []
        prefix = mapping["key_prefix"]
        for item in items:
            item_str = str(item).strip()
            if item_str:
                facts.append({
                    "category": mapping["category"],
                    "key": f"{prefix}.{item_str.lower().replace(' ', '_')}",
                    "value": item_str,
                })

    elif field_type == "structured_list":
        items = value if isinstance(value, list) else []
        prefix = mapping["key_prefix"]
        id_field = mapping.get("id_field")
        name_field = mapping.get("name_field", "name")
        for item in items:
            if not isinstance(item, dict):
                continue
            # Require a non-empty name for validation
            if not item.get(name_field):
                continue
            # Use stable id_field for the key if available, fall back to name
            if id_field and item.get(id_field):
                key_suffix = item[id_field]
            else:
                key_suffix = item[name_field].lower().replace(" ", "_")
            facts.append({
                "category": mapping["category"],
                "key": f"{prefix}.{key_suffix}",
                "value": item,
            })

    elif field_type == "json":
        if mapping.get("key_suffix"):
            key = f"person.{entity_id}.{mapping['key_suffix']}"
        else:
            key = mapping["key"]
        if value is not None:
            facts.append({
                "category": mapping["category"],
                "key": key,
                "value": value,
            })

    return facts


async def _supersede_existing_facts(
    db: AsyncSession,
    category: str,
    key: str,
    new_fact_id: uuid.UUID,
) -> None:
    """Mark existing active facts with the same category+key as superseded."""
    result = await db.execute(
        select(ProfileFact).where(
            and_(
                ProfileFact.category == category,
                ProfileFact.key == key,
                ProfileFact.superseded_by.is_(None),
            )
        )
    )
    for existing in result.scalars().all():
        existing.superseded_by = new_fact_id


async def _supersede_removed_facts(
    db: AsyncSession,
    category: str,
    key_prefix: str,
    current_keys: set[str],
) -> None:
    """For list fields, supersede facts whose keys are no longer present.

    Example: if the user had hobbies [running, swimming, cycling] and saves
    [running, swimming], this supersedes the "cycling" fact.

    Uses self-reference (superseded_by = own id) to mark removal,
    satisfying the FK constraint without needing a replacement fact.
    """
    result = await db.execute(
        select(ProfileFact).where(
            and_(
                ProfileFact.category == category,
                ProfileFact.key.startswith(key_prefix + "."),
                ProfileFact.superseded_by.is_(None),
            )
        )
    )
    for existing in result.scalars().all():
        if existing.key not in current_keys:
            existing.superseded_by = existing.id


async def ingest_field_changes(
    db: AsyncSession,
    entity_type: Literal["profile", "person"],
    entity_id: uuid.UUID | None,
    fields: list[dict[str, Any]],
) -> list[ProfileFact]:
    """Main ingestion pipeline.

    Args:
        db: Database session
        entity_type: "profile" or "person"
        entity_id: None for profile, person UUID for people
        fields: List of {"field_key": str, "value": Any}

    Returns:
        List of newly created ProfileFact records
    """
    mappings = PROFILE_FIELD_MAPPINGS if entity_type == "profile" else PEOPLE_FIELD_MAPPINGS
    created_facts: list[ProfileFact] = []

    # Process each field independently. A single form save may contain
    # 10+ fields, but most will be unchanged and get skipped at step 1.
    for field in fields:
        field_key = field["field_key"]
        value = field["value"]

        mapping = mappings.get(field_key)
        if mapping is None:
            continue  # Field has no mapping -- not ingested as facts

        # Step 1: Diff detection
        serialized = _serialize_value(value)
        latest_version = await _get_latest_version(db, entity_type, entity_id, field_key)
        if latest_version is not None and latest_version.value == serialized:
            continue  # No change

        # Step 2: Create new version
        new_version = SeedFieldVersion(
            entity_type=entity_type,
            entity_id=entity_id,
            field_key=field_key,
            value=serialized,
        )
        db.add(new_version)

        # Step 3: Generate facts
        generated = _generate_facts_from_field(field_key, value, mapping, entity_id)

        # Step 4: For list/structured_list fields, supersede removed items
        if mapping["type"] in ("list", "structured_list"):
            current_keys = {f["key"] for f in generated}
            key_prefix = mapping.get("key_prefix", "")
            await _supersede_removed_facts(db, mapping["category"], key_prefix, current_keys)

        # Step 5: Create or update facts
        for fact_data in generated:
            new_fact = ProfileFact(
                category=fact_data["category"],
                key=fact_data["key"],
                value=fact_data["value"] if isinstance(fact_data["value"], (dict, list)) else fact_data["value"],
                provenance="seeded",
                confidence=1.0,
            )
            db.add(new_fact)
            await db.flush()  # Get the ID assigned

            # Generate embedding for the new fact
            text = fact_to_text(new_fact.category, new_fact.key, new_fact.value)
            new_fact.embedding = await get_embedding(text)

            # Supersede existing facts with same category+key (excluding the one we just created)
            result = await db.execute(
                select(ProfileFact).where(
                    and_(
                        ProfileFact.category == fact_data["category"],
                        ProfileFact.key == fact_data["key"],
                        ProfileFact.superseded_by.is_(None),
                        ProfileFact.id != new_fact.id,
                    )
                )
            )
            for existing in result.scalars().all():
                existing.superseded_by = new_fact.id

            created_facts.append(new_fact)

    # Post-processing: consolidate dietary preferences into a single fact
    if entity_type == "profile":
        dietary_fact = await _consolidate_dietary(db, fields)
        if dietary_fact:
            created_facts.append(dietary_fact)

    await db.commit()
    return created_facts


# ── Dietary consolidation ───────────────────────────────────────


_DIETARY_FIELD_KEYS = {"dietary_likes", "dietary_dislikes"}


async def _consolidate_dietary(
    db: AsyncSession,
    fields: list[dict[str, Any]],
) -> ProfileFact | None:
    """Consolidate dietary_likes and dietary_dislikes into one ProfileFact.

    Called after the main per-field loop. Reads current values from the
    submitted fields or falls back to the latest SeedFieldVersion.
    """
    submitted_keys = {f["field_key"] for f in fields}
    if not submitted_keys & _DIETARY_FIELD_KEYS:
        return None  # No dietary fields in this batch

    # Resolve current values: prefer submitted, fall back to saved version
    likes: list[str] = []
    dislikes: list[str] = []

    for field_key, target in [("dietary_likes", "likes"), ("dietary_dislikes", "dislikes")]:
        # Check submitted fields first
        submitted = next((f["value"] for f in fields if f["field_key"] == field_key), None)
        if submitted is not None:
            items = submitted if isinstance(submitted, list) else []
        else:
            # Fall back to latest saved version
            version = await _get_latest_version(db, "profile", None, field_key)
            if version is not None:
                try:
                    items = json.loads(version.value)
                    if not isinstance(items, list):
                        items = []
                except (json.JSONDecodeError, TypeError):
                    items = []
            else:
                items = []

        if target == "likes":
            likes = [str(x).strip() for x in items if str(x).strip()]
        else:
            dislikes = [str(x).strip() for x in items if str(x).strip()]

        # Still create SeedFieldVersion for diff detection on re-saves
        if submitted is not None:
            serialized = _serialize_value(submitted)
            latest = await _get_latest_version(db, "profile", None, field_key)
            if latest is None or latest.value != serialized:
                db.add(SeedFieldVersion(
                    entity_type="profile",
                    entity_id=None,
                    field_key=field_key,
                    value=serialized,
                ))

    value: dict[str, Any] = {}
    if likes:
        value["likes"] = likes
    if dislikes:
        value["dislikes"] = dislikes

    if not value:
        return None

    # Create consolidated fact
    new_fact = ProfileFact(
        category="preferences",
        key="dietary",
        value=value,
        provenance="seeded",
        confidence=1.0,
    )
    db.add(new_fact)
    await db.flush()

    text = fact_to_text(new_fact.category, new_fact.key, new_fact.value)
    new_fact.embedding = await get_embedding(text)

    # Supersede previous consolidated dietary fact
    result = await db.execute(
        select(ProfileFact).where(
            and_(
                ProfileFact.category == "preferences",
                ProfileFact.key == "dietary",
                ProfileFact.superseded_by.is_(None),
                ProfileFact.id != new_fact.id,
            )
        )
    )
    for old in result.scalars().all():
        old.superseded_by = new_fact.id

    # Also supersede any old per-item dietary facts
    result = await db.execute(
        select(ProfileFact).where(
            and_(
                ProfileFact.category == "preferences",
                ProfileFact.key.startswith("dietary."),
                ProfileFact.superseded_by.is_(None),
            )
        )
    )
    for old in result.scalars().all():
        old.superseded_by = new_fact.id

    return new_fact
