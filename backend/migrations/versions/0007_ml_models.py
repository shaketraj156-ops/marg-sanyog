"""ml_models

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-17
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.db.base import UTCDateTime

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

BigPk = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
Json = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "ml_models",
        sa.Column("id", BigPk, primary_key=True, autoincrement=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("metrics", Json, nullable=False),
        sa.Column("artifact_path", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("trained_by", BigPk, sa.ForeignKey("users.id")),
        sa.Column("created_at", UTCDateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("kind IN ('delay', 'overrun')", name="ck_ml_models_kind"),
        sa.UniqueConstraint("kind", "version", name="uq_ml_models_kind_version"),
    )
    op.create_index(
        "uq_ml_models_one_active",
        "ml_models",
        ["kind"],
        unique=True,
        sqlite_where=sa.text("is_active"),
        postgresql_where=sa.text("is_active"),
    )


def downgrade() -> None:
    op.drop_index("uq_ml_models_one_active", table_name="ml_models")
    op.drop_table("ml_models")
