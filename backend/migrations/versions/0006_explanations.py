"""explanations

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-17
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

BigPk = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
Json = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "explanations",
        sa.Column("id", BigPk, primary_key=True, autoincrement=True),
        sa.Column(
            "plan_run_id",
            BigPk,
            sa.ForeignKey("plan_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("block_id", BigPk, sa.ForeignKey("blocks.id")),
        sa.Column("request_id", BigPk, sa.ForeignKey("block_requests.id")),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("numbers", Json, nullable=False, server_default=sa.text("'{}'")),
    )
    op.create_index("ix_explanations_run", "explanations", ["plan_run_id"])


def downgrade() -> None:
    op.drop_index("ix_explanations_run", table_name="explanations")
    op.drop_table("explanations")
