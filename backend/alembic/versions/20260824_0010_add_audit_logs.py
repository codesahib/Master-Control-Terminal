"""add audit logs

Revision ID: 20260824_0010
Revises: 20260824_0009
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260824_0010"
down_revision: Union[str, None] = "20260824_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("operation", sa.String(length=20), nullable=False),
        sa.Column("table_name", sa.String(length=100), nullable=False),
        sa.Column("row_id", sa.String(length=100), nullable=True),
        sa.Column("summary", sa.String(length=255), nullable=True),
        sa.Column("before_json", sa.Text(), nullable=True),
        sa.Column("after_json", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=100), nullable=True),
    )
    for column in ["created_at", "operation", "table_name", "row_id"]:
        op.create_index(op.f(f"ix_audit_logs_{column}"), "audit_logs", [column])


def downgrade() -> None:
    op.drop_table("audit_logs")
