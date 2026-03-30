"""List service layer -- CRUD operations for List and ListItem models.

Lists are named collections of items (grocery list, packing list, etc.).
Each list has a type and status, and contains ordered ListItems.

Called by the agent tools (list_tools.py).
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.tables import List, ListItem
from app.services.serialization import model_to_dict


async def get_lists(db: AsyncSession, filters: dict[str, Any] | None = None) -> list[dict]:
    """Query lists with optional filters.

    Supported filters:
        - type: str
        - status: str
    """
    filters = filters or {}
    query = select(List).options(selectinload(List.items))

    if "type" in filters:
        query = query.where(List.type == filters["type"])
    if "status" in filters:
        query = query.where(List.status == filters["status"])

    query = query.order_by(List.created_at.desc())
    result = await db.execute(query)
    lists = result.scalars().unique().all()

    output = []
    for lst in lists:
        d = model_to_dict(lst)
        d["item_count"] = len(lst.items) if lst.items else 0
        d["pending_count"] = sum(1 for i in (lst.items or []) if i.status == "pending")
        output.append(d)
    return output


async def get_list_items(
    db: AsyncSession, list_id: str | uuid.UUID, filters: dict[str, Any] | None = None
) -> list[dict]:
    """Get items for a specific list.

    Supported filters:
        - status: str
    """
    filters = filters or {}
    query = select(ListItem).where(ListItem.list_id == _parse_uuid(list_id))

    if "status" in filters:
        query = query.where(ListItem.status == filters["status"])

    query = query.order_by(ListItem.position.asc().nullslast(), ListItem.added_at.asc())
    result = await db.execute(query)
    return [model_to_dict(item) for item in result.scalars().all()]


async def create_list(
    db: AsyncSession, name: str, type: str = "custom", description: str | None = None
) -> dict:
    """Create a new list."""
    lst = List(name=name, type=type, description=description, status="active")
    db.add(lst)
    await db.flush()
    return model_to_dict(lst)


async def add_list_item(
    db: AsyncSession,
    list_id: str | uuid.UUID,
    name: str,
    notes: str | None = None,
) -> dict:
    """Add an item to a list."""
    # Get current max position
    result = await db.execute(
        select(ListItem.position)
        .where(ListItem.list_id == _parse_uuid(list_id))
        .order_by(ListItem.position.desc().nullslast())
        .limit(1)
    )
    max_pos = result.scalar_one_or_none()
    next_pos = (max_pos or 0) + 1

    item = ListItem(
        list_id=_parse_uuid(list_id),
        name=name,
        notes=notes,
        position=next_pos,
        status="pending",
        added_by="assistant",
    )
    db.add(item)
    await db.flush()
    return model_to_dict(item)


async def complete_list_item(db: AsyncSession, item_id: str | uuid.UUID) -> dict | None:
    """Mark a list item as done."""
    result = await db.execute(select(ListItem).where(ListItem.id == _parse_uuid(item_id)))
    item = result.scalar_one_or_none()
    if item is None:
        return None

    item.status = "completed"
    item.completed_at = datetime.now(timezone.utc)
    await db.flush()
    return model_to_dict(item)


async def bulk_complete_list_items(
    db: AsyncSession,
    list_id: str | uuid.UUID,
    exceptions: list[str | uuid.UUID] | None = None,
) -> int:
    """Mark all pending items on a list as completed, except those in exceptions.

    Returns the count of items completed.
    """
    exception_ids = {_parse_uuid(e) for e in (exceptions or [])}

    result = await db.execute(
        select(ListItem).where(
            ListItem.list_id == _parse_uuid(list_id),
            ListItem.status == "pending",
        )
    )
    items = list(result.scalars().all())

    count = 0
    now = datetime.now(timezone.utc)
    for item in items:
        if item.id not in exception_ids:
            item.status = "completed"
            item.completed_at = now
            count += 1

    await db.flush()
    return count


# ── Internal helpers ──────────────────────────────────────────────


def _parse_uuid(value: str | uuid.UUID | None) -> uuid.UUID | None:
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(value)
