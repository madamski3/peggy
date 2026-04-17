"""Wiki service — CRUD and semantic search for the personal wiki.

The wiki is a directory of markdown files on disk, with a vector search
index in the wiki_pages table. Markdown files are the source of truth
for content; the database provides embeddings for semantic search.

The nightly review job writes pages via write_page() and updates the
index. The agent reads pages via search_wiki() during chat.
"""

import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import WikiPage
from app.services.embeddings import get_embedding

logger = logging.getLogger(__name__)

_WIKI_DIR = Path(__file__).resolve().parent.parent.parent / "wiki"


def read_index() -> list[dict[str, str]]:
    """Parse wiki/index.md into structured entries.

    Returns list of {page_name, summary} dicts.
    """
    index_path = _WIKI_DIR / "index.md"
    if not index_path.exists():
        return []

    entries = []
    for line in index_path.read_text().splitlines():
        # Match: - [Title](page-name.md) — summary
        m = re.match(r"^- \[(.+?)\]\((.+?)\)\s*[—–-]\s*(.+)$", line)
        if m:
            entries.append({
                "title": m.group(1),
                "page_name": m.group(2).removesuffix(".md"),
                "summary": m.group(3).strip(),
            })
    return entries


def read_page(page_name: str) -> str | None:
    """Read a wiki page's content. Returns None if the page doesn't exist."""
    path = _WIKI_DIR / f"{page_name}.md"
    if not path.exists():
        return None
    return path.read_text()


def write_page(page_name: str, content: str) -> None:
    """Write or overwrite a wiki page."""
    path = _WIKI_DIR / f"{page_name}.md"
    path.write_text(content)
    logger.info("Wiki page written: %s (%d chars)", page_name, len(content))


def update_index(entries: list[dict[str, str]]) -> None:
    """Rewrite wiki/index.md from structured entries.

    Each entry: {title, page_name, summary}.
    """
    lines = ["# Wiki Index", ""]
    for e in entries:
        lines.append(f"- [{e['title']}]({e['page_name']}.md) — {e['summary']}")
    lines.append("")  # trailing newline

    index_path = _WIKI_DIR / "index.md"
    index_path.write_text("\n".join(lines))
    logger.info("Wiki index updated with %d entries", len(entries))


def list_pages() -> list[str]:
    """List all wiki page names (without .md extension).

    Excludes index.md and schema.md.
    """
    excluded = {"index", "schema"}
    return sorted(
        p.stem for p in _WIKI_DIR.glob("*.md")
        if p.stem not in excluded
    )


async def embed_pages(db: AsyncSession) -> int:
    """Vectorize all wiki pages and upsert into the wiki_pages table.

    Returns the number of pages embedded.
    """
    page_names = list_pages()
    if not page_names:
        return 0

    count = 0
    for name in page_names:
        content = read_page(name)
        if not content or not content.strip():
            continue

        embedding = await get_embedding(content[:8000])  # truncate very long pages

        # Upsert into wiki_pages
        result = await db.execute(
            select(WikiPage).where(WikiPage.page_name == name)
        )
        row = result.scalar_one_or_none()

        now = datetime.now(timezone.utc)
        if row:
            row.embedding = embedding
            row.last_compiled_at = now
            row.updated_at = now
        else:
            # Read summary from index if available
            index_entries = read_index()
            summary = next(
                (e["summary"] for e in index_entries if e["page_name"] == name),
                None,
            )
            db.add(WikiPage(
                page_name=name,
                summary=summary,
                embedding=embedding,
                last_compiled_at=now,
            ))
        count += 1

    await db.flush()
    logger.info("Embedded %d wiki pages", count)
    return count


async def search_wiki(
    db: AsyncSession,
    query: str,
    top_k: int = 3,
) -> list[dict]:
    """Semantic search over wiki pages.

    Embeds the query, computes cosine similarity against wiki_pages,
    and returns the top-k matching pages with their content.
    """
    query_embedding = await get_embedding(query)

    result = await db.execute(
        select(WikiPage)
        .where(WikiPage.embedding.isnot(None))
        .order_by(WikiPage.embedding.cosine_distance(query_embedding))
        .limit(top_k)
    )
    pages = result.scalars().all()

    results = []
    for page in pages:
        content = read_page(page.page_name)
        if content:
            results.append({
                "page_name": page.page_name,
                "summary": page.summary or "",
                "content": content[:3000],  # truncate for LLM context
            })

    return results
