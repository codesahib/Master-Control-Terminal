"""add transaction currencies and currency exchanges

Revision ID: 20260822_0007
Revises: 20260822_0006
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260822_0007"
down_revision: Union[str, None] = "20260822_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TYPE transactiontype ADD VALUE IF NOT EXISTS 'currency_exchange'")
    op.add_column("transactions", sa.Column("currency", sa.String(length=3), nullable=False, server_default="CAD"))
    op.add_column("transactions", sa.Column("source_amount", sa.Numeric(14, 2), nullable=True))
    op.add_column("transactions", sa.Column("source_currency", sa.String(length=3), nullable=True))
    op.add_column("transactions", sa.Column("fee_currency", sa.String(length=3), nullable=True))
    op.alter_column("transactions", "currency", server_default=None)


def downgrade() -> None:
    op.drop_column("transactions", "fee_currency")
    op.drop_column("transactions", "source_currency")
    op.drop_column("transactions", "source_amount")
    op.drop_column("transactions", "currency")
