"""NGO checks: confirmed by phone, checked against banned lists, registration.

Revision ID: 0004_ngo_checks
Revises: 0003_ngos
Create Date: 2026-10-27
"""
import sqlalchemy as sa
from alembic import op

revision = "0004_ngo_checks"
down_revision = "0003_ngos"
branch_labels = None
depends_on = None

COLUMNS = [
    ("phone_confirmed_at", sa.DateTime(timezone=True)),
    ("ban_checked_at", sa.DateTime(timezone=True)),
    ("registration", sa.String(160)),
]


def upgrade() -> None:
    have = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("ngos")}   # a new database already has them
    for name, type_ in COLUMNS:
        if name not in have:
            op.add_column("ngos", sa.Column(name, type_, nullable=True))


def downgrade() -> None:
    for name, _ in COLUMNS:
        op.drop_column("ngos", name)
