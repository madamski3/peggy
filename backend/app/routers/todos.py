"""Todos router -- read-only REST endpoint for the frontend UI."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services import todos as todo_service

router = APIRouter(prefix="/todos", tags=["todos"])


@router.get("/")
async def list_todos(
    status: str | None = Query(None),
    priority: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    filters = {}
    if status:
        filters["status"] = status
    if priority:
        filters["priority"] = priority
    todos = await todo_service.get_todos(db, filters)
    return {"todos": todos}
