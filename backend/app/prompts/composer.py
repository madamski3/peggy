"""Dynamic system prompt composer.

Assembles the system prompt from granular component files based on:
  - Always-on components (core identity, context, tool guidance)
  - Channel-based components (proactive notification)
  - Planner-selected components (daily planning, schedule overview)
  - Derived components (response format variant)

Each component lives in prompts/components/*.txt and is rendered with
Jinja2 for variable interpolation ({{ user_name }}, {{ strategy }}, etc.).
"""

import logging
from pathlib import Path

from jinja2 import Template

logger = logging.getLogger(__name__)

COMPONENTS_DIR = Path(__file__).parent / "components"

# Fixed ordering for prompt assembly
_COMPOSITION_ORDER = [
    "core_identity",
    "current_context",
    "tool_guidance",
    "proactive_notification",
    "daily_planning",
    "schedule_overview",
    "strategy",
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


def _load_component(name: str) -> str:
    """Load a component file by name."""
    path = COMPONENTS_DIR / f"{name}.txt"
    return path.read_text()


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

    # Planner-selected (validated against known set)
    for name in planner_components:
        if name in SELECTABLE_COMPONENTS:
            active.add(name)
        else:
            logger.warning("Planner selected unknown component: %s", name)

    # Strategy (only if non-empty)
    if context.get("strategy"):
        active.add("strategy")

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
) -> str:
    """Compose the system prompt from relevant components.

    Args:
        context: Template variables (current_datetime, timezone, user_name,
                 strategy, etc.)
        planner_components: Component names selected by the planner LLM.
        channel: Interaction channel — "chat" or "proactive".

    Returns:
        The fully rendered system prompt string.
    """
    components = _select_components(context, planner_components, channel)
    logger.info("Prompt components: %s", components)

    sections = []
    for name in components:
        raw = _load_component(name)
        rendered = Template(raw).render(**context)
        sections.append(rendered)

    return "\n\n".join(sections)
