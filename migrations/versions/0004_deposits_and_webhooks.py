"""deposits and webhooks

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "processed_webhooks",
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("event_id", name=op.f("pk_processed_webhooks")),
    )
    op.create_table(
        "deposits",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_deposits_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_deposits")),
    )
    op.create_index(op.f("ix_deposits_user_id"), "deposits", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_deposits_user_id"), table_name="deposits")
    op.drop_table("deposits")
    op.drop_table("processed_webhooks")
