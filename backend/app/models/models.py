import enum
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum, Float, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

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


class ImportType(str, enum.Enum):
    contributions = "contributions"
    holdings = "holdings"


class ImportStatus(str, enum.Enum):
    parsed = "parsed"
    committed = "committed"
    failed = "failed"


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
    platform_id: Mapped[int] = mapped_column(ForeignKey("platforms.id", ondelete="CASCADE"))


class Category(Base):
    __tablename__ = "categories"

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

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id", ondelete="CASCADE"), index=True)
    price: Mapped[float] = mapped_column(Numeric(14, 4))
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    provider: Mapped[str] = mapped_column(String(50), default="yfinance")
    priced_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ContributionLimit(Base):
    __tablename__ = "contribution_limits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    tax_year: Mapped[str] = mapped_column(String(4), index=True)
    new_room: Mapped[float] = mapped_column(Numeric(14, 2), default=0)


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    transaction_type: Mapped[TransactionType] = mapped_column(Enum(TransactionType), index=True)
    transaction_date: Mapped[date] = mapped_column(Date, index=True)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True, index=True)
    platform_id: Mapped[int | None] = mapped_column(ForeignKey("platforms.id"), nullable=True, index=True)
    source_platform_id: Mapped[int | None] = mapped_column(ForeignKey("platforms.id"), nullable=True, index=True)
    instrument_id: Mapped[int | None] = mapped_column(ForeignKey("instruments.id"), nullable=True, index=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), nullable=True, index=True)
    amount: Mapped[float] = mapped_column(Numeric(18, 6), default=0)
    currency: Mapped[str] = mapped_column(String(3), default="CAD")
    source_amount: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True)
    source_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    fees: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True)
    fee_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reversal_of_id: Mapped[int | None] = mapped_column(ForeignKey("transactions.id"), nullable=True)
    contribution_id: Mapped[int | None] = mapped_column(ForeignKey("transactions.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TransactionFunding(Base):
    __tablename__ = "transaction_fundings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    transaction_id: Mapped[int] = mapped_column(ForeignKey("transactions.id", ondelete="CASCADE"), index=True)
    contribution_id: Mapped[int] = mapped_column(ForeignKey("transactions.id"), index=True)
    amount: Mapped[float] = mapped_column(Numeric(14, 2))


class HoldingSnapshot(Base):
    __tablename__ = "holdings_snapshots"

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


class Import(Base):
    __tablename__ = "imports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    import_type: Mapped[ImportType] = mapped_column(Enum(ImportType), index=True)
    source_filename: Mapped[str] = mapped_column(String(255))
    status: Mapped[ImportStatus] = mapped_column(Enum(ImportStatus), default=ImportStatus.parsed)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ImportRow(Base):
    __tablename__ = "import_rows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    import_id: Mapped[int] = mapped_column(ForeignKey("imports.id", ondelete="CASCADE"), index=True)
    row_number: Mapped[int] = mapped_column(Integer)
    payload_json: Mapped[str] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
