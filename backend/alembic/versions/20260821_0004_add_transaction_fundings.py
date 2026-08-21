"""add multi-contribution transaction funding

Revision ID: 20260821_0004
Revises: 20260821_0003
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260821_0004"
down_revision: Union[str, None] = "20260821_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "transaction_fundings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("transaction_id", sa.Integer(), sa.ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("contribution_id", sa.Integer(), sa.ForeignKey("transactions.id"), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.UniqueConstraint("transaction_id", "contribution_id", name="uq_transaction_fundings_transaction_contribution"),
    )
    op.create_index(op.f("ix_transaction_fundings_transaction_id"), "transaction_fundings", ["transaction_id"])
    op.create_index(op.f("ix_transaction_fundings_contribution_id"), "transaction_fundings", ["contribution_id"])
    op.execute(
        """
        INSERT INTO transaction_fundings (transaction_id, contribution_id, amount)
        SELECT id, contribution_id, amount + COALESCE(fees, 0)
        FROM transactions
        WHERE contribution_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE transactions
        SET contribution_id = (
            SELECT contribution_id
            FROM transaction_fundings
            WHERE transaction_id = transactions.id
            ORDER BY id
            LIMIT 1
        )
        WHERE contribution_id IS NULL
        """
    )
    op.drop_index(op.f("ix_transaction_fundings_contribution_id"), table_name="transaction_fundings")
    op.drop_index(op.f("ix_transaction_fundings_transaction_id"), table_name="transaction_fundings")
    op.drop_table("transaction_fundings")
