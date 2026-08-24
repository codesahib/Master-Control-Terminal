"""increase transaction money precision

Revision ID: 20260824_0009
Revises: 20260824_0008
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260824_0009"
down_revision: Union[str, None] = "20260824_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("transactions", "amount", type_=sa.Numeric(18, 6), existing_type=sa.Numeric(14, 2))
    op.alter_column("transactions", "source_amount", type_=sa.Numeric(18, 6), existing_type=sa.Numeric(14, 2))
    op.alter_column("transactions", "fees", type_=sa.Numeric(18, 6), existing_type=sa.Numeric(14, 2))


def downgrade() -> None:
    op.alter_column("transactions", "fees", type_=sa.Numeric(14, 2), existing_type=sa.Numeric(18, 6))
    op.alter_column("transactions", "source_amount", type_=sa.Numeric(14, 2), existing_type=sa.Numeric(18, 6))
    op.alter_column("transactions", "amount", type_=sa.Numeric(14, 2), existing_type=sa.Numeric(18, 6))
