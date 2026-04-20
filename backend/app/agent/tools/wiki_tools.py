"""Wiki tool definitions for the agent.

Provides search and write access to the personal wiki — a collection of
markdown files organized by topic that capture synthesized knowledge about
the user's life, preferences, and context.

Registered tools:
  - wiki_search        (READ_ONLY)   -- semantic search over wiki pages
  - write_wiki_page    (LOW_STAKES)  -- create or update a wiki page
  - update_wiki_index  (LOW_STAKES)  -- update the wiki index
"""

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools.registry import ActionTier, tool
from app.services import wiki as wiki_service


class WikiSearchInput(BaseModel):
    query: str = Field(..., description="Search query.")
    top_k: int = Field(3, description="Max results (default 3).")


class WriteWikiPageInput(BaseModel):
    page_name: str = Field(
        ...,
        description="Page name (no .md extension). Use lowercase-hyphenated format.",
    )
    content: str = Field(..., description="Full markdown content for the page.")


class WikiIndexEntry(BaseModel):
    title: str
    page_name: str
    summary: str


class UpdateWikiIndexInput(BaseModel):
    entries: list[WikiIndexEntry]


@tool(
    tier=ActionTier.READ_ONLY,
    category="wiki",
    embedding_text=(
        "wiki: wiki_search — search personal wiki, notes, knowledge base, "
        "what do I know about, information about me, my life, preferences, "
        "relationships, history, memories, what I've mentioned before, "
        "context, background, personal details"
    ),
)
async def wiki_search(db: AsyncSession, input: WikiSearchInput) -> dict:
    """Search the personal wiki for synthesized knowledge about the user.

    The wiki contains topic-organized notes compiled from past conversations —
    preferences, relationships, work context, goals, routines, and more.
    Returns the most relevant wiki pages.
    """
    results = await wiki_service.search_wiki(db, query=input.query, top_k=input.top_k)
    return {"results": results, "count": len(results)}


@tool(
    tier=ActionTier.LOW_STAKES,
    category="wiki",
    embedding_text=(
        "wiki: write_wiki_page — write, create, update wiki page, "
        "save knowledge, persist notes, compile information"
    ),
)
async def write_wiki_page(db: AsyncSession, input: WriteWikiPageInput) -> dict:
    """Create or overwrite a wiki page.

    Used during nightly wiki compilation to persist synthesized knowledge
    from conversations.
    """
    wiki_service.write_page(input.page_name, input.content)
    return {"written": True, "page_name": input.page_name}


@tool(
    tier=ActionTier.LOW_STAKES,
    category="wiki",
    embedding_text=(
        "wiki: update_wiki_index — update index, catalog, page listing"
    ),
)
async def update_wiki_index(db: AsyncSession, input: UpdateWikiIndexInput) -> dict:
    """Update the wiki index with current page listings.

    Each entry has a title, page_name, and one-line summary.
    """
    entries = [e.model_dump() for e in input.entries]
    wiki_service.update_index(entries)
    return {"updated": True, "entry_count": len(entries)}
