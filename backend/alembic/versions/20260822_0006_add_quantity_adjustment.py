"""add quantity adjustment transaction type

Revision ID: 20260822_0006
Revises: 20260821_0005
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20260822_0006"
down_revision: Union[str, None] = "20260821_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TYPE transactiontype ADD VALUE IF NOT EXISTS 'quantity_adjustment'")


def downgrade() -> None:
    pass
