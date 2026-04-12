"""Unified daily planning router — yesterday's review + today's plan proposal.

Endpoints:
  GET  /planning/today      — fetch review todos + current plan proposal
  POST /planning/submit     — process review decisions + execute approved plan
  POST /planning/regenerate — generate a fresh plan via agent
  POST /planning/refine     — modify current plan based on user feedback
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import async_session_maker, get_db
from app.globals import get_cached_timezone
from app.models.tables import Todo
from app.services import daily_plans as plan_service
from app.services import planning as planning_exec
from app.services import todos as todo_service
from app.services.proactive import invoke_agent_proactively
from app.services.serialization import model_to_dict

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/planning", tags=["planning"])

PLANNING_PROMPT = """\
Plan the user's day. Check today's calendar, scheduled todos, backlog todos \
(especially those with approaching deadlines or target dates), and find free \
time slots. Generate a daily plan proposal.

Return a structured_payload with EXACTLY this schema (no extra keys):
```json
{
  "type": "daily_plan",
  "date": "YYYY-MM-DD",
  "events": [
    {
      "title": "Event or todo title",
      "scheduled_start": "ISO8601 with timezone",
      "scheduled_end": "ISO8601 with timezone",
      "todo_id": "uuid-of-todo OR null for calendar-only events",
      "proposed": true
    }
  ]
}
```
The events array is a flat list containing ALL events for the day:
- Calendar events already on the schedule: proposed=false, todo_id=null
- Todos already scheduled for today: proposed=false, todo_id=<their uuid>
- Newly proposed todos from the backlog: proposed=true, todo_id=<their uuid>

Each event MUST have ISO8601 scheduled_start and scheduled_end in the user's timezone.
Sort events by scheduled_start.

Also include a brief spoken_summary (2-3 sentences for a push notification).\
"""


# ── Request/response schemas ────────────────────────────────────────


class TodoReviewItem(BaseModel):
    todo_id: str
    action: Literal["complete", "reschedule"]
    completion_notes: str | None = None


class PlanningSubmission(BaseModel):
    review_items: list[TodoReviewItem] = []
    approved_events: list[dict[str, Any]] | None = None
    plan_id: str | None = None


class RefineRequest(BaseModel):
    feedback: str
    current_proposal: dict[str, Any]


# ── Helpers ──────────────────────────────────────────────────────────


async def _get_review_todos(db: AsyncSession) -> tuple[list[dict], str]:
    """Fetch all past incomplete scheduled todos for review.

    Looks at every todo scheduled before today that isn't completed or
    cancelled, so skipping a day of planning doesn't orphan items.
    """
    user_tz = get_cached_timezone()
    now_local = datetime.now(user_tz)
    today_start = datetime(
        now_local.year, now_local.month, now_local.day, tzinfo=user_tz
    )

    result = await db.execute(
        select(Todo)
        .options(selectinload(Todo.parent))
        .where(
            and_(
                Todo.scheduled_start < today_start,
                Todo.scheduled_start.isnot(None),
                Todo.status.notin_(["completed", "cancelled"]),
            )
        )
        .order_by(Todo.scheduled_start.asc())
    )
    todos = list(result.scalars().all())

    todo_dicts = []
    for t in todos:
        d = model_to_dict(t)
        d["parent_title"] = t.parent.title if t.parent else None
        todo_dicts.append(d)

    yesterday = now_local.date() - timedelta(days=1)
    return todo_dicts, str(yesterday)


async def _enrich_events_with_todo_ids(db: AsyncSession, proposal: dict) -> dict:
    """Link calendar events in the proposal to their todos.

    Looks up todos that have a calendar_event_id and matches them to
    events in the proposal.  Calendar events from Google include an ``id``
    field that corresponds to ``calendar_event_id`` on the todo.  The
    agent may also include an ``event_id`` from the calendar API.
    """
    events = proposal.get("events", [])
    if not events:
        return proposal

    # Build lookup: calendar_event_id -> todo_id for all todos with calendar links
    result = await db.execute(
        select(Todo.id, Todo.calendar_event_id).where(
            Todo.calendar_event_id.isnot(None),
            Todo.status.notin_(["completed", "cancelled"]),
        )
    )
    cal_to_todo = {row.calendar_event_id: str(row.id) for row in result.all()}

    if not cal_to_todo:
        return proposal

    for event in events:
        # Skip events that already have a todo_id
        if event.get("todo_id"):
            continue
        # Match by event_id if the agent included it from calendar data
        event_id = event.get("event_id")
        if event_id and event_id in cal_to_todo:
            event["todo_id"] = cal_to_todo[event_id]

    return proposal


async def _generate_plan(prompt: str) -> dict | None:
    """Invoke the agent to generate a daily plan proposal.

    Returns the structured_payload dict if the agent produced one, else None.
    """
    response = await invoke_agent_proactively(async_session_maker, prompt)
    if not response:
        return None

    payload = response.get("structured_payload")
    if isinstance(payload, dict) and payload.get("type") == "daily_plan":
        return {
            "proposal": payload,
            "spoken_summary": response.get("spoken_summary"),
        }
    return None


# ── Endpoints ────────────────────────────────────────────────────────


@router.get("/dates")
async def list_plan_dates(db: AsyncSession = Depends(get_db)):
    """Return all dates that have a stored plan."""
    dates = await plan_service.list_plan_dates(db)
    return {"dates": dates}


@router.get("/history/{plan_date}")
async def get_plan_by_date(plan_date: str, db: AsyncSession = Depends(get_db)):
    """Return a stored plan for a specific date."""
    try:
        parsed = datetime.strptime(plan_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format, use YYYY-MM-DD")
    plan = await plan_service.get_plan_for_date(db, parsed)
    if plan is None:
        raise HTTPException(status_code=404, detail="No plan found for this date")
    return plan


@router.get("/today")
async def get_today(db: AsyncSession = Depends(get_db)):
    """Return review todos (past incomplete) and today's plan proposal."""
    review_todos, review_date = await _get_review_todos(db)

    user_tz = get_cached_timezone()
    today = datetime.now(user_tz).date()
    plan = await plan_service.get_plan_for_date(db, today)

    return {
        "review": {"todos": review_todos, "review_date": review_date},
        "plan": plan,
    }


