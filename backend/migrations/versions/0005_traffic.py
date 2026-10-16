"""timetable_entries, traffic_profile

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-17
"""
import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

BigPk = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
CATEGORIES = "'premium', 'mail', 'passenger', 'local', 'freight'"


def upgrade() -> None:
    op.create_table(
        "timetable_entries",
        sa.Column("id", BigPk, primary_key=True, autoincrement=True),
        sa.Column("train_no", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("weight", sa.SmallInteger(), nullable=False, server_default="1"),
        sa.Column("section_id", BigPk, sa.ForeignKey("sections.id"), nullable=False),
        sa.Column("days_of_week", sa.SmallInteger(), nullable=False, server_default="127"),
        sa.Column("enters_at", sa.Time(), nullable=False),
        sa.Column("leaves_at", sa.Time(), nullable=False),
        sa.CheckConstraint(f"category IN ({CATEGORIES})", name="ck_timetable_entries_category"),
        sa.CheckConstraint("days_of_week BETWEEN 1 AND 127", name="ck_timetable_entries_days"),
    )
    op.create_table(
        "traffic_profile",
        sa.Column(
            "section_id", BigPk, sa.ForeignKey("sections.id"), primary_key=True, autoincrement=False
        ),
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("slot_index", sa.SmallInteger(), primary_key=True, autoincrement=False),
        sa.Column("trains", sa.SmallInteger(), nullable=False),
        sa.Column("weighted", sa.Integer(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("traffic_profile")
    op.drop_table("timetable_entries")
