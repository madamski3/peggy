"""Pydantic schemas for the agent chat endpoint.

These define the API contract between the frontend and the agent:
  - ChatRequest: what the frontend sends (message, session_id, confirmation_id)
  - ChatResponse: what the agent returns (spoken_summary, actions, confirmations, suggestions)
  - ActionTaken: a record of each tool the agent executed
  - ConfirmationRequired: returned when a HIGH_STAKES tool needs user approval
  - TurnPlan: the planner's structured plan for handling the current turn
  - StatusEvent: structured progress update streamed over SSE
"""

import uuid
from typing import Literal

from pydantic import BaseModel, Field


class TurnPlan(BaseModel):
    """The planner's plan for this conversational turn.

    `goal` frames what the user is trying to accomplish in one sentence.
    `steps` are high-level, natural-language steps the agent is expected to
    work through — not a script of tool calls. The agent may deviate when
    reality diverges from the plan.
    """

    goal: str = ""
    steps: list[str] = []


class StatusEvent(BaseModel):
    """A structured progress update emitted during the agent loop.

    Shape varies by `kind`:
      - "message": a free-text status line (``message``).
      - "plan": the planner's plan, emitted once at the start of the loop (``plan``).
      - "step": the agent has advanced to a step (``step_index`` 1-based,
        or None for off-plan work; ``step_text`` is the label to display).
    """

    kind: Literal["message", "plan", "step"]
    message: str | None = None
    plan: TurnPlan | None = None
    step_index: int | None = None
    step_text: str | None = None


class ChatRequest(BaseModel):
    """Incoming chat message from the user."""

    message: str
    session_id: uuid.UUID | None = None
    confirmation_id: uuid.UUID | None = None


class ActionTaken(BaseModel):
    """Record of a tool action executed during the agent loop."""

    tool_name: str
    tool_args: dict
    result_summary: str


class ConfirmationRequired(BaseModel):
    """Returned when a HIGH_STAKES action needs user approval before executing."""

    confirmation_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    tool_name: str
    tool_args: dict
    description: str


class ChatResponse(BaseModel):
    """The agent's response contract."""

    spoken_summary: str
    structured_payload: dict | None = None
    actions_taken: list[ActionTaken] = []
    confirmation_required: ConfirmationRequired | None = None
    follow_up_suggestions: list[str] = []
    session_id: uuid.UUID