@router.post("/submit")
async def submit_planning(body: PlanningSubmission, db: AsyncSession = Depends(get_db)):
    """Process review decisions and execute the approved plan."""
    # Step 1: process review
    completed = 0
    rescheduled = 0

    for item in body.review_items:
        if item.action == "complete":
            result = await todo_service.complete_todo(
                db, item.todo_id, completion_notes=item.completion_notes
            )
            if result is None:
                raise HTTPException(status_code=404, detail=f"Todo {item.todo_id} not found")
            completed += 1
        elif item.action == "reschedule":
            result = await todo_service.send_to_backlog(
                db, item.todo_id, notes=item.completion_notes
            )
            if result is None:
                raise HTTPException(status_code=404, detail=f"Todo {item.todo_id} not found")
            rescheduled += 1

    # Step 2: execute approved events (schedule todos + create calendar events)
    plan_result = {"todos_scheduled": 0, "calendar_events_created": 0}
    if body.approved_events:
        plan_result = await planning_exec.execute_daily_plan(db, body.approved_events)

    # Step 3: mark plan as approved, storing only the accepted events
    if body.plan_id:
        await plan_service.mark_approved(
            db, body.plan_id, approved_events=body.approved_events
        )

    await db.commit()
    return {
        "review": {"completed": completed, "rescheduled": rescheduled},
        "plan": plan_result,
    }


@router.post("/regenerate")
async def regenerate_plan(db: AsyncSession = Depends(get_db)):
    """Generate a fresh daily plan proposal via the agent."""
    result = await _generate_plan(PLANNING_PROMPT)

    if result is None:
        raise HTTPException(status_code=502, detail="Agent did not produce a plan proposal")

    proposal = await _enrich_events_with_todo_ids(db, result["proposal"])
    user_tz = get_cached_timezone()
    today = datetime.now(user_tz).date()
    plan = await plan_service.save_proposal(
        db, today, proposal, result.get("spoken_summary")
    )
    await db.commit()
    return plan


@router.post("/refine")
async def refine_plan(body: RefineRequest, db: AsyncSession = Depends(get_db)):
    """Modify the current plan based on user feedback."""
    prompt = (
        "The user is reviewing their daily plan proposal. Here is the current plan:\n"
        f"{json.dumps(body.current_proposal, indent=2)}\n\n"
        f"The user's feedback: {body.feedback}\n\n"
        "Please modify the plan accordingly and return the updated structured_payload "
        "with type 'daily_plan'. Keep existing calendar events unchanged. "
        "Return the full updated plan, not just the changes."
    )

    result = await _generate_plan(prompt)

    if result is None:
        raise HTTPException(status_code=502, detail="Agent did not produce an updated plan")

    proposal = await _enrich_events_with_todo_ids(db, result["proposal"])
    user_tz = get_cached_timezone()
    today = datetime.now(user_tz).date()
    plan = await plan_service.save_proposal(
        db, today, proposal, result.get("spoken_summary")
    )
    await db.commit()
    return plan
