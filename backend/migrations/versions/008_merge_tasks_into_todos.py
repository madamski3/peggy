"""Merge tasks table into todos.

Tasks were a thin scheduling wrapper around todos. This migration:
1. Adds scheduling/completion columns to the todos table
2. Renames status 'active' -> 'scheduled'
3. Migrates each task row into a new child todo
4. Moves scheduled_notifications FK from task_id to todo_id
5. Drops the tasks table

Revision ID: 008
Revises: 007
Create Date: 2026-04-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Step 1: Add new columns to todos
    op.add_column("todos", sa.Column("scheduled_start", sa.DateTime(timezone=True)))
    op.add_column("todos", sa.Column("scheduled_end", sa.DateTime(timezone=True)))
    op.add_column("todos", sa.Column("actual_duration_minutes", sa.Integer))
    op.add_column("todos", sa.Column("calendar_event_id", sa.Text))
    op.add_column("todos", sa.Column("completed_at", sa.DateTime(timezone=True)))
    op.add_column("todos", sa.Column("deferred_count", sa.Integer, server_default=sa.text("0")))
    op.add_column("todos", sa.Column("completion_notes", sa.Text))
    op.add_column("todos", sa.Column("position", sa.Integer))

    # Step 2: Rename status 'active' -> 'scheduled'
    op.execute("UPDATE todos SET status = 'scheduled' WHERE status = 'active'")

    # Step 3: Add todo_id column to scheduled_notifications (before dropping tasks)
    op.add_column(
        "scheduled_notifications",
        sa.Column("todo_id", UUID(as_uuid=True), sa.ForeignKey("todos.id")),
    )

    # Step 4: Migrate task rows into child todos + update notification FKs
    # Use a CTE to insert tasks as child todos and capture the id mapping
    op.execute("""
        WITH task_migration AS (
            INSERT INTO todos (
                title, description, status, priority,
                parent_todo_id,
                scheduled_start, scheduled_end,
                estimated_duration_minutes, actual_duration_minutes,
                calendar_event_id,
                completed_at, deferred_count, completion_notes,
                position, created_by, created_at, updated_at
            )
            SELECT
                t.title,
                t.description,
                CASE
                    WHEN t.status = 'in_progress' THEN 'scheduled'
                    ELSE t.status
                END,
                'medium',
                t.todo_id,
                t.scheduled_start,
                t.scheduled_end,
                t.estimated_duration_minutes,
                t.actual_duration_minutes,
                t.calendar_event_id,
                t.completed_at,
                t.deferred_count,
                t.completion_notes,
                t.position,
                t.created_by,
                t.created_at,
                t.updated_at
            FROM tasks t
            RETURNING id, parent_todo_id, scheduled_start, created_at
        )
        UPDATE scheduled_notifications sn
        SET todo_id = tm.id
        FROM task_migration tm
        JOIN tasks t ON t.todo_id = tm.parent_todo_id
            AND t.scheduled_start IS NOT DISTINCT FROM tm.scheduled_start
            AND t.created_at = tm.created_at
        WHERE sn.task_id = t.id
    """)

    # For any notifications that didn't match (edge case), point to the parent todo
    op.execute("""
        UPDATE scheduled_notifications
        SET todo_id = (
            SELECT todo_id FROM tasks WHERE tasks.id = scheduled_notifications.task_id
        )
        WHERE todo_id IS NULL AND task_id IS NOT NULL
    """)

    # Step 5: Drop task_id column from scheduled_notifications
    op.drop_constraint(
        "scheduled_notifications_task_id_fkey",
        "scheduled_notifications",
        type_="foreignkey",
    )
    op.drop_column("scheduled_notifications", "task_id")

    # Step 6: Add indexes
    op.create_index(
        "idx_todos_scheduled_start",
        "todos",
        ["scheduled_start"],
        postgresql_where=sa.text("scheduled_start IS NOT NULL"),
    )
    # idx_todos_parent already exists from a prior migration, skip it
    op.create_index(
        "idx_todos_calendar_event",
        "todos",
        ["calendar_event_id"],
        postgresql_where=sa.text("calendar_event_id IS NOT NULL"),
    )

    # Step 7: Drop tasks table and its indexes
    op.drop_index("idx_tasks_scheduled", table_name="tasks")
    op.drop_index("idx_tasks_status", table_name="tasks")
    op.drop_index("idx_tasks_todo", table_name="tasks")
    op.drop_index("idx_tasks_calendar", table_name="tasks")
    op.drop_table("tasks")


def downgrade() -> None:
    # Recreate tasks table
    op.create_table(
        "tasks",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("todo_id", UUID(as_uuid=True), sa.ForeignKey("todos.id"), nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("scheduled_start", sa.DateTime(timezone=True)),
        sa.Column("scheduled_end", sa.DateTime(timezone=True)),
        sa.Column("estimated_duration_minutes", sa.Integer),
        sa.Column("actual_duration_minutes", sa.Integer),
        sa.Column("calendar_event_id", sa.Text),
        sa.Column("status", sa.Text, server_default=sa.text("'scheduled'")),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("deferred_count", sa.Integer, server_default=sa.text("0")),
        sa.Column("completion_notes", sa.Text),
        sa.Column("position", sa.Integer),
        sa.Column("created_by", sa.Text, server_default=sa.text("'assistant'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # Restore task_id on scheduled_notifications
    op.add_column(
        "scheduled_notifications",
        sa.Column("task_id", UUID(as_uuid=True), sa.ForeignKey("tasks.id")),
    )
    op.drop_column("scheduled_notifications", "todo_id")

    # Drop new indexes and columns from todos
    op.drop_index("idx_todos_calendar_event", table_name="todos")
    op.drop_index("idx_todos_parent", table_name="todos")
    op.drop_index("idx_todos_scheduled_start", table_name="todos")
    op.drop_column("todos", "completion_notes")
    op.drop_column("todos", "deferred_count")
    op.drop_column("todos", "completed_at")
    op.drop_column("todos", "calendar_event_id")
    op.drop_column("todos", "actual_duration_minutes")
    op.drop_column("todos", "scheduled_end")
    op.drop_column("todos", "scheduled_start")
    op.drop_column("todos", "position")

    # Restore status
    op.execute("UPDATE todos SET status = 'active' WHERE status = 'scheduled'")
