"""add dividend reinvestment transaction type

Revision ID: 20260821_0003
Revises: 20260821_0002
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20260821_0003"
down_revision: Union[str, None] = "20260821_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TYPE transactiontype ADD VALUE IF NOT EXISTS 'dividend_reinvestment'")


def downgrade() -> None:
    pass
