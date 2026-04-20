"""List tool definitions for the agent.

Manages named lists (grocery, packing, custom) and their items.

Registered tools:
  - get_lists              (READ_ONLY)  -- query lists, optionally filtered by type/status
  - get_list_items         (READ_ONLY)  -- get items for a specific list
  - create_list            (LOW_STAKES) -- create a new named list
  - add_list_item          (LOW_STAKES) -- add an item to a list
  - complete_list_item     (LOW_STAKES) -- mark a single item done
  - bulk_complete_list_items (LOW_STAKES) -- mark all items done, with optional exceptions
"""

from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools.registry import ActionTier, tool
from app.services import lists as list_service


class ListFilters(BaseModel):
    type: str | None = None
    status: Literal["active", "archived"] | None = None


class GetListsInput(BaseModel):
    filters: ListFilters | None = None


class ListItemFilters(BaseModel):
    status: Literal["pending", "completed"] | None = None


class GetListItemsInput(BaseModel):
    list_id: str
    filters: ListItemFilters | None = None


class CreateListInput(BaseModel):
    name: str
    type: str = "custom"
    description: str | None = None


class AddListItemInput(BaseModel):
    list_id: str
    name: str
    notes: str | None = None


class CompleteListItemInput(BaseModel):
    item_id: str


class BulkCompleteListItemsInput(BaseModel):
    list_id: str
    exceptions: list[str] | None = Field(
        None, description="Item UUIDs to exclude from completion."
    )


@tool(
    tier=ActionTier.READ_ONLY,
    category="list",
    embedding_text=(
        "list: get_lists — show, view my lists, grocery list, packing list, "
        "shopping list. What lists do I have? Show my grocery list."
    ),
)
async def get_lists(db: AsyncSession, input: GetListsInput) -> dict:
    """Get lists, optionally filtered by type or status."""
    filters = input.filters.model_dump(exclude_none=True) if input.filters else {}
    results = await list_service.get_lists(db, filters)
    return {"lists": results, "count": len(results)}


@tool(
    tier=ActionTier.READ_ONLY,
    category="list",
    embedding_text=(
        "list: get_list_items — show items on a list, what's on my grocery list, "
        "view list contents. What do I need to buy?"
    ),
)
async def get_list_items(db: AsyncSession, input: GetListItemsInput) -> dict:
    """Get items from a specific list."""
    filters = input.filters.model_dump(exclude_none=True) if input.filters else {}
    results = await list_service.get_list_items(db, input.list_id, filters)
    return {"items": results, "count": len(results)}


@tool(
    tier=ActionTier.LOW_STAKES,
    category="list",
    embedding_text=(
        "list: create_list — create, start a new list, grocery list, packing list, "
        "shopping list. Make me a grocery list. Start a packing list for my trip."
    ),
)
async def create_list(db: AsyncSession, input: CreateListInput) -> dict:
    """Create a new list."""
    return await list_service.create_list(
        db, name=input.name, type=input.type, description=input.description,
    )


@tool(
    tier=ActionTier.LOW_STAKES,
    category="list",
    embedding_text=(
        "list: add_list_item — add item to a list, put milk on the grocery list, "
        "add something to my shopping list. Don't forget to pack sunscreen."
    ),
)
async def add_list_item(db: AsyncSession, input: AddListItemInput) -> dict:
    """Add an item to a list."""
    return await list_service.add_list_item(
        db, list_id=input.list_id, name=input.name, notes=input.notes,
    )


@tool(
    tier=ActionTier.LOW_STAKES,
    category="list",
    embedding_text=(
        "list: complete_list_item — check off, mark done, complete an item on a list. "
        "I got the milk. Cross that off my list."
    ),
)
async def complete_list_item(db: AsyncSession, input: CompleteListItemInput) -> dict:
    """Mark a list item as done."""
    result = await list_service.complete_list_item(db, input.item_id)
    if result is None:
        return {"error": "List item not found"}
    return result


@tool(
    tier=ActionTier.LOW_STAKES,
    category="list",
    embedding_text=(
        "list: bulk_complete_list_items — complete all items, clear the list, "
        "mark everything as done. I got everything on my grocery list."
    ),
)
async def bulk_complete_list_items(db: AsyncSession, input: BulkCompleteListItemsInput) -> dict:
    """Mark all pending items on a list as completed."""
    count = await list_service.bulk_complete_list_items(
        db, list_id=input.list_id, exceptions=input.exceptions,
    )
    return {"completed_count": count}
