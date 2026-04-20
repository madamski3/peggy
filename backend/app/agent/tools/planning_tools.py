"""Daily planning tool definitions for the agent.

Registered tools:
  - execute_daily_plan  (HIGH_STAKES) -- schedule todos + create calendar events for a daily plan
"""

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools.registry import ActionTier, tool
from app.services import planning as planning_service


class PlanEvent(BaseModel):
    title: str
    scheduled_start: str
    scheduled_end: str
    todo_id: str | None
    proposed: bool


class ExecuteDailyPlanInput(BaseModel):
    events: list[PlanEvent]


@tool(
    tier=ActionTier.HIGH_STAKES,
    category="planning",
    embedding_text=(
        "planning: execute_daily_plan — execute, run, activate a daily plan, "
        "batch schedule todos and create calendar events for the day. Plan my day. "
        "Schedule all my todos for today. Create a daily schedule."
    ),
)
async def execute_daily_plan(db: AsyncSession, input: ExecuteDailyPlanInput) -> dict:
    """Execute a daily plan: schedule todos and create calendar events for approved plan events (requires confirmation)."""
    events = [e.model_dump() for e in input.events]
    return await planning_service.execute_daily_plan(db, events)
