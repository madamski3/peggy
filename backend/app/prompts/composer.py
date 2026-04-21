"""Dynamic system prompt composer.

Assembles the system prompt from granular component files based on:
  - Always-on components (core identity, context, tool guidance)
  - Channel-based components (proactive notification)
  - Planner-selected components (daily planning, schedule overview)
  - Derived components (response format variant)

Each component lives in prompts/components/*.txt and is rendered with
Jinja2 for variable interpolation ({{ user_name }}, {{ plan }}, etc.).

Component versioning: every active component is content-hashed (SHA-256 of
its raw pre-Jinja text) and returned alongside the rendered prompt so the
orchestrator can tag the llm_calls row with an array of component ids.
compose_and_persist_prompt upserts those versions into prompt_components
so the hash-to-text mapping is browsable.
"""

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Template
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import PromptComponent
from app.observability.langfuse_client import get_langfuse

logger = logging.getLogger(__name__)

COMPONENTS_DIR = Path(__file__).parent / "components"

# Fixed ordering for prompt assembly
_COMPOSITION_ORDER = [
    "core_identity",
    "current_context",
    "tool_guidance",
    "proactive_notification",
    "wiki_review",
    "daily_planning",
    "schedule_overview",
    "plan",
    "response_format_planning",
    "response_format_default",
]

# Valid planner-selectable component names
SELECTABLE_COMPONENTS = {"daily_planning", "schedule_overview"}

# Response format mapping: if any of these components are active,
# use the specialized response format instead of the default
_RESPONSE_FORMAT_OVERRIDES = {
    "daily_planning": "response_format_planning",
}


@dataclass(frozen=True)
class ActiveComponent:
    """A single prompt component active for one LLM call.

    `id` is the hex SHA-256 of `raw_text` — hashing the pre-Jinja template
    keeps the hash stable across requests where only context vars change.
    """

    name: str
    id: str
    raw_text: str
    type: str = "component"


@dataclass(frozen=True)
class ComposedPrompt:
    """Result of composing a system prompt from components."""

    text: str
    components: list[ActiveComponent]


def _load_component(name: str) -> str:
    """Load a component file by name."""
    path = COMPONENTS_DIR / f"{name}.txt"
    return path.read_text()


def _hash_text(text: str) -> str:
    """Hex SHA-256 of a string."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _select_components(
    context: dict,
    planner_components: list[str],
    channel: str,
) -> list[str]:
    """Determine which components to include, in composition order."""
    active = set()

    # Always included
    active.update(["core_identity", "current_context", "tool_guidance"])

    # Channel-based
    if channel == "proactive":
        active.add("proactive_notification")
    elif channel == "wiki_review":
        active.add("wiki_review")

    # Planner-selected (validated against known set)
    for name in planner_components:
        if name in SELECTABLE_COMPONENTS:
            active.add(name)
        else:
            logger.warning("Planner selected unknown component: %s", name)

    # Plan (only if the planner produced goal or steps)
    plan = context.get("plan") or {}
    if plan.get("goal") or plan.get("steps"):
        active.add("plan")

    # Response format — use override if a matching component is active,
    # otherwise use default
    response_format = "response_format_default"
    for component, override in _RESPONSE_FORMAT_OVERRIDES.items():
        if component in active:
            response_format = override
            break
    active.add(response_format)

    # Return in composition order
    return [name for name in _COMPOSITION_ORDER if name in active]


def compose_prompt(
    context: dict,
    planner_components: list[str],
    channel: str = "chat",
) -> ComposedPrompt:
    """Compose the system prompt from relevant components.

    Pure — no I/O. Call `compose_and_persist_prompt` instead from production
    code paths that need the component versions persisted.

    Args:
        context: Template variables (current_datetime, timezone, user_name,
                 plan, etc.)
        planner_components: Component names selected by the planner LLM.
        channel: Interaction channel — "chat" or "proactive".

    Returns:
        ComposedPrompt with the rendered text and the ordered list of
        ActiveComponent records that made it up.
    """
    names = _select_components(context, planner_components, channel)
    logger.info("Prompt components: %s", names)

    sections: list[str] = []
    components: list[ActiveComponent] = []
    for name in names:
        raw = _load_component(name)
        rendered = Template(raw).render(**context)
        sections.append(rendered)
        components.append(
            ActiveComponent(
                name=name,
                id=_hash_text(raw),
                raw_text=raw,
                type="component",
            )
        )

    return ComposedPrompt(
        text="\n\n".join(sections),
        components=components,
    )


async def upsert_prompt_components(
    db: AsyncSession,
    components: list[ActiveComponent],
) -> None:
    """Insert any new component versions; no-op on id conflicts.

    Safe to call redundantly — ON CONFLICT DO NOTHING means repeated hits
    with the same id are cheap and idempotent.
    """
    if not components:
        return
    rows = [
        {
            "id": c.id,
            "name": c.name,
            "type": c.type,
            "prompt_text": c.raw_text,
        }
        for c in components
    ]
    stmt = pg_insert(PromptComponent).values(rows)
    stmt = stmt.on_conflict_do_nothing(index_elements=["id"])
    await db.execute(stmt)

    _mirror_components_to_langfuse(components)


def _mirror_components_to_langfuse(components: list[ActiveComponent]) -> None:
    """Push each component to Langfuse Prompt Management as a labeled version.

    Langfuse dedupes on (name, prompt_text) so repeat calls with unchanged text
    are no-ops. Tagging with the content hash lets us correlate Langfuse prompt
    versions with our `prompt_components` table.
    """
    lf = get_langfuse()
    if lf is None:
        return
    for c in components:
        try:
            lf.create_prompt(
                name=c.name,
                prompt=c.raw_text,
                labels=["production"],
                tags=[c.id[:12], c.type],
            )
        except Exception as e:
            logger.warning("Langfuse create_prompt failed for %s: %s", c.name, e)


async def compose_and_persist_prompt(
    db: AsyncSession,
    context: dict,
    planner_components: list[str],
    channel: str = "chat",
) -> ComposedPrompt:
    """Compose the system prompt AND persist its component versions.

    This is what production callers should use. `compose_prompt` is kept
    pure for unit tests and for code paths that want to inspect a prompt
    without writing anything.
    """
    composed = compose_prompt(context, planner_components, channel)
    await upsert_prompt_components(db, composed.components)
    return composed
