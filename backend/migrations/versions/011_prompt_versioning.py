"""Add prompt_components table and prompt_component_ids column on llm_calls.

Revision ID: 011
Revises: 010
Create Date: 2026-04-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "prompt_components",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("prompt_text", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_prompt_components_name",
        "prompt_components",
        ["name"],
    )
    op.add_column(
        "llm_calls",
        sa.Column("prompt_component_ids", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("llm_calls", "prompt_component_ids")
    op.drop_index("ix_prompt_components_name", table_name="prompt_components")
    op.drop_table("prompt_components")
