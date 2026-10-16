"""block_requests, request_dependencies, audit_log

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-17
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.db.base import UTCDateTime

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

SmallPk = sa.SmallInteger().with_variant(sa.Integer(), "sqlite")
BigPk = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
Json = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")

STATUSES = "'draft', 'submitted', 'scheduled', 'published', 'completed', 'cancelled', 'rejected'"
RELATIONS = "'finish_before_start', 'not_same_block', 'same_block_allowed'"


def upgrade() -> None:
    op.create_table(
        "block_requests",
        sa.Column("id", BigPk, primary_key=True, autoincrement=True),
        sa.Column("department_id", SmallPk, sa.ForeignKey("departments.id"), nullable=False),
        sa.Column("section_id", BigPk, sa.ForeignKey("sections.id"), nullable=False),
        sa.Column("requested_by", BigPk, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("work_type", sa.Text(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("earliest_date", sa.Date(), nullable=False),
        sa.Column("deadline_date", sa.Date(), nullable=False),
        sa.Column("priority", sa.SmallInteger(), nullable=False),
        sa.Column("needs_power_block", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("preferred_start", UTCDateTime()),
        sa.Column("status", sa.Text(), nullable=False, server_default="draft"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", UTCDateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", UTCDateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("duration_minutes BETWEEN 15 AND 720", name="ck_block_requests_duration"),
        sa.CheckConstraint("priority BETWEEN 1 AND 3", name="ck_block_requests_priority"),
        sa.CheckConstraint("deadline_date >= earliest_date", name="ck_block_requests_dates"),
        sa.CheckConstraint(f"status IN ({STATUSES})", name="ck_block_requests_status"),
    )
    op.create_index(
        "ix_block_requests_status_section", "block_requests", ["status", "section_id"]
    )
    op.create_table(
        "request_dependencies",
        sa.Column(
            "request_id",
            BigPk,
            sa.ForeignKey("block_requests.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "depends_on_request_id",
            BigPk,
            sa.ForeignKey("block_requests.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("relation", sa.Text(), nullable=False),
        sa.Column("min_gap_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint(f"relation IN ({RELATIONS})", name="ck_request_dependencies_relation"),
        sa.CheckConstraint(
            "request_id <> depends_on_request_id", name="ck_request_dependencies_not_self"
        ),
    )
    op.create_table(
        "audit_log",
        sa.Column("id", BigPk, primary_key=True, autoincrement=True),
        sa.Column("ts", UTCDateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("user_id", BigPk, sa.ForeignKey("users.id")),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("entity", sa.Text(), nullable=False),
        sa.Column("entity_id", sa.BigInteger()),
        sa.Column("details", Json, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("request_dependencies")
    op.drop_index("ix_block_requests_status_section", table_name="block_requests")
    op.drop_table("block_requests")
