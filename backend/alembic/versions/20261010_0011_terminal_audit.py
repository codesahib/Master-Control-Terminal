"""Terminal audit schema: dedupe + constraints, exact numeric types, timestamptz,
withdrawal type, portfolio snapshots, drop legacy funding and spreadsheet imports, RLS.

Revision ID: 20261010_0011
Revises: 20260824_0010
Create Date: 2026-10-10

Postgres only (production and docker both run Postgres; unit tests use create_all).
"""

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261010_0011"
down_revision: Union[str, None] = "20260824_0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

log = logging.getLogger("alembic.runtime.migration")

APP_TABLES = [
    "accounts",
    "platforms",
    "platform_aliases",
    "categories",
    "instruments",
    "market_prices",
    "contribution_limits",
    "transactions",
    "transaction_fundings",
    "holdings_snapshots",
    "audit_logs",
    "portfolio_snapshots",
    "alembic_version",
]
TIMESTAMP_COLUMNS = [
    ("transactions", "created_at"),
    ("market_prices", "priced_at"),
    ("market_prices", "created_at"),
    ("audit_logs", "created_at"),
]
PORTABLE_CHECKS = [
    ("ck_transactions_amount_non_negative", "transactions", "amount >= 0"),
    ("ck_transactions_fees_non_negative", "transactions", "fees IS NULL OR fees >= 0"),
    ("ck_transactions_source_amount_non_negative", "transactions", "source_amount IS NULL OR source_amount >= 0"),
    ("ck_transaction_fundings_amount_positive", "transaction_fundings", "amount > 0"),
    ("ck_contribution_limits_new_room_non_negative", "contribution_limits", "new_room >= 0"),
    ("ck_market_prices_price_non_negative", "market_prices", "price >= 0"),
    # "unused" snapshot rows track contribution room and can be negative.
    ("ck_holdings_snapshots_holding_value_non_negative", "holdings_snapshots", "record_type <> 'holding' OR market_value >= 0"),
]
POSTGRES_CHECKS = [
    ("ck_transactions_currency_format", "transactions", "currency ~ '^[A-Z]{3}$'"),
    ("ck_transactions_source_currency_format", "transactions", "source_currency IS NULL OR source_currency ~ '^[A-Z]{3}$'"),
    ("ck_transactions_fee_currency_format", "transactions", "fee_currency IS NULL OR fee_currency ~ '^[A-Z]{3}$'"),
]


def _require_zero(sql: str, message: str) -> None:
    count = op.get_bind().execute(sa.text(sql)).scalar()
    if count:
        raise RuntimeError(f"{count} {message}; resolve them before running 20261010_0011")


def _execute(sql: str, label: str | None = None) -> None:
    result = op.get_bind().execute(sa.text(sql))
    if label:
        log.info("%s: %s rows", label, result.rowcount)


