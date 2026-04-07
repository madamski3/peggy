"""Add daily_plans table for storing proactive plan proposals.

Revision ID: 007
Revises: 006
Create Date: 2026-04-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "daily_plans",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("plan_date", sa.Date, nullable=False),
        sa.Column("status", sa.Text, server_default=sa.text("'proposed'"), nullable=False),
        sa.Column("proposal", JSONB, nullable=False),
        sa.Column("spoken_summary", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_daily_plans_date", "daily_plans", ["plan_date"])


def downgrade() -> None:
    op.drop_index("ix_daily_plans_date", table_name="daily_plans")
    op.drop_table("daily_plans")
