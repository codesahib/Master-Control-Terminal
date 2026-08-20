"""add contribution funding reference

Revision ID: 20260821_0002
Revises: 20260623_0001
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260821_0002"
down_revision: Union[str, None] = "20260623_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("transactions", sa.Column("contribution_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_transactions_contribution_id", "transactions", "transactions", ["contribution_id"], ["id"]
    )
    op.create_index(op.f("ix_transactions_contribution_id"), "transactions", ["contribution_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_transactions_contribution_id"), table_name="transactions")
    op.drop_constraint("fk_transactions_contribution_id", "transactions", type_="foreignkey")
    op.drop_column("transactions", "contribution_id")
