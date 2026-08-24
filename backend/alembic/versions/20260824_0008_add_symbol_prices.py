"""add normalized instrument metadata and market prices

Revision ID: 20260824_0008
Revises: 20260822_0007
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260824_0008"
down_revision: Union[str, None] = "20260822_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("instruments", sa.Column("provider_symbol", sa.String(length=80), nullable=True))
    op.add_column("instruments", sa.Column("exchange", sa.String(length=80), nullable=True))
    op.add_column("instruments", sa.Column("currency", sa.String(length=3), nullable=True))
    op.add_column("instruments", sa.Column("asset_type", sa.String(length=50), nullable=True))
    op.add_column("instruments", sa.Column("provider", sa.String(length=50), nullable=True))
    op.add_column("instruments", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.create_index("ix_instruments_provider_symbol", "instruments", ["provider_symbol"])
    op.execute("UPDATE instruments SET provider = 'yfinance', provider_symbol = symbol WHERE provider_symbol IS NULL")
    op.alter_column("instruments", "is_active", server_default=None)

    op.create_table(
        "market_prices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("price", sa.Numeric(14, 4), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("priced_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_market_prices_instrument_id", "market_prices", ["instrument_id"])
    op.create_index("ix_market_prices_priced_at", "market_prices", ["priced_at"])


def downgrade() -> None:
    op.drop_index("ix_market_prices_priced_at", table_name="market_prices")
    op.drop_index("ix_market_prices_instrument_id", table_name="market_prices")
    op.drop_table("market_prices")
    op.drop_index("ix_instruments_provider_symbol", table_name="instruments")
    op.drop_column("instruments", "is_active")
    op.drop_column("instruments", "provider")
    op.drop_column("instruments", "asset_type")
    op.drop_column("instruments", "currency")
    op.drop_column("instruments", "exchange")
    op.drop_column("instruments", "provider_symbol")
