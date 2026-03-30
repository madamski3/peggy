"""Pydantic schemas for the agent chat endpoint.

These define the API contract between the frontend and the agent:
  - ChatRequest: what the frontend sends (message, session_id, confirmation_id)
  - ChatResponse: what the agent returns (spoken_summary, actions, confirmations, suggestions)
  - ActionTaken: a record of each tool the agent executed
  - ConfirmationRequired: returned when a HIGH_STAKES tool needs user approval
"""

import uuid

from pydantic import BaseModel, Field


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
