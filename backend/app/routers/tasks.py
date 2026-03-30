"""Tasks router -- read-only REST endpoint for the frontend UI."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services import tasks as task_service

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("/")
async def list_tasks(
    status: str | None = Query(None),
    scheduled_date: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    filters = {}
    if status:
        filters["status"] = status
    if scheduled_date:
        filters["scheduled_date"] = scheduled_date
    tasks = await task_service.get_tasks(db, filters)
    return {"tasks": tasks}
