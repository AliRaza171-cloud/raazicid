"""Reports remember when the AI read them for unmet needs (report reader, Phase 6).

Revision ID: 0002_report_needs_checked
Revises: 0001_initial
Create Date: 2026-10-25
"""
import sqlalchemy as sa
from alembic import op

revision = "0002_report_needs_checked"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("reports", sa.Column("needs_checked_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_reports_needs_checked_at", "reports", ["needs_checked_at"])


def downgrade() -> None:
    op.drop_index("ix_reports_needs_checked_at", table_name="reports")
    op.drop_column("reports", "needs_checked_at")
