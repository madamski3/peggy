"""Todos router -- REST endpoints for the frontend UI."""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services import todos as todo_service

router = APIRouter(prefix="/todos", tags=["todos"])


class TodoUpdate(BaseModel):
    status: str | None = None
    priority: str | None = None
    title: str | None = None
    scheduled_start: str | None = None
    scheduled_end: str | None = None


@router.get("/")
async def list_todos(
    status: str | None = Query(None),
    priority: str | None = Query(None),
    scheduled_date: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    filters = {}
    if status:
        filters["status"] = status
    if priority:
        filters["priority"] = priority
    if scheduled_date:
        filters["scheduled_date"] = scheduled_date
    todos = await todo_service.get_todos(db, filters)
    return {"todos": todos}


@router.patch("/{todo_id}")
async def update_todo(
    todo_id: str,
    body: TodoUpdate,
    db: AsyncSession = Depends(get_db),
):
    fields = body.model_dump(exclude_none=True)
    result = await todo_service.update_todo(db, todo_id, fields)
    if result is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Todo not found")
    await db.commit()
    return result


@router.delete("/{todo_id}")
async def delete_todo(
    todo_id: str,
    db: AsyncSession = Depends(get_db),
):
    deleted = await todo_service.delete_todo(db, todo_id)
    if not deleted:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Todo not found")
    await db.commit()
    return {"success": True}
