"""Add vector embedding column to profile_facts for semantic search.

Revision ID: 004
Revises: 003
Create Date: 2026-04-02
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column("profile_facts", sa.Column("embedding", Vector(1536)))
    op.create_index(
        "ix_profile_facts_embedding",
        "profile_facts",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_profile_facts_embedding", table_name="profile_facts")
    op.drop_column("profile_facts", "embedding")
