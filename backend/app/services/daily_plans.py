"""Daily plan proposal storage and retrieval.

Manages the lifecycle of proactive daily plan proposals:
  - save_proposal() — upsert a draft plan for a given date
  - get_plan_for_date() — fetch the latest plan for a date
  - mark_approved() — mark a plan as approved after user confirms
"""

from datetime import date, datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import DailyPlan
from app.services.serialization import model_to_dict


async def save_proposal(
    db: AsyncSession,
    plan_date: date,
    proposal: dict,
    spoken_summary: str | None = None,
) -> dict:
    """Save (or replace) a proposed daily plan for the given date.

    If a plan with status 'proposed' already exists for this date, it is
    deleted first so only one draft exists at a time.
    """
    await db.execute(
        delete(DailyPlan).where(DailyPlan.plan_date == plan_date)
    )
    plan = DailyPlan(
        plan_date=plan_date,
        proposal=proposal,
        spoken_summary=spoken_summary,
    )
    db.add(plan)
    await db.flush()
    return model_to_dict(plan)


async def get_plan_for_date(db: AsyncSession, plan_date: date) -> dict | None:
    """Return the latest plan for a date, or None."""
    result = await db.execute(
        select(DailyPlan)
        .where(DailyPlan.plan_date == plan_date)
        .order_by(DailyPlan.created_at.desc())
        .limit(1)
    )
    plan = result.scalar_one_or_none()
    if plan is None:
        return None
    return model_to_dict(plan)


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
    approved_plan_items: list[dict] | None = None,
) -> None:
    """Mark a plan as approved, storing only the accepted items."""
    import uuid as _uuid

    result = await db.execute(
        select(DailyPlan).where(DailyPlan.id == _uuid.UUID(plan_id))
    )
    plan = result.scalar_one_or_none()
    if plan:
        plan.status = "approved"
        plan.approved_at = datetime.now(timezone.utc)
        if approved_plan_items is not None:
            updated = {**plan.proposal, "plan_items": approved_plan_items}
            plan.proposal = updated
