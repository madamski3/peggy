"""Vector-search tool selection.

Replaces category-based tool filtering with per-tool semantic search.
At startup, embeds all registered tools using their embedding_text
(or a generated fallback). At query time, embeds the user message
(with conversation context) and returns the most relevant tools by
cosine similarity.

The _GENERAL_TOOLS set is always included as a floor so the main LLM
has basic read capabilities regardless of similarity scores.
"""

import logging
import math

from app.agent.tools.registry import TOOL_REGISTRY, ToolDefinition, _GENERAL_TOOLS
from app.services.embeddings import get_embedding, get_embeddings_batch

logger = logging.getLogger(__name__)

# Module-level cache: tool name → normalized embedding vector
_tool_vectors: dict[str, list[float]] = {}
_initialized = False


def _normalize(vec: list[float]) -> list[float]:
    """L2-normalize a vector so dot product == cosine similarity."""
    norm = math.sqrt(sum(x * x for x in vec))
    return [x / norm for x in vec] if norm > 0 else vec


def _build_embedding_text(tool: ToolDefinition) -> str:
    """Build the text to embed for a tool.

    Uses the hand-written embedding_text if set, otherwise generates
    a reasonable fallback from the tool's metadata.
    """
    if tool.embedding_text:
        return tool.embedding_text
    return f"{tool.category}: {tool.name} — {tool.description}"


async def initialize() -> None:
    """Pre-compute and cache normalized embeddings for all registered tools.

    Safe to call multiple times — skips if already initialized.
    """
    global _initialized, _tool_vectors
    if _initialized:
        return

    tools = list(TOOL_REGISTRY.values())
    if not tools:
        logger.warning("Tool selector: no tools registered, skipping initialization")
        _initialized = True
        return

    texts = [_build_embedding_text(t) for t in tools]
    names = [t.name for t in tools]

    logger.info(f"Tool selector: embedding {len(tools)} tools...")
    embeddings = await get_embeddings_batch(texts)

    _tool_vectors = {
        name: _normalize(emb)
        for name, emb in zip(names, embeddings)
    }
    _initialized = True
    logger.info(f"Tool selector: initialized with {len(_tool_vectors)} tool embeddings")


async def select_tools(
    user_message: str,
    conversation_history: list[dict] | None,
    top_k: int = 12,
    threshold: float = 0.40,
) -> set[str]:
    """Select relevant tools for a turn via vector similarity.

    Args:
        user_message: The current user message.
        conversation_history: Recent session history (list of turn dicts).
        top_k: Maximum number of tools to return (before adding general tools).
        threshold: Minimum cosine similarity score to include a tool.

    Returns:
        Set of tool names to include in the LLM call.
    """
    if not _initialized:
        await initialize()

    # Build query: recent user messages + current message for context
    query_parts = []
    if conversation_history:
        for turn in conversation_history[-2:]:
            if msg := turn.get("user_message"):
                query_parts.append(msg)
    query_parts.append(user_message)
    query_text = "\n".join(query_parts)

    query_vec = _normalize(await get_embedding(query_text))

    # Score all tools by cosine similarity (dot product of normalized vectors)
    scores = {
        name: sum(a * b for a, b in zip(query_vec, vec))
        for name, vec in _tool_vectors.items()
    }

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    selected = {name for name, score in ranked[:top_k] if score >= threshold}

    # Always include baseline read tools
    selected |= _GENERAL_TOOLS

    return selected
