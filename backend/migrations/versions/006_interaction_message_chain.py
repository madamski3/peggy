"""Add message_chain column to interactions for full tool context replay.

Revision ID: 006
Revises: 005
Create Date: 2026-04-02
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("interactions", sa.Column("message_chain", JSONB))


def downgrade() -> None:
    op.drop_column("interactions", "message_chain")
