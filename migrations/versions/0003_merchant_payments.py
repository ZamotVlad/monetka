"""merchant payments

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "merchants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("api_key_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_merchants")),
        sa.UniqueConstraint("api_key_hash", name=op.f("uq_merchants_api_key_hash")),
    )
    op.create_table(
        "payments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("merchant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("description", sa.String(length=140), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["merchant_id"], ["merchants.id"], name=op.f("fk_payments_merchant_id_merchants")
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_payments_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payments")),
    )
    op.create_index(op.f("ix_payments_merchant_id"), "payments", ["merchant_id"], unique=False)
    op.create_index(
        "ix_payments_status_expires_at", "payments", ["status", "expires_at"], unique=False
    )
    op.create_index(op.f("ix_payments_user_id"), "payments", ["user_id"], unique=False)
    op.add_column("accounts", sa.Column("merchant_id", sa.Uuid(), nullable=True))
    op.create_unique_constraint(op.f("uq_accounts_merchant_id"), "accounts", ["merchant_id"])
    op.create_foreign_key(
        op.f("fk_accounts_merchant_id_merchants"), "accounts", "merchants", ["merchant_id"], ["id"]
    )
    op.add_column("ledger_transactions", sa.Column("payment_id", sa.Uuid(), nullable=True))
    op.create_index(
        op.f("ix_ledger_transactions_payment_id"),
        "ledger_transactions",
        ["payment_id"],
        unique=False,
    )
    op.create_foreign_key(
        op.f("fk_ledger_transactions_payment_id_payments"),
        "ledger_transactions",
        "payments",
        ["payment_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_ledger_transactions_payment_id_payments"),
        "ledger_transactions",
        type_="foreignkey",
    )
    op.drop_index(op.f("ix_ledger_transactions_payment_id"), table_name="ledger_transactions")
    op.drop_column("ledger_transactions", "payment_id")
    op.drop_constraint(op.f("fk_accounts_merchant_id_merchants"), "accounts", type_="foreignkey")
    op.drop_constraint(op.f("uq_accounts_merchant_id"), "accounts", type_="unique")
    op.drop_column("accounts", "merchant_id")
    op.drop_index(op.f("ix_payments_user_id"), table_name="payments")
    op.drop_index("ix_payments_status_expires_at", table_name="payments")
    op.drop_index(op.f("ix_payments_merchant_id"), table_name="payments")
    op.drop_table("payments")
    op.drop_table("merchants")
