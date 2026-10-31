"""statements

Revision ID: 0006
Revises: 0005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "statements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("period", sa.String(length=7), nullable=False),
        sa.Column("object_key", sa.String(length=255), nullable=False),
        sa.Column("rows", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_statements_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_statements")),
        sa.UniqueConstraint("user_id", "period", name=op.f("uq_statements_user_id")),
    )
    op.create_index(op.f("ix_statements_user_id"), "statements", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_statements_user_id"), table_name="statements")
    op.drop_table("statements")
