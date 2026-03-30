"""SQLAlchemy ORM models for all database tables.

This is the single source of truth for the database schema. All 12 tables
are defined here. The main groups:

  Knowledge base:
    - ProfileFact     -- versioned user knowledge (with superseded_by chain)
    - SeedFieldVersion -- form field edit history (for diff detection in ingestion)
    - Person          -- contacts directory

  Productivity:
    - Todo            -- backlog items (has many Tasks, supports hierarchy)
    - Task            -- scheduled work blocks (belongs to a Todo)
    - List            -- named lists (grocery, packing, custom)
    - ListItem        -- items within a list

  Infrastructure:
    - Interaction     -- conversation log (user message + agent response)
    - Credential      -- OAuth tokens (currently Google Calendar)
    - ScheduledNotification -- (placeholder) push notification queue

  Financial (placeholder, not yet implemented):
    - FinancialAccount, Transaction, NetWorthSnapshot
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    ARRAY,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class ProfileFact(Base):
    __tablename__ = "profile_facts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    category: Mapped[str] = mapped_column(Text, nullable=False)
    key: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    provenance: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, server_default=text("1.0"))
    evidence: Mapped[str | None] = mapped_column(Text)
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profile_facts.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    last_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Person(Base):
    __tablename__ = "people"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    relationship_type: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    contact_info: Mapped[dict | None] = mapped_column(JSONB)
    key_dates: Mapped[dict | None] = mapped_column(JSONB)
    preferences: Mapped[dict | None] = mapped_column(JSONB)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class SeedFieldVersion(Base):
    __tablename__ = "seed_field_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    field_key: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    edited_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class Todo(Base):
    __tablename__ = "todos"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default=text("'backlog'"))
    priority: Mapped[str] = mapped_column(Text, server_default=text("'medium'"))

    # Scheduling
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    target_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    preferred_window: Mapped[str | None] = mapped_column(Text)
    estimated_duration_minutes: Mapped[int | None] = mapped_column(Integer)
    energy_level: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(Text)

    # Hierarchy
    parent_todo_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("todos.id")
    )

    # Context
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    dependencies: Mapped[list[uuid.UUID] | None] = mapped_column(ARRAY(UUID(as_uuid=True)))
    notes: Mapped[str | None] = mapped_column(Text)

    created_by: Mapped[str] = mapped_column(Text, server_default=text("'user'"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )

    # Relationships
    tasks: Mapped[list["Task"]] = relationship(back_populates="todo")
    children: Mapped[list["Todo"]] = relationship(back_populates="parent")
    parent: Mapped["Todo | None"] = relationship(
        back_populates="children", remote_side="Todo.id"
    )


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    todo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("todos.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # Scheduling
    scheduled_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scheduled_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    estimated_duration_minutes: Mapped[int | None] = mapped_column(Integer)
    actual_duration_minutes: Mapped[int | None] = mapped_column(Integer)
    calendar_event_id: Mapped[str | None] = mapped_column(Text)

    # Status
    status: Mapped[str] = mapped_column(Text, server_default=text("'scheduled'"))

    # Completion
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deferred_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    completion_notes: Mapped[str | None] = mapped_column(Text)

    # Ordering
    position: Mapped[int | None] = mapped_column(Integer)

    created_by: Mapped[str] = mapped_column(Text, server_default=text("'assistant'"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )

    # Relationships
    todo: Mapped["Todo"] = relationship(back_populates="tasks")


class List(Base):
    __tablename__ = "lists"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(Text, server_default=text("'custom'"))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default=text("'active'"))
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )

    # Relationships
    items: Mapped[list["ListItem"]] = relationship(back_populates="list")


class ListItem(Base):
    __tablename__ = "list_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    list_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lists.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, server_default=text("'pending'"))
    notes: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int | None] = mapped_column(Integer)
    added_by: Mapped[str] = mapped_column(Text, server_default=text("'user'"))
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    list: Mapped["List"] = relationship(back_populates="items")


class Interaction(Base):
    __tablename__ = "interactions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    channel: Mapped[str] = mapped_column(Text, server_default=text("'chat'"))
    user_message: Mapped[str | None] = mapped_column(Text)
    parsed_intent: Mapped[str | None] = mapped_column(Text)
    assistant_response: Mapped[dict | None] = mapped_column(JSONB)
    actions_taken: Mapped[dict | None] = mapped_column(JSONB)
    feedback: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class FinancialAccount(Base):
    __tablename__ = "financial_accounts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    plaid_account_id: Mapped[str | None] = mapped_column(Text, unique=True)
    institution_name: Mapped[str | None] = mapped_column(Text)
    account_type: Mapped[str | None] = mapped_column(Text)
    account_name: Mapped[str | None] = mapped_column(Text)
    current_balance: Mapped[float | None] = mapped_column(Numeric)
    available_balance: Mapped[float | None] = mapped_column(Numeric)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("financial_accounts.id")
    )
    plaid_transaction_id: Mapped[str | None] = mapped_column(Text, unique=True)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric, nullable=False)
    merchant_name: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(Text)
    category_override: Mapped[str | None] = mapped_column(Text)
    is_recurring: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    notes: Mapped[str | None] = mapped_column(Text)
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class NetWorthSnapshot(Base):
    __tablename__ = "net_worth_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, unique=True)
    total_assets: Mapped[float | None] = mapped_column(Numeric)
    total_liabilities: Mapped[float | None] = mapped_column(Numeric)
    net_worth: Mapped[float | None] = mapped_column(Numeric)
    breakdown: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class Credential(Base):
    __tablename__ = "credentials"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    service: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    token_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class ScheduledNotification(Base):
    __tablename__ = "scheduled_notifications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id")
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    send_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sent: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
