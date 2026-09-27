"""Initial schema managed by Alembic.

Revision ID: 20260623_0001
Revises:
Create Date: 2026-06-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260623_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

transaction_type = postgresql.ENUM(
    "contribution",
    "investment_buy",
    "investment_sell",
    "transfer",
    "dividend_interest",
    name="transactiontype",
    create_type=False,
)
import_type = postgresql.ENUM("contributions", "holdings", name="importtype", create_type=False)
import_status = postgresql.ENUM("parsed", "committed", "failed", name="importstatus", create_type=False)


def _has_table(table_name: str) -> bool:
    bind = op.get_bind()
    return sa.inspect(bind).has_table(table_name)


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(table_name):
        return False
    columns = sa.inspect(bind).get_columns(table_name)
    return any(column["name"] == column_name for column in columns)


def upgrade() -> None:
    bind = op.get_bind()
    transaction_type.create(bind, checkfirst=True)
    import_type.create(bind, checkfirst=True)
    import_status.create(bind, checkfirst=True)

    if not _has_table("accounts"):
        op.create_table(
            "accounts",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=100), nullable=False),
        )
        op.create_index(op.f("ix_accounts_name"), "accounts", ["name"], unique=True)

    if not _has_table("platforms"):
        op.create_table(
            "platforms",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("canonical_name", sa.String(length=100), nullable=False),
        )
        op.create_index(op.f("ix_platforms_canonical_name"), "platforms", ["canonical_name"], unique=True)

    if not _has_table("platform_aliases"):
        op.create_table(
            "platform_aliases",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("alias", sa.String(length=100), nullable=False),
            sa.Column("platform_id", sa.Integer(), sa.ForeignKey("platforms.id", ondelete="CASCADE"), nullable=False),
        )
        op.create_index(op.f("ix_platform_aliases_alias"), "platform_aliases", ["alias"], unique=True)
        op.create_index(op.f("ix_platform_aliases_platform_id"), "platform_aliases", ["platform_id"])

    if not _has_table("categories"):
        op.create_table(
            "categories",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("broad", sa.String(length=100), nullable=False),
            sa.Column("precise", sa.String(length=100), nullable=False),
        )
        op.create_index(op.f("ix_categories_broad"), "categories", ["broad"])
        op.create_index(op.f("ix_categories_precise"), "categories", ["precise"])

    if not _has_table("instruments"):
        op.create_table(
            "instruments",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("symbol", sa.String(length=50), nullable=False),
            sa.Column("name", sa.String(length=200), nullable=True),
            sa.Column("category_id", sa.Integer(), sa.ForeignKey("categories.id"), nullable=True),
        )
        op.create_index(op.f("ix_instruments_symbol"), "instruments", ["symbol"], unique=True)

    if not _has_table("contribution_limits"):
        op.create_table(
            "contribution_limits",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
            sa.Column("tax_year", sa.String(length=4), nullable=False),
            sa.Column("new_room", sa.Numeric(14, 2), nullable=False),
        )
        op.create_index(op.f("ix_contribution_limits_account_id"), "contribution_limits", ["account_id"])
        op.create_index(op.f("ix_contribution_limits_tax_year"), "contribution_limits", ["tax_year"])

    if not _has_table("transactions"):
        op.create_table(
            "transactions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("transaction_type", transaction_type, nullable=False),
            sa.Column("transaction_date", sa.Date(), nullable=False),
            sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id"), nullable=True),
            sa.Column("platform_id", sa.Integer(), sa.ForeignKey("platforms.id"), nullable=True),
            sa.Column("instrument_id", sa.Integer(), sa.ForeignKey("instruments.id"), nullable=True),
            sa.Column("category_id", sa.Integer(), sa.ForeignKey("categories.id"), nullable=True),
            sa.Column("amount", sa.Numeric(14, 2), nullable=False),
            sa.Column("quantity", sa.Float(), nullable=True),
            sa.Column("fees", sa.Numeric(14, 2), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("reversal_of_id", sa.Integer(), sa.ForeignKey("transactions.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        for column in ["transaction_type", "transaction_date", "account_id", "platform_id", "instrument_id", "category_id"]:
            op.create_index(op.f(f"ix_transactions_{column}"), "transactions", [column])

    if not _has_table("holdings_snapshots"):
        op.create_table(
            "holdings_snapshots",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("snapshot_date", sa.Date(), nullable=False),
            sa.Column("snapshot_year", sa.Integer(), nullable=True),
            sa.Column("snapshot_type", sa.String(length=20), nullable=False, server_default="current"),
            sa.Column("holding_date", sa.Date(), nullable=True),
            sa.Column("record_type", sa.String(length=20), nullable=False, server_default="holding"),
            sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id"), nullable=True),
            sa.Column("platform_id", sa.Integer(), sa.ForeignKey("platforms.id"), nullable=True),
            sa.Column("instrument_id", sa.Integer(), sa.ForeignKey("instruments.id"), nullable=True),
            sa.Column("category_id", sa.Integer(), sa.ForeignKey("categories.id"), nullable=True),
            sa.Column("market_value", sa.Numeric(14, 2), nullable=False),
        )
        for column in ["snapshot_date", "snapshot_year", "snapshot_type", "holding_date", "record_type", "account_id", "platform_id", "instrument_id", "category_id"]:
            op.create_index(op.f(f"ix_holdings_snapshots_{column}"), "holdings_snapshots", [column])
    else:
        if not _has_column("holdings_snapshots", "snapshot_year"):
            op.add_column("holdings_snapshots", sa.Column("snapshot_year", sa.Integer(), nullable=True))
            op.create_index(op.f("ix_holdings_snapshots_snapshot_year"), "holdings_snapshots", ["snapshot_year"])
        if not _has_column("holdings_snapshots", "snapshot_type"):
            op.add_column("holdings_snapshots", sa.Column("snapshot_type", sa.String(length=20), nullable=False, server_default="current"))
            op.create_index(op.f("ix_holdings_snapshots_snapshot_type"), "holdings_snapshots", ["snapshot_type"])
        if not _has_column("holdings_snapshots", "holding_date"):
            op.add_column("holdings_snapshots", sa.Column("holding_date", sa.Date(), nullable=True))
            op.create_index(op.f("ix_holdings_snapshots_holding_date"), "holdings_snapshots", ["holding_date"])
        if not _has_column("holdings_snapshots", "record_type"):
            op.add_column("holdings_snapshots", sa.Column("record_type", sa.String(length=20), nullable=False, server_default="holding"))
            op.create_index(op.f("ix_holdings_snapshots_record_type"), "holdings_snapshots", ["record_type"])

    if not _has_table("imports"):
        op.create_table(
            "imports",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("import_type", import_type, nullable=False),
            sa.Column("source_filename", sa.String(length=255), nullable=False),
            sa.Column("status", import_status, nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index(op.f("ix_imports_import_type"), "imports", ["import_type"])

    if not _has_table("import_rows"):
        op.create_table(
            "import_rows",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("import_id", sa.Integer(), sa.ForeignKey("imports.id", ondelete="CASCADE"), nullable=False),
            sa.Column("row_number", sa.Integer(), nullable=False),
            sa.Column("payload_json", sa.Text(), nullable=False),
            sa.Column("error", sa.Text(), nullable=True),
        )
        op.create_index(op.f("ix_import_rows_import_id"), "import_rows", ["import_id"])


def downgrade() -> None:
    for table in [
        "import_rows",
        "imports",
        "holdings_snapshots",
        "transactions",
        "contribution_limits",
        "instruments",
        "categories",
        "platform_aliases",
        "platforms",
        "accounts",
    ]:
        if _has_table(table):
            op.drop_table(table)
    import_status.drop(op.get_bind(), checkfirst=True)
    import_type.drop(op.get_bind(), checkfirst=True)
    transaction_type.drop(op.get_bind(), checkfirst=True)
