"""Initial schema: pgvector extension + all Phase 1 tables.

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-24

This first migration builds the tables straight from the models. From here on, every
model change gets its own migration:  alembic revision --autogenerate -m "what changed"
"""
from alembic import op

from app.db.base import Base
import app.models  # noqa: F401

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    Base.metadata.create_all(bind=op.get_bind())
    # Fast nearest-neighbour search on report chunks (cosine distance)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_report_chunks_embedding "
        "ON report_chunks USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
