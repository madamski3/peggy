"""Add tools JSONB column to llm_calls for tool selection logging.

Revision ID: 009
Revises: 008
Create Date: 2026-04-12
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("llm_calls", sa.Column("tools", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("llm_calls", "tools")
