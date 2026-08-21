"""add transfer source platform

Revision ID: 20260821_0005
Revises: 20260821_0004
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260821_0005"
down_revision: Union[str, None] = "20260821_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("transactions", sa.Column("source_platform_id", sa.Integer(), sa.ForeignKey("platforms.id"), nullable=True))
    op.create_index(op.f("ix_transactions_source_platform_id"), "transactions", ["source_platform_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_transactions_source_platform_id"), table_name="transactions")
    op.drop_column("transactions", "source_platform_id")
