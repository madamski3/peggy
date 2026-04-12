"""Daily plan proposal storage and retrieval.

Manages the lifecycle of proactive daily plan proposals:
  - save_proposal() — upsert a draft plan for a given date
  - get_plan_for_date() — fetch the latest plan for a date
  - mark_approved() — mark a plan as approved after user confirms
"""

from datetime import date, datetime, timezone

from sqlalchemy import and_, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import DailyPlan
from app.services.serialization import model_to_dict


async def save_proposal(
    db: AsyncSession,
    plan_date: date,
    proposal: dict,
    spoken_summary: str | None = None,
) -> dict:
    """Save a proposed daily plan for the given date.

    Any existing plans with status 'proposed' for this date are set to
    'expired' so only one active draft exists at a time.  Expired plans
    are kept for read-only record-keeping.
    """
    await db.execute(
        update(DailyPlan)
        .where(and_(DailyPlan.plan_date == plan_date, DailyPlan.status == "proposed"))
        .values(status="expired")
    )
    plan = DailyPlan(
        plan_date=plan_date,
        proposal=proposal,
        spoken_summary=spoken_summary,
    )
    db.add(plan)
    await db.flush()
    return model_to_dict(plan)


def _normalize_proposal(proposal: dict) -> dict:
    """Convert old nested plan format to flat events format on read.

    Old format had ``existing_events`` + ``plan_items[].tasks[]``.
    New format uses a single ``events[]`` array with ``proposed`` boolean.
    """
    if "events" in proposal:
        return proposal

    events: list[dict] = []
    for ev in proposal.get("existing_events", []):
        events.append({
            "title": ev.get("title", ""),
            "scheduled_start": ev.get("start"),
            "scheduled_end": ev.get("end"),
            "todo_id": None,
            "proposed": False,
        })
    for item in proposal.get("plan_items", []):
        for task in item.get("tasks", []):
            events.append({
                "title": task.get("title", ""),
                "scheduled_start": task.get("scheduled_start"),
                "scheduled_end": task.get("scheduled_end"),
                "todo_id": item.get("todo_id"),
                "proposed": True,
            })
    events.sort(key=lambda e: e.get("scheduled_start") or "")
    return {"type": "daily_plan", "events": events}


async def get_plan_for_date(
    db: AsyncSession, plan_date: date, *, include_expired: bool = False
) -> dict | None:
    """Return the latest plan for a date, or None.

    By default, expired plans are excluded so the active (proposed/approved)
    plan is returned.  Pass ``include_expired=True`` for historical views.
    """
    query = select(DailyPlan).where(DailyPlan.plan_date == plan_date)
    if not include_expired:
        query = query.where(DailyPlan.status != "expired")
    result = await db.execute(
        query.order_by(DailyPlan.created_at.desc()).limit(1)
    )
    plan = result.scalar_one_or_none()
    if plan is None:
        return None
    d = model_to_dict(plan)
    d["proposal"] = _normalize_proposal(d.get("proposal", {}))
    return d


async def list_plan_dates(db: AsyncSession) -> list[str]:
    """Return all dates that have a plan, most recent first."""
    result = await db.execute(
        select(DailyPlan.plan_date)
        .distinct()
        .order_by(DailyPlan.plan_date.desc())
    )
    return [row.isoformat() for row in result.scalars().all()]


async def mark_approved(
    db: AsyncSession,
    plan_id: str,
    approved_events: list[dict] | None = None,
) -> None:
    """Mark a plan as approved, storing only the accepted events."""
    import uuid as _uuid

    result = await db.execute(
        select(DailyPlan).where(DailyPlan.id == _uuid.UUID(plan_id))
    )
    plan = result.scalar_one_or_none()
    if plan:
        plan.status = "approved"
        plan.approved_at = datetime.now(timezone.utc)
        if approved_events is not None:
            updated = {**plan.proposal, "events": approved_events}
            plan.proposal = updated
