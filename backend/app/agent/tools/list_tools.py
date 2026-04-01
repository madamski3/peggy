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
    description="Get all lists or a filtered subset. Use to find a specific list like a grocery or shopping list.",
    input_schema={
        "type": "object",
        "properties": {
            "filters": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "description": "Filter by list type (grocery, shopping, custom, etc.)."},
                    "status": {"type": "string", "description": "Filter by status (active, archived)."},
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
    description="Get items from a specific list, optionally filtered by status.",
    input_schema={
        "type": "object",
        "properties": {
            "list_id": {"type": "string", "description": "UUID of the list."},
            "filters": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "description": "Filter by item status (pending, completed)."},
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
    description="Create a new list (e.g., grocery list, packing list, project checklist).",
    input_schema={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Name of the list."},
            "type": {"type": "string", "description": "Type of list (grocery, shopping, packing, custom). Default: custom."},
            "description": {"type": "string", "description": "Optional description."},
        },
        "required": ["name"],
    },
    tier=ActionTier.LOW_STAKES,
    handler=handle_create_list,
    category="list",
))

register_tool(ToolDefinition(
    name="add_list_item",
    description="Add an item to an existing list.",
    input_schema={
        "type": "object",
        "properties": {
            "list_id": {"type": "string", "description": "UUID of the list to add to."},
            "name": {"type": "string", "description": "Name of the item."},
            "notes": {"type": "string", "description": "Optional notes."},
        },
        "required": ["list_id", "name"],
    },
    tier=ActionTier.LOW_STAKES,
    handler=handle_add_list_item,
    category="list",
))

register_tool(ToolDefinition(
    name="complete_list_item",
    description="Mark a single list item as done.",
    input_schema={
        "type": "object",
        "properties": {
            "item_id": {"type": "string", "description": "UUID of the list item to complete."},
        },
        "required": ["item_id"],
    },
    tier=ActionTier.LOW_STAKES,
    handler=handle_complete_list_item,
    category="list",
))

register_tool(ToolDefinition(
    name="bulk_complete_list_items",
    description="Mark all pending items on a list as completed, optionally excluding specific items.",
    input_schema={
        "type": "object",
        "properties": {
            "list_id": {"type": "string", "description": "UUID of the list."},
            "exceptions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "UUIDs of items to NOT complete (keep pending).",
            },
        },
        "required": ["list_id"],
    },
    tier=ActionTier.LOW_STAKES,
    handler=handle_bulk_complete_list_items,
    category="list",
))
