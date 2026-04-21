"""Meta-tools the agent uses to coordinate with the harness.

Registered tools:
  - advance_to_step (READ_ONLY) -- signals that the agent is starting work
    on a planner step (or going off-plan). The orchestrator intercepts the
    call to emit a structured status event; the handler itself is a no-op
    that echoes acknowledgement so the agent can continue reasoning.
"""

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools.registry import ActionTier, tool


class AdvanceToStepInput(BaseModel):
    step_index: int | None = Field(
        default=None,
        description=(
            "1-based index into the plan's steps. Use null when you're doing "
            "something outside the plan (and provide `note` to describe it)."
        ),
    )
    note: str | None = Field(
        default=None,
        description=(
            "Short human-facing label for what you're about to do. Required "
            "when `step_index` is null; otherwise optional."
        ),
    )


@tool(
    tier=ActionTier.READ_ONLY,
    category="meta",
    embedding_text="",
)
async def advance_to_step(db: AsyncSession, input: AdvanceToStepInput) -> dict:
    """Signal that you're starting a new step in the plan (or going off-plan).

    Call this at the start of each plan step, before the real tool calls for
    that step. Pass the 1-based `step_index`. If the plan needs to change and
    you're doing something not covered by a step, pass `step_index: null` and
    a short `note` describing what you're doing instead.
    """
    return {"acknowledged": True}
