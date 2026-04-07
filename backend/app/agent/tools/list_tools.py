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

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools.registry import ActionTier, ToolDefinition, register_tool
from app.services import lists as list_service


# ── Handlers ──────────────────────────────────────────────────────


async def handle_get_lists(db: AsyncSession, **kwargs: Any) -> dict:
    filters = kwargs.get("filters", {})
    results = await list_service.get_lists(db, filters)
    return {"lists": results, "count": len(results)}


async def handle_get_list_items(db: AsyncSession, **kwargs: Any) -> dict:
    filters = kwargs.get("filters", {})
    results = await list_service.get_list_items(db, kwargs["list_id"], filters)
    return {"items": results, "count": len(results)}


async def handle_create_list(db: AsyncSession, **kwargs: Any) -> dict:
    return await list_service.create_list(
        db,
        name=kwargs["name"],
        type=kwargs.get("type", "custom"),
        description=kwargs.get("description"),
    )


async def handle_add_list_item(db: AsyncSession, **kwargs: Any) -> dict:
    return await list_service.add_list_item(
        db,
        list_id=kwargs["list_id"],
        name=kwargs["name"],
        notes=kwargs.get("notes"),
    )


async def handle_complete_list_item(db: AsyncSession, **kwargs: Any) -> dict:
    result = await list_service.complete_list_item(db, kwargs["item_id"])
    if result is None:
        return {"error": "List item not found"}
    return result


async def handle_bulk_complete_list_items(db: AsyncSession, **kwargs: Any) -> dict:
    count = await list_service.bulk_complete_list_items(
        db,
        list_id=kwargs["list_id"],
        exceptions=kwargs.get("exceptions"),
    )
    return {"completed_count": count}


# ── Tool Definitions ─────────────────────────────────────────────

register_tool(ToolDefinition(
    name="get_lists",
    description="Get lists, optionally filtered by type or status.",
    embedding_text=(
        "list: get_lists — show, view my lists, grocery list, packing list, "
        "shopping list. What lists do I have? Show my grocery list."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "filters": {
                "type": "object",
                "properties": {
                    "type": {"type": "string"},
                    "status": {"type": "string", "enum": ["active", "archived"]},
                },
            },
        },
    },
    tier=ActionTier.READ_ONLY,
    handler=handle_get_lists,
    category="list",
))

register_tool(ToolDefinition(
    name="get_list_items",
    description="Get items from a specific list.",
    embedding_text=(
        "list: get_list_items — show items on a list, what's on my grocery list, "
        "view list contents. What do I need to buy?"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "list_id": {"type": "string"},
            "filters": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": ["pending", "completed"]},
                },
            },
        },
        "required": ["list_id"],
    },
    tier=ActionTier.READ_ONLY,
    handler=handle_get_list_items,
    category="list",
))

register_tool(ToolDefinition(
    name="create_list",
    description="Create a new list.",
    embedding_text=(
        "list: create_list — create, start a new list, grocery list, packing list, "
        "shopping list. Make me a grocery list. Start a packing list for my trip."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "type": {"type": "string"},
            "description": {"type": "string"},
        },
        "required": ["name"],
    },
    tier=ActionTier.LOW_STAKES,
    handler=handle_create_list,
    category="list",
))

register_tool(ToolDefinition(
    name="add_list_item",
    description="Add an item to a list.",
    embedding_text=(
        "list: add_list_item — add item to a list, put milk on the grocery list, "
        "add something to my shopping list. Don't forget to pack sunscreen."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "list_id": {"type": "string"},
            "name": {"type": "string"},
            "notes": {"type": "string"},
        },
        "required": ["list_id", "name"],
    },
    tier=ActionTier.LOW_STAKES,
    handler=handle_add_list_item,
    category="list",
))

register_tool(ToolDefinition(
    name="complete_list_item",
    description="Mark a list item as done.",
    embedding_text=(
        "list: complete_list_item — check off, mark done, complete an item on a list. "
        "I got the milk. Cross that off my list."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "item_id": {"type": "string"},
        },
        "required": ["item_id"],
    },
    tier=ActionTier.LOW_STAKES,
    handler=handle_complete_list_item,
    category="list",
))

register_tool(ToolDefinition(
    name="bulk_complete_list_items",
    description="Mark all pending items on a list as completed.",
    embedding_text=(
        "list: bulk_complete_list_items — complete all items, clear the list, "
        "mark everything as done. I got everything on my grocery list."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "list_id": {"type": "string"},
            "exceptions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Item UUIDs to exclude from completion.",
            },
        },
        "required": ["list_id"],
    },
    tier=ActionTier.LOW_STAKES,
    handler=handle_bulk_complete_list_items,
    category="list",
))
