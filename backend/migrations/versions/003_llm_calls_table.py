"""Add llm_calls table for per-round LLM response metadata.

Revision ID: 003
Revises: 002
Create Date: 2026-04-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "llm_calls",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("interaction_id", UUID(as_uuid=True), sa.ForeignKey("interactions.id"), nullable=True),
        sa.Column("session_id", UUID(as_uuid=True), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("stop_reason", sa.Text(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("thinking_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("cache_read_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("cache_creation_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("estimated_cost_usd", sa.Numeric(precision=10, scale=6), nullable=False, server_default=sa.text("0")),
        sa.Column("raw_response", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_llm_calls_session_id", "llm_calls", ["session_id"])
    op.create_index("ix_llm_calls_interaction_id", "llm_calls", ["interaction_id"])


def downgrade() -> None:
    op.drop_index("ix_llm_calls_interaction_id")
    op.drop_index("ix_llm_calls_session_id")
    op.drop_table("llm_calls")
