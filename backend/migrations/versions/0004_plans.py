"""plan_runs, blocks, plan_assignments

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-17
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.db.base import UTCDateTime

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

BigPk = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
Json = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")

PLAN_STATUSES = (
    "'queued', 'running', 'succeeded', 'infeasible', 'failed', 'cancelled', "
    "'approved', 'published', 'superseded'"
)
BLOCK_STATUSES = "'proposed', 'published', 'cancelled', 'completed'"


def upgrade() -> None:
    op.create_table(
        "plan_runs",
        sa.Column("id", BigPk, primary_key=True, autoincrement=True),
        sa.Column("parent_id", BigPk, sa.ForeignKey("plan_runs.id")),
        sa.Column("created_by", BigPk, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("horizon_start", UTCDateTime(), nullable=False),
        sa.Column("horizon_end", UTCDateTime(), nullable=False),
        sa.Column("slot_minutes", sa.SmallInteger(), nullable=False, server_default="30"),
        sa.Column("weights", Json, nullable=False),
        sa.Column("time_limit_s", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("random_seed", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("input_hash", sa.Text()),
        sa.Column("model_versions", Json, nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="queued"),
        sa.Column("solver_status", sa.Text()),
        sa.Column("objective_value", sa.Float()),
        sa.Column("best_bound", sa.Float()),
        sa.Column("metrics", Json),
        sa.Column("error", sa.Text()),
        sa.Column("idempotency_key", sa.Text(), unique=True),
        sa.Column("created_at", UTCDateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", UTCDateTime()),
        sa.Column("approved_by", BigPk, sa.ForeignKey("users.id")),
        sa.Column("approved_at", UTCDateTime()),
        sa.Column("published_at", UTCDateTime()),
        sa.Column("snapshot", Json),
        sa.Column("baseline", Json),
        sa.Column("plan", Json),
        sa.CheckConstraint("horizon_end > horizon_start", name="ck_plan_runs_horizon"),
        sa.CheckConstraint(f"status IN ({PLAN_STATUSES})", name="ck_plan_runs_status"),
    )
    op.create_table(
        "blocks",
        sa.Column("id", BigPk, primary_key=True, autoincrement=True),
        sa.Column("plan_run_id", BigPk, sa.ForeignKey("plan_runs.id"), nullable=False),
        sa.Column("section_id", BigPk, sa.ForeignKey("sections.id"), nullable=False),
        sa.Column("start_ts", UTCDateTime(), nullable=False),
        sa.Column("end_ts", UTCDateTime(), nullable=False),
        sa.Column("trains_affected", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.Text(), nullable=False, server_default="proposed"),
        sa.CheckConstraint("end_ts > start_ts", name="ck_blocks_window"),
        sa.CheckConstraint(f"status IN ({BLOCK_STATUSES})", name="ck_blocks_status"),
    )
    op.create_index("ix_blocks_section_start", "blocks", ["section_id", "start_ts"])
    op.create_table(
        "plan_assignments",
        sa.Column("id", BigPk, primary_key=True, autoincrement=True),
        sa.Column(
            "plan_run_id",
            BigPk,
            sa.ForeignKey("plan_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("request_id", BigPk, sa.ForeignKey("block_requests.id"), nullable=False),
        sa.Column("block_id", BigPk, sa.ForeignKey("blocks.id")),
        sa.Column("start_ts", UTCDateTime()),
        sa.Column("end_ts", UTCDateTime()),
        sa.Column("deferred", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("defer_reason", sa.Text()),
        sa.Column("overridden", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("plan_run_id", "request_id", name="uq_plan_assignments_run_request"),
    )
    op.create_index("ix_plan_assignments_run", "plan_assignments", ["plan_run_id"])

    if op.get_bind().dialect.name == "postgresql":
        # Database-level backstop for the overlap rule. SQLite has no exclusion constraints,
        # so there the rule is enforced in the publish code only.
        op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
        op.execute(
            "ALTER TABLE blocks ADD CONSTRAINT ex_blocks_published_no_overlap "
            "EXCLUDE USING gist (section_id WITH =, tstzrange(start_ts, end_ts) WITH &&) "
            "WHERE (status = 'published')"
        )


def downgrade() -> None:
    op.drop_index("ix_plan_assignments_run", table_name="plan_assignments")
    op.drop_table("plan_assignments")
    op.drop_index("ix_blocks_section_start", table_name="blocks")
    op.drop_table("blocks")
    op.drop_table("plan_runs")
