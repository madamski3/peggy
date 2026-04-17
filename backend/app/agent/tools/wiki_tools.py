"""Wiki tool definitions for the agent.

Provides search and write access to the personal wiki — a collection of
markdown files organized by topic that capture synthesized knowledge about
the user's life, preferences, and context.

Registered tools:
  - wiki_search        (READ_ONLY)   -- semantic search over wiki pages
  - write_wiki_page    (LOW_STAKES)  -- create or update a wiki page
  - update_wiki_index  (LOW_STAKES)  -- update the wiki index
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools.registry import ActionTier, ToolDefinition, register_tool
from app.services import wiki as wiki_service


# ── Handlers ──────────────────────────────────────────────────────


async def handle_wiki_search(db: AsyncSession, **kwargs: Any) -> dict:
    results = await wiki_service.search_wiki(
        db, query=kwargs["query"], top_k=kwargs.get("top_k", 3),
    )
    return {"results": results, "count": len(results)}


async def handle_write_wiki_page(db: AsyncSession, **kwargs: Any) -> dict:
    wiki_service.write_page(kwargs["page_name"], kwargs["content"])
    return {"written": True, "page_name": kwargs["page_name"]}


async def handle_update_wiki_index(db: AsyncSession, **kwargs: Any) -> dict:
    wiki_service.update_index(kwargs["entries"])
    return {"updated": True, "entry_count": len(kwargs["entries"])}


# ── Tool Definitions ─────────────────────────────────────────────

register_tool(ToolDefinition(
    name="wiki_search",
    description=(
        "Search the personal wiki for synthesized knowledge about the user. "
        "The wiki contains topic-organized notes compiled from past conversations — "
        "preferences, relationships, work context, goals, routines, and more. "
        "Returns the most relevant wiki pages."
    ),
    embedding_text=(
        "wiki: wiki_search — search personal wiki, notes, knowledge base, "
        "what do I know about, information about me, my life, preferences, "
        "relationships, history, memories, what I've mentioned before, "
        "context, background, personal details"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query."},
            "top_k": {"type": "integer", "description": "Max results (default 3)."},
        },
        "required": ["query"],
    },
    tier=ActionTier.READ_ONLY,
    handler=handle_wiki_search,
    category="wiki",
))

register_tool(ToolDefinition(
    name="write_wiki_page",
    description=(
        "Create or overwrite a wiki page. Used during nightly wiki compilation "
        "to persist synthesized knowledge from conversations."
    ),
    embedding_text=(
        "wiki: write_wiki_page — write, create, update wiki page, "
        "save knowledge, persist notes, compile information"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "page_name": {"type": "string", "description": "Page name (no .md extension). Use lowercase-hyphenated format."},
            "content": {"type": "string", "description": "Full markdown content for the page."},
        },
        "required": ["page_name", "content"],
    },
    tier=ActionTier.LOW_STAKES,
    handler=handle_write_wiki_page,
    category="wiki",
))

register_tool(ToolDefinition(
    name="update_wiki_index",
    description=(
        "Update the wiki index with current page listings. Each entry has a "
        "title, page_name, and one-line summary."
    ),
    embedding_text=(
        "wiki: update_wiki_index — update index, catalog, page listing"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "entries": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "page_name": {"type": "string"},
                        "summary": {"type": "string"},
                    },
                    "required": ["title", "page_name", "summary"],
                },
            },
        },
        "required": ["entries"],
    },
    tier=ActionTier.LOW_STAKES,
    handler=handle_update_wiki_index,
    category="wiki",
))
