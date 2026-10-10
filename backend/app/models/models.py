import enum
from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import utcnow
from app.db.session import Base


class TransactionType(str, enum.Enum):
    contribution = "contribution"
    investment_buy = "investment_buy"
    investment_sell = "investment_sell"
    transfer = "transfer"
    dividend_interest = "dividend_interest"
    dividend_reinvestment = "dividend_reinvestment"
    quantity_adjustment = "quantity_adjustment"
    currency_exchange = "currency_exchange"
    withdrawal = "withdrawal"


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)


class Platform(Base):
    __tablename__ = "platforms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String(100), unique=True, index=True)


class PlatformAlias(Base):
    __tablename__ = "platform_aliases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alias: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    platform_id: Mapped[int] = mapped_column(ForeignKey("platforms.id", ondelete="CASCADE"), index=True)


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("broad", "precise", name="uq_categories_broad_precise"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    broad: Mapped[str] = mapped_column(String(100), index=True)
    precise: Mapped[str] = mapped_column(String(100), index=True)


class Instrument(Base):
    __tablename__ = "instruments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    provider_symbol: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    exchange: Mapped[str | None] = mapped_column(String(80), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    asset_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), nullable=True)


class MarketPrice(Base):
    __tablename__ = "market_prices"
    # ponytail: the unique index (instrument_id, priced_at) also serves the latest-price lookup; no separate DESC index.
    __table_args__ = (
        UniqueConstraint("instrument_id", "priced_at", name="uq_market_prices_instrument_priced_at"),
        CheckConstraint("price >= 0", name="ck_market_prices_price_non_negative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id", ondelete="CASCADE"))
    price: Mapped[float] = mapped_column(Numeric(14, 4))
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    provider: Mapped[str] = mapped_column(String(50), default="yfinance")
    priced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ContributionLimit(Base):
    __tablename__ = "contribution_limits"
    __table_args__ = (
        UniqueConstraint("account_id", "tax_year", name="uq_contribution_limits_account_tax_year"),
        CheckConstraint("new_room >= 0", name="ck_contribution_limits_new_room_non_negative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    tax_year: Mapped[str] = mapped_column(String(4), index=True)
    new_room: Mapped[float] = mapped_column(Numeric(14, 2), default=0)


class Transaction(Base):
    __tablename__ = "transactions"
    # Currency format checks are Postgres-only and live in migration 20261010_0011.
    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_transactions_amount_non_negative"),
        CheckConstraint("fees IS NULL OR fees >= 0", name="ck_transactions_fees_non_negative"),
        CheckConstraint("source_amount IS NULL OR source_amount >= 0", name="ck_transactions_source_amount_non_negative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    transaction_type: Mapped[TransactionType] = mapped_column(Enum(TransactionType), index=True)
    transaction_date: Mapped[date] = mapped_column(Date, index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    platform_id: Mapped[int | None] = mapped_column(ForeignKey("platforms.id"), nullable=True, index=True)
    source_platform_id: Mapped[int | None] = mapped_column(ForeignKey("platforms.id"), nullable=True, index=True)
    instrument_id: Mapped[int | None] = mapped_column(ForeignKey("instruments.id"), nullable=True, index=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), nullable=True, index=True)
    amount: Mapped[float] = mapped_column(Numeric(18, 6), default=0)
    currency: Mapped[str] = mapped_column(String(3), default="CAD")
    source_amount: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True)
    source_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    quantity: Mapped[float | None] = mapped_column(Numeric(20, 8, asdecimal=False), nullable=True)
    fees: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True)
    fee_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TransactionFunding(Base):
    __tablename__ = "transaction_fundings"
    __table_args__ = (
        UniqueConstraint("transaction_id", "contribution_id", name="uq_transaction_fundings_transaction_contribution"),
        CheckConstraint("amount > 0", name="ck_transaction_fundings_amount_positive"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    transaction_id: Mapped[int] = mapped_column(ForeignKey("transactions.id", ondelete="CASCADE"), index=True)
    contribution_id: Mapped[int] = mapped_column(ForeignKey("transactions.id"), index=True)
    amount: Mapped[float] = mapped_column(Numeric(18, 6))


class HoldingSnapshot(Base):
    __tablename__ = "holdings_snapshots"
    # "unused" rows track contribution room and can be negative; only holdings must be >= 0.
    __table_args__ = (
        CheckConstraint("record_type <> 'holding' OR market_value >= 0", name="ck_holdings_snapshots_holding_value_non_negative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_date: Mapped[date] = mapped_column(Date, index=True)
    snapshot_year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    snapshot_type: Mapped[str] = mapped_column(String(20), default="current", index=True)
    holding_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    record_type: Mapped[str] = mapped_column(String(20), default="holding", index=True)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True, index=True)
    platform_id: Mapped[int | None] = mapped_column(ForeignKey("platforms.id"), nullable=True, index=True)
    instrument_id: Mapped[int | None] = mapped_column(ForeignKey("instruments.id"), nullable=True, index=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), nullable=True, index=True)
    market_value: Mapped[float] = mapped_column(Numeric(14, 2), default=0)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    operation: Mapped[str] = mapped_column(String(20), index=True)
    table_name: Mapped[str] = mapped_column(String(100), index=True)
    row_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    summary: Mapped[str | None] = mapped_column(String(255), nullable=True)
    before_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str | None] = mapped_column(String(100), nullable=True)


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"
    __table_args__ = (UniqueConstraint("snapshot_date", "account_id", name="uq_portfolio_snapshots_date_account"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_date: Mapped[date] = mapped_column(Date, index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    book_value: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    market_value: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    currency: Mapped[str] = mapped_column(String(3), default="CAD")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
