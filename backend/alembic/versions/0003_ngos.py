"""NGOs replace distribution points, relief camps and hand-outs.

RAAZICID does not hand out donations itself: riders drop them at an NGO in the city, found by web search.
- new tables ngos and ngo_categories; donations.ngo_id
- donation statuses at_point and handed_out become delivered (also in the status history)
- distribution-proof photos, hand_outs, point_requests, point_categories and distribution_points are removed

Revision ID: 0003_ngos
Revises: 0002_report_needs_checked
Create Date: 2026-10-27
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0003_ngos"
down_revision = "0002_report_needs_checked"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "ngos" not in tables:   # a new database already has it (0001 builds from the current models)
        op.create_table(
            "ngos",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("name", sa.String(160), nullable=False),
            sa.Column("location_id", UUID(as_uuid=True), sa.ForeignKey("locations.id"), nullable=False),
            sa.Column("address", sa.Text(), nullable=False),
            sa.Column("lat", sa.Float(), nullable=False),
            sa.Column("lng", sa.Float(), nullable=False),
            sa.Column("location_approx", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("phone", sa.String(40)),
            sa.Column("website", sa.Text()),
            sa.Column("about", sa.Text()),
            sa.Column("takes_cooked_food", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("source_url", sa.Text()),
            sa.Column("found_by", sa.String(20), nullable=False, server_default="admin"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_ngos_location_id", "ngos", ["location_id"])
    if "ngo_categories" not in tables:
        op.create_table(
            "ngo_categories",
            sa.Column("ngo_id", UUID(as_uuid=True), sa.ForeignKey("ngos.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("category_id", sa.Integer(), sa.ForeignKey("categories.id"), primary_key=True),
        )
    donation_cols = {c["name"] for c in sa.inspect(bind).get_columns("donations")}
    if "ngo_id" not in donation_cols:
        op.add_column("donations", sa.Column("ngo_id", UUID(as_uuid=True), sa.ForeignKey("ngos.id"), nullable=True))
        op.create_index("ix_donations_ngo_id", "donations", ["ngo_id"])

    for col in ("status",):
        op.execute(f"UPDATE donations SET {col} = 'delivered' WHERE {col} IN ('at_point', 'handed_out')")
    for col in ("from_status", "to_status"):
        op.execute(f"UPDATE status_changes SET {col} = 'delivered' WHERE {col} IN ('at_point', 'handed_out')")
    # A history row "at_point -> handed_out" is now "delivered -> delivered": drop it
    op.execute("DELETE FROM status_changes WHERE from_status = 'delivered' AND to_status = 'delivered'")
    op.execute("DELETE FROM donation_images WHERE kind = 'distribution_proof'")

    if "point_id" in donation_cols:
        op.execute("ALTER TABLE donations DROP COLUMN point_id CASCADE")
    for t in ("hand_outs", "point_requests", "point_categories", "distribution_points"):
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")


def downgrade() -> None:
    raise NotImplementedError("Distribution points were removed; restore a database backup to go back.")
