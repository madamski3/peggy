"""Langfuse observability client and tracing helpers.

All three langfuse_* settings must be populated for tracing to be active;
otherwise every helper here becomes a no-op so the backend keeps running
even if Langfuse is down or disabled.
"""

import logging
from contextlib import contextmanager
from typing import Any

from langfuse import Langfuse

from app.config import settings

logger = logging.getLogger(__name__)

_client: Langfuse | None = None
_initialized: bool = False


def get_langfuse() -> Langfuse | None:
    """Return the process-wide Langfuse client, or None if tracing is off."""
    global _client, _initialized
    if _initialized:
        return _client
    _initialized = True
    if not (settings.langfuse_host and settings.langfuse_public_key and settings.langfuse_secret_key):
        logger.info("Langfuse tracing disabled (credentials not set)")
        return None
    try:
        _client = Langfuse(
            host=settings.langfuse_host,
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
        )
        logger.info("Langfuse tracing enabled: %s", settings.langfuse_host)
    except Exception as e:
        logger.warning("Langfuse init failed, tracing disabled: %s", e)
        _client = None
    return _client


@contextmanager
def trace_observation(
    name: str,
    as_type: str = "span",
    **kwargs: Any,
):
    """Open a Langfuse observation (span/generation/tool) around a block.

    Yields the LangfuseSpan/Generation/Tool if tracing is active, else None.
    Callers should guard `.update(...)` calls with `if span is not None`.
    """
    lf = get_langfuse()
    if lf is None:
        yield None
        return
    try:
        with lf.start_as_current_observation(name=name, as_type=as_type, **kwargs) as span:
            yield span
    except Exception as e:
        logger.warning("Langfuse %s '%s' failed: %s", as_type, name, e)
        yield None


def set_trace_attributes(
    *,
    session_id: str | None = None,
    user_id: str | None = None,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Attach trace-level attributes to the currently active root span.

    Must be called from inside a `trace_observation(...)` context. No-op if
    Langfuse is disabled or no span is active.
    """
    from opentelemetry import trace as otel_trace

    span = otel_trace.get_current_span()
    if span is None or not span.is_recording():
        return
    if session_id is not None:
        span.set_attribute("session.id", session_id)
    if user_id is not None:
        span.set_attribute("user.id", user_id)
    if tags:
        span.set_attribute("langfuse.trace.tags", tags)
    if metadata:
        import json
        span.set_attribute("langfuse.trace.metadata", json.dumps(metadata, default=str))


def anthropic_usage_to_langfuse(usage: Any) -> dict[str, int]:
    """Convert an Anthropic response.usage into Langfuse's usage_details dict.

    Returns cache read/write alongside input/output so cache-hit rate is
    visible in the Langfuse UI.
    """
    return {
        "input": getattr(usage, "input_tokens", 0) or 0,
        "output": getattr(usage, "output_tokens", 0) or 0,
        "cache_read_input": getattr(usage, "cache_read_input_tokens", 0) or 0,
        "cache_creation_input": getattr(usage, "cache_creation_input_tokens", 0) or 0,
    }
