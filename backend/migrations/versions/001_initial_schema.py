"""Initial schema with all tables and indexes.

Revision ID: 001
Revises:
Create Date: 2026-03-27
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # pgvector extension must be created by a superuser before running this migration:
    #   psql -U postgres -d assistant -c "CREATE EXTENSION IF NOT EXISTS vector;"

    # Profile facts
    op.create_table(
        "profile_facts",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("value", JSONB(), nullable=False),
        sa.Column("provenance", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), server_default=sa.text("1.0")),
        sa.Column("evidence", sa.Text()),
        sa.Column("superseded_by", UUID(as_uuid=True), sa.ForeignKey("profile_facts.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("last_confirmed_at", sa.DateTime(timezone=True)),
    )

    # People
    op.create_table(
        "people",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("relationship_type", sa.Text()),
        sa.Column("description", sa.Text()),
        sa.Column("contact_info", JSONB()),
        sa.Column("key_dates", JSONB()),
        sa.Column("preferences", JSONB()),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # Seed field versions
    op.create_table(
        "seed_field_versions",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("entity_id", UUID(as_uuid=True)),
        sa.Column("field_key", sa.Text(), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("edited_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # Todos
    op.create_table(
        "todos",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("status", sa.Text(), server_default=sa.text("'backlog'")),
        sa.Column("priority", sa.Text(), server_default=sa.text("'medium'")),
        sa.Column("deadline", sa.DateTime(timezone=True)),
        sa.Column("target_date", sa.DateTime(timezone=True)),
        sa.Column("preferred_window", sa.Text()),
        sa.Column("estimated_duration_minutes", sa.Integer()),
        sa.Column("energy_level", sa.Text()),
        sa.Column("location", sa.Text()),
        sa.Column("parent_todo_id", UUID(as_uuid=True), sa.ForeignKey("todos.id")),
        sa.Column("tags", sa.ARRAY(sa.Text())),
        sa.Column("dependencies", sa.ARRAY(UUID(as_uuid=True))),
        sa.Column("notes", sa.Text()),
        sa.Column("created_by", sa.Text(), server_default=sa.text("'user'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # Tasks
    op.create_table(
        "tasks",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("todo_id", UUID(as_uuid=True), sa.ForeignKey("todos.id"), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("scheduled_start", sa.DateTime(timezone=True)),
        sa.Column("scheduled_end", sa.DateTime(timezone=True)),
        sa.Column("estimated_duration_minutes", sa.Integer()),
        sa.Column("actual_duration_minutes", sa.Integer()),
        sa.Column("calendar_event_id", sa.Text()),
        sa.Column("status", sa.Text(), server_default=sa.text("'scheduled'")),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("deferred_count", sa.Integer(), server_default=sa.text("0")),
        sa.Column("completion_notes", sa.Text()),
        sa.Column("position", sa.Integer()),
        sa.Column("created_by", sa.Text(), server_default=sa.text("'assistant'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # Lists
    op.create_table(
        "lists",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), server_default=sa.text("'custom'")),
        sa.Column("description", sa.Text()),
        sa.Column("status", sa.Text(), server_default=sa.text("'active'")),
        sa.Column("tags", sa.ARRAY(sa.Text())),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # List items
    op.create_table(
        "list_items",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("list_id", UUID(as_uuid=True), sa.ForeignKey("lists.id"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'pending'")),
        sa.Column("notes", sa.Text()),
        sa.Column("position", sa.Integer()),
        sa.Column("added_by", sa.Text(), server_default=sa.text("'user'")),
        sa.Column("added_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )

    # Interactions
    op.create_table(
        "interactions",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("session_id", UUID(as_uuid=True)),
        sa.Column("channel", sa.Text(), server_default=sa.text("'chat'")),
        sa.Column("user_message", sa.Text()),
        sa.Column("parsed_intent", sa.Text()),
        sa.Column("assistant_response", JSONB()),
        sa.Column("actions_taken", JSONB()),
        sa.Column("feedback", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # Financial accounts
    op.create_table(
        "financial_accounts",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("plaid_account_id", sa.Text(), unique=True),
        sa.Column("institution_name", sa.Text()),
        sa.Column("account_type", sa.Text()),
        sa.Column("account_name", sa.Text()),
        sa.Column("current_balance", sa.Numeric()),
        sa.Column("available_balance", sa.Numeric()),
        sa.Column("last_synced_at", sa.DateTime(timezone=True)),
    )

    # Transactions
    op.create_table(
        "transactions",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("account_id", UUID(as_uuid=True), sa.ForeignKey("financial_accounts.id")),
        sa.Column("plaid_transaction_id", sa.Text(), unique=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(), nullable=False),
        sa.Column("merchant_name", sa.Text()),
        sa.Column("category", sa.Text()),
        sa.Column("category_override", sa.Text()),
        sa.Column("is_recurring", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("notes", sa.Text()),
        sa.Column("synced_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # Net worth snapshots
    op.create_table(
        "net_worth_snapshots",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("date", sa.Date(), nullable=False, unique=True),
        sa.Column("total_assets", sa.Numeric()),
        sa.Column("total_liabilities", sa.Numeric()),
        sa.Column("net_worth", sa.Numeric()),
        sa.Column("breakdown", JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # Scheduled notifications
    op.create_table(
        "scheduled_notifications",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("task_id", UUID(as_uuid=True), sa.ForeignKey("tasks.id")),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("send_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # === Indexes ===

    # Todos
    op.create_index("idx_todos_status", "todos", ["status"],
                    postgresql_where=sa.text("status NOT IN ('completed', 'abandoned')"))
    op.create_index("idx_todos_deadline", "todos", ["deadline"],
                    postgresql_where=sa.text("status IN ('backlog', 'planning', 'active')"))
    op.create_index("idx_todos_priority", "todos", ["priority", "status"],
                    postgresql_where=sa.text("status IN ('backlog', 'planning', 'active')"))
    op.create_index("idx_todos_parent", "todos", ["parent_todo_id"],
                    postgresql_where=sa.text("parent_todo_id IS NOT NULL"))

    # Tasks
    op.create_index("idx_tasks_scheduled", "tasks", ["scheduled_start"],
                    postgresql_where=sa.text("status NOT IN ('completed', 'cancelled')"))
    op.create_index("idx_tasks_status", "tasks", ["status"],
                    postgresql_where=sa.text("status != 'cancelled'"))
    op.create_index("idx_tasks_todo", "tasks", ["todo_id"])
    op.create_index("idx_tasks_calendar", "tasks", ["calendar_event_id"],
                    postgresql_where=sa.text("calendar_event_id IS NOT NULL"))

    # Profile facts
    op.create_index("idx_profile_category", "profile_facts", ["category"])
    op.create_index("idx_profile_key", "profile_facts", ["key"])
    op.create_index("idx_profile_active", "profile_facts", ["category", "key"],
                    postgresql_where=sa.text("superseded_by IS NULL"))

    # Seed field versions
    op.create_index("idx_seed_versions", "seed_field_versions",
                    ["entity_type", "entity_id", "field_key", sa.text("edited_at DESC")])

    # Interactions
    op.create_index("idx_interactions_session", "interactions", ["session_id", "created_at"])
    op.create_index("idx_interactions_created", "interactions", [sa.text("created_at DESC")])

    # Transactions
    op.create_index("idx_transactions_date", "transactions", [sa.text("date DESC")])
    op.create_index("idx_transactions_category", "transactions", ["category", "date"])

    # Scheduled notifications
    op.create_index("idx_notifications_pending", "scheduled_notifications", ["send_at"],
                    postgresql_where=sa.text("sent = FALSE"))

    # List items
    op.create_index("idx_list_items_list", "list_items", ["list_id", "status"])


def downgrade() -> None:
    op.drop_table("scheduled_notifications")
    op.drop_table("net_worth_snapshots")
    op.drop_table("transactions")
    op.drop_table("financial_accounts")
    op.drop_table("interactions")
    op.drop_table("list_items")
    op.drop_table("lists")
    op.drop_table("tasks")
    op.drop_table("todos")
    op.drop_table("seed_field_versions")
    op.drop_table("people")
    op.drop_table("profile_facts")
    # pgvector extension should be dropped manually by superuser if needed
