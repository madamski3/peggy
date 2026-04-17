"""Vector-search tool selection.

Replaces category-based tool filtering with per-tool semantic search.
At startup, embeds all registered tools using their embedding_text
(or a generated fallback). At query time, embeds the user message
(with conversation context) and returns the most relevant tools by
cosine similarity.

Embeddings are cached to disk so they survive restarts without
re-calling the OpenAI API. The cache is keyed by a hash of each
tool's embedding text — if a tool's text changes, only that tool's
embedding is recomputed.

The _GENERAL_TOOLS set is always included as a floor so the main LLM
has basic read capabilities regardless of similarity scores.
"""

import hashlib
import json
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path

from app.agent.tools.registry import TOOL_REGISTRY, ToolDefinition, _GENERAL_TOOLS
from app.globals import TOOL_SELECTOR_THRESHOLD, TOOL_SELECTOR_TOP_K
from app.services.embeddings import get_embedding, get_embeddings_batch

logger = logging.getLogger(__name__)

_CACHE_PATH = Path(__file__).resolve().parent.parent.parent / "tool_embedding_cache.json"


@dataclass
class ToolSelectionResult:
    """Result of vector-search tool selection."""

    selected: set[str] = field(default_factory=set)
    scores: dict[str, float] = field(default_factory=dict)


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


def _text_hash(text: str) -> str:
    """Stable hash of embedding text for cache keying."""
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _load_cache() -> dict[str, dict]:
    """Load the on-disk embedding cache. Returns {tool_name: {hash, vector}}."""
    if not _CACHE_PATH.exists():
        return {}
    try:
        return json.loads(_CACHE_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        logger.warning("Tool embedding cache corrupted, will recompute")
        return {}


def _save_cache(cache: dict[str, dict]) -> None:
    """Persist the embedding cache to disk."""
    try:
        _CACHE_PATH.write_text(json.dumps(cache))
    except OSError:
        logger.warning("Failed to write tool embedding cache")


async def initialize() -> None:
    """Pre-compute and cache normalized embeddings for all registered tools.

    Loads cached embeddings from disk when available. Only recomputes
    embeddings for tools whose embedding_text has changed.
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

    # Build current text + hash for each tool
    tool_texts = {t.name: _build_embedding_text(t) for t in tools}
    tool_hashes = {name: _text_hash(text) for name, text in tool_texts.items()}

    # Load disk cache and identify which tools need (re-)embedding
    cache = _load_cache()
    needs_embedding: list[str] = []
    for name, h in tool_hashes.items():
        cached = cache.get(name)
        if cached and cached.get("hash") == h and cached.get("vector"):
            _tool_vectors[name] = _normalize(cached["vector"])
        else:
            needs_embedding.append(name)

    if needs_embedding:
        texts = [tool_texts[n] for n in needs_embedding]
        logger.info("Tool selector: embedding %d tool(s): %s", len(needs_embedding), needs_embedding)
        embeddings = await get_embeddings_batch(texts)
        for name, emb in zip(needs_embedding, embeddings):
            normed = _normalize(emb)
            _tool_vectors[name] = normed
            cache[name] = {"hash": tool_hashes[name], "vector": emb}
        _save_cache(cache)
    else:
        logger.info("Tool selector: all %d embeddings loaded from cache", len(tools))

    _initialized = True
    logger.info("Tool selector: initialized with %d tool embeddings", len(_tool_vectors))


async def select_tools(
    user_message: str,
    conversation_history: list[dict] | None,
    top_k: int = TOOL_SELECTOR_TOP_K,
    threshold: float = TOOL_SELECTOR_THRESHOLD,
) -> ToolSelectionResult:
    """Select relevant tools for a turn via vector similarity.

    Args:
        user_message: The current user message.
        conversation_history: Recent session history (list of turn dicts).
        top_k: Maximum number of tools to return (before adding general tools).
        threshold: Minimum cosine similarity score to include a tool.

    Returns:
        ToolSelectionResult with selected tool names and all similarity scores.
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
        name: round(sum(a * b for a, b in zip(query_vec, vec)), 4)
        for name, vec in _tool_vectors.items()
    }

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    selected = {name for name, score in ranked[:top_k] if score >= threshold}

    # Always include baseline read tools
    selected |= _GENERAL_TOOLS

    return ToolSelectionResult(selected=selected, scores=scores)