def upgrade() -> None:
    # Refuse to lose data: every row this migration drops or rewrites must be safe to drop.
    _require_zero("SELECT count(*) FROM transactions WHERE account_id IS NULL", "transactions have no account_id")
    _require_zero(
        "SELECT count(*) FROM transactions WHERE reversal_of_id IS NOT NULL",
        "transactions use reversal_of_id (column is dropped)",
    )
    _require_zero("SELECT count(*) FROM imports", "imports rows exist (table is dropped)")
    _require_zero("SELECT count(*) FROM import_rows", "import_rows rows exist (table is dropped)")
    _require_zero(
        """
        SELECT count(*) FROM (
            SELECT 1 FROM contribution_limits GROUP BY account_id, tax_year HAVING count(DISTINCT new_room) > 1
        ) conflicting
        """,
        "(account, tax_year) pairs have contribution_limits rows with different new_room values",
    )

    # 1. Dedupe, then unique constraints.
    _execute(
        """
        DELETE FROM contribution_limits a USING contribution_limits b
        WHERE a.account_id = b.account_id AND a.tax_year = b.tax_year AND a.new_room = b.new_room AND a.id < b.id
        """,
        "contribution_limits duplicates removed",
    )
    op.create_unique_constraint("uq_contribution_limits_account_tax_year", "contribution_limits", ["account_id", "tax_year"])

    _execute(
        """
        CREATE TEMP TABLE category_remap ON COMMIT DROP AS
        SELECT c.id AS old_id, k.keep_id
        FROM categories c
        JOIN (
            SELECT lower(broad) AS broad, lower(precise) AS precise, min(id) AS keep_id
            FROM categories GROUP BY 1, 2
        ) k ON lower(c.broad) = k.broad AND lower(c.precise) = k.precise
        WHERE c.id <> k.keep_id
        """
    )
    for table in ["transactions", "instruments", "holdings_snapshots"]:
        _execute(
            f"UPDATE {table} t SET category_id = r.keep_id FROM category_remap r WHERE t.category_id = r.old_id",
            f"{table} category ids remapped",
        )
    _execute("DELETE FROM categories c USING category_remap r WHERE c.id = r.old_id", "categories duplicates removed")
    op.create_unique_constraint("uq_categories_broad_precise", "categories", ["broad", "precise"])

    # priced_at is still naive UTC here, so ::date is the UTC day.
    _execute(
        """
        DELETE FROM market_prices m USING (
            SELECT id, row_number() OVER (
                PARTITION BY instrument_id, priced_at::date ORDER BY priced_at DESC, id DESC
            ) AS rn
            FROM market_prices
        ) d
        WHERE m.id = d.id AND d.rn > 1
        """,
        "market_prices same-day duplicates removed",
    )

    # 2. Types.
    op.alter_column(
        "transactions", "quantity", type_=sa.Numeric(20, 8), existing_type=sa.Float(),
        postgresql_using="quantity::numeric(20,8)",
    )
    op.alter_column("transaction_fundings", "amount", type_=sa.Numeric(18, 6), existing_type=sa.Numeric(14, 2))
    for table, column in TIMESTAMP_COLUMNS:
        op.alter_column(
            table, column, type_=sa.DateTime(timezone=True), existing_type=sa.DateTime(),
            postgresql_using=f"{column} AT TIME ZONE 'UTC'",
        )

    # The composite unique index leads with instrument_id and serves the latest-price lookup.
    op.drop_index("ix_market_prices_instrument_id", table_name="market_prices")
    op.create_unique_constraint("uq_market_prices_instrument_priced_at", "market_prices", ["instrument_id", "priced_at"])

    # 4. Withdrawal transaction type (not used inside this migration, so no autocommit block needed).
    op.execute("ALTER TYPE transactiontype ADD VALUE IF NOT EXISTS 'withdrawal'")

    # 5. Daily portfolio value snapshots.
    op.create_table(
        "portfolio_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("book_value", sa.Numeric(18, 2), nullable=False),
        sa.Column("market_value", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("snapshot_date", "account_id", name="uq_portfolio_snapshots_date_account"),
    )
    op.create_index(op.f("ix_portfolio_snapshots_snapshot_date"), "portfolio_snapshots", ["snapshot_date"])
    op.create_index(op.f("ix_portfolio_snapshots_account_id"), "portfolio_snapshots", ["account_id"])

    # 6. Legacy single-funding column → transaction_fundings (the old code counted only investment buys),
    # then drop legacy columns and import tables.
    _execute(
        """
        INSERT INTO transaction_fundings (transaction_id, contribution_id, amount)
        SELECT t.id, t.contribution_id, t.amount + COALESCE(t.fees, 0)
        FROM transactions t
        WHERE t.contribution_id IS NOT NULL
          AND t.transaction_type = 'investment_buy'
          AND t.amount + COALESCE(t.fees, 0) > 0
          AND NOT EXISTS (SELECT 1 FROM transaction_fundings f WHERE f.transaction_id = t.id)
        """,
        "transaction_fundings backfilled from transactions.contribution_id",
    )
    op.drop_column("transactions", "contribution_id")  # also drops its FK and index
    op.drop_column("transactions", "reversal_of_id")
    op.drop_table("import_rows")
    op.drop_table("imports")
    op.execute("DROP TYPE IF EXISTS importstatus")
    op.execute("DROP TYPE IF EXISTS importtype")

    # 3. Checks and NOT NULL (after backfill so the funding check sees final rows).
    for name, table, condition in PORTABLE_CHECKS + POSTGRES_CHECKS:
        op.create_check_constraint(name, table, condition)
    op.alter_column("transactions", "account_id", existing_type=sa.Integer(), nullable=False)

    # 7. Row-level security with no policies: the owning role (the app) bypasses it,
    # the Supabase Data API roles (anon/authenticated) get nothing.
    for table in APP_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    bind = op.get_bind()
    withdrawals = bind.execute(sa.text("SELECT count(*) FROM transactions WHERE transaction_type = 'withdrawal'")).scalar()
    if withdrawals:
        raise RuntimeError(f"{withdrawals} withdrawal transactions exist; the previous schema cannot represent them")

    for table in APP_TABLES:
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.alter_column("transactions", "account_id", existing_type=sa.Integer(), nullable=True)
    for name, table, _condition in PORTABLE_CHECKS + POSTGRES_CHECKS:
        op.drop_constraint(name, table, type_="check")

    import_type = postgresql.ENUM("contributions", "holdings", name="importtype")
    import_status = postgresql.ENUM("parsed", "committed", "failed", name="importstatus")
    import_type.create(bind, checkfirst=True)
    import_status.create(bind, checkfirst=True)
    op.create_table(
        "imports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("import_type", postgresql.ENUM(name="importtype", create_type=False), nullable=False),
        sa.Column("source_filename", sa.String(length=255), nullable=False),
        sa.Column("status", postgresql.ENUM(name="importstatus", create_type=False), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(op.f("ix_imports_import_type"), "imports", ["import_type"])
    op.create_table(
        "import_rows",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("import_id", sa.Integer(), sa.ForeignKey("imports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index(op.f("ix_import_rows_import_id"), "import_rows", ["import_id"])

    # Funding rows stay the source of truth; the old code only read contribution_id when no funding row existed.
    op.add_column("transactions", sa.Column("reversal_of_id", sa.Integer(), sa.ForeignKey("transactions.id"), nullable=True))
    op.add_column("transactions", sa.Column("contribution_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_transactions_contribution_id", "transactions", "transactions", ["contribution_id"], ["id"])
    op.create_index(op.f("ix_transactions_contribution_id"), "transactions", ["contribution_id"])

    op.drop_index(op.f("ix_portfolio_snapshots_account_id"), table_name="portfolio_snapshots")
    op.drop_index(op.f("ix_portfolio_snapshots_snapshot_date"), table_name="portfolio_snapshots")
    op.drop_table("portfolio_snapshots")
    # Postgres cannot drop an enum value; 'withdrawal' stays unused in transactiontype.

    op.drop_constraint("uq_market_prices_instrument_priced_at", "market_prices", type_="unique")
    op.create_index("ix_market_prices_instrument_id", "market_prices", ["instrument_id"])
    for table, column in TIMESTAMP_COLUMNS:
        op.alter_column(
            table, column, type_=sa.DateTime(), existing_type=sa.DateTime(timezone=True),
            postgresql_using=f"{column} AT TIME ZONE 'UTC'",
        )
    op.alter_column("transaction_fundings", "amount", type_=sa.Numeric(14, 2), existing_type=sa.Numeric(18, 6))
    op.alter_column(
        "transactions", "quantity", type_=sa.Float(), existing_type=sa.Numeric(20, 8),
        postgresql_using="quantity::double precision",
    )
    op.drop_constraint("uq_categories_broad_precise", "categories", type_="unique")
    op.drop_constraint("uq_contribution_limits_account_tax_year", "contribution_limits", type_="unique")
