"""add sync state

Revision ID: 20260824_0011
Revises: 20260824_0010
Create Date: 2026-08-24 00:11:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260824_0011"
down_revision: Union[str, None] = "20260824_0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "sync_state" in inspector.get_table_names():
        return
    op.create_table(
        "sync_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("database_id", sa.String(length=36), nullable=False),
        sa.Column("last_write_at", sa.DateTime(), nullable=True),
        sa.Column("last_push_at", sa.DateTime(), nullable=True),
        sa.Column("last_pull_at", sa.DateTime(), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(), nullable=True),
        sa.Column("last_sync_direction", sa.String(length=20), nullable=True),
        sa.Column("last_sync_status", sa.String(length=20), nullable=True),
        sa.Column("last_sync_error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("database_id"),
    )
    op.create_index(op.f("ix_sync_state_last_write_at"), "sync_state", ["last_write_at"], unique=False)


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "sync_state" not in inspector.get_table_names():
        return
    op.drop_index(op.f("ix_sync_state_last_write_at"), table_name="sync_state")
    op.drop_table("sync_state")
