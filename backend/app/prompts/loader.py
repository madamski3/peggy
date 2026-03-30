"""Prompt template loader.

Loads YAML prompt files and renders them with Jinja2 template variables.
The orchestrator calls render_prompt() with the context dict assembled
by context.py, producing the final system prompt string that gets sent
to Claude.

Prompt versions are stored as YAML files (e.g. system_v1.yaml) with a
Jinja2 template field. The active version is controlled by the
system_prompt_version config setting.
"""
from pathlib import Path

import yaml
from jinja2 import Template

PROMPTS_DIR = Path(__file__).parent


def load_prompt(version: str = "v1") -> dict:
    """Load a prompt template by version."""
    path = PROMPTS_DIR / f"system_{version}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path}")
    with open(path) as f:
        return yaml.safe_load(f)


def render_prompt(version: str = "v1", context: dict | None = None) -> str:
    """Load and render a prompt template with context variables.

    Args:
        version: Prompt version to load (e.g., "v1")
        context: Dict of template variables to inject

    Returns:
        Rendered prompt string
    """
    prompt_data = load_prompt(version)
    template = Template(prompt_data["template"])
    return template.render(**(context or {}))
