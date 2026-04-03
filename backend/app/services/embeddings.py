"""Thin wrapper around OpenAI embeddings API for vector search."""

import json
import logging

from openai import AsyncOpenAI

from app.config import settings

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None
_MODEL = "text-embedding-3-small"


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


async def get_embedding(text: str) -> list[float]:
    """Get embedding vector for a single text string."""
    client = _get_client()
    resp = await client.embeddings.create(model=_MODEL, input=text)
    return resp.data[0].embedding


async def get_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """Get embedding vectors for multiple texts in one API call."""
    if not texts:
        return []
    client = _get_client()
    resp = await client.embeddings.create(model=_MODEL, input=texts)
    return [item.embedding for item in resp.data]


def fact_to_text(category: str, key: str, value) -> str:
    """Serialize a profile fact into searchable embedding text.

    Consolidated facts (people, dietary) get natural-language text so that
    vector search matches on names, relationships, dates, etc.
    """
    # People facts: rich natural-language representation
    if category == "people" and isinstance(value, dict) and "name" in value:
        return _person_value_to_text(value)

    # Consolidated dietary preferences
    if category == "preferences" and key == "dietary" and isinstance(value, dict):
        return _dietary_value_to_text(value)

    # Default: simple key=value
    if isinstance(value, (dict, list)):
        val_str = json.dumps(value)
    else:
        val_str = str(value)
    return f"{category}: {key} = {val_str}"


def _person_value_to_text(value: dict) -> str:
    """Build rich embedding text from a consolidated person fact value."""
    parts = [f"person: {value['name']}"]
    if value.get("relationship_type"):
        parts.append(f"relationship: {value['relationship_type']}")
    if value.get("description"):
        parts.append(f"description: {value['description']}")
    if value.get("notes"):
        parts.append(f"notes: {value['notes']}")
    if value.get("key_dates"):
        for date_key, date_val in value["key_dates"].items():
            parts.append(f"{date_key}: {date_val}")
    if value.get("contact_info"):
        for info_key, info_val in value["contact_info"].items():
            parts.append(f"{info_key}: {info_val}")
    if value.get("preferences"):
        for pref_key, pref_val in value["preferences"].items():
            parts.append(f"{pref_key}: {pref_val}")
    return "; ".join(parts)


def _dietary_value_to_text(value: dict) -> str:
    """Build embedding text from consolidated dietary preferences."""
    parts = ["dietary preferences"]
    if value.get("likes"):
        parts.append(f"likes {', '.join(str(x) for x in value['likes'])}")
    if value.get("dislikes"):
        parts.append(f"dislikes {', '.join(str(x) for x in value['dislikes'])}")
    if value.get("notes"):
        for note_key, note_val in value["notes"].items():
            parts.append(f"{note_key}: {note_val}")
    return "; ".join(parts)


def person_to_text(name: str, relationship_type: str | None,
                   description: str | None, notes: str | None,
                   preferences: dict | None) -> str:
    """Serialize a person record into embeddable text."""
    parts = [f"person: {name}"]
    if relationship_type:
        parts.append(f"relationship: {relationship_type}")
    if description:
        parts.append(f"description: {description}")
    if notes:
        parts.append(f"notes: {notes}")
    if preferences:
        parts.append(f"preferences: {json.dumps(preferences)}")
    return "; ".join(parts)
