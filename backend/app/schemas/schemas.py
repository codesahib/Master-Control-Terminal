from datetime import date, datetime
from typing import Annotated, Optional

from pydantic import AfterValidator, BaseModel, Field, model_validator

from app.models.models import TransactionType


ACCOUNT_NAMES = ("RRSP", "TFSA", "FHSA")


def _account_name(value: str) -> str:
    normalized = value.strip().upper()
    if normalized not in ACCOUNT_NAMES:
        raise ValueError("account must be RRSP, TFSA or FHSA")
    return normalized


AccountName = Annotated[str, AfterValidator(_account_name)]
PlatformName = Annotated[str, Field(min_length=1, max_length=100)]
SymbolText = Annotated[str, Field(max_length=40)]
CategoryName = Annotated[str, Field(max_length=100)]


class ContributionCreate(BaseModel):
    transaction_date: date
    account_name: AccountName
    platform_name: Optional[PlatformName] = None
    amount: float = Field(ge=0)
    currency: str = Field(default="CAD", pattern="^[A-Z]{3}$")
    notes: Optional[str] = None


class FundingContribution(BaseModel):
    contribution_id: int = Field(gt=0)
    amount: float = Field(gt=0)
    platform_name: Optional[str] = None


class FundingCashSource(BaseModel):
    platform_name: str = Field(min_length=1)
    amount: float = Field(gt=0)


class AccountTransactionCreate(BaseModel):
    transaction_type: TransactionType
    transaction_date: date
    account_name: AccountName
    platform_name: PlatformName
    source_platform_name: Optional[PlatformName] = None
    instrument_id: Optional[int] = Field(default=None, gt=0)
    symbol: Optional[SymbolText] = None
    instrument_name: Optional[str] = Field(default=None, max_length=200)
    is_custom_symbol: bool = False
    broad_category: Optional[CategoryName] = None
    precise_category: Optional[CategoryName] = None
    amount: float = Field(ge=0)
    currency: str = Field(default="CAD", pattern="^[A-Z]{3}$")
    source_amount: Optional[float] = Field(default=None, ge=0)
    source_currency: Optional[str] = Field(default=None, pattern="^[A-Z]{3}$")
    quantity: Optional[float] = None
    fees: Optional[float] = Field(default=0, ge=0)
    fee_currency: Optional[str] = Field(default=None, pattern="^[A-Z]{3}$")
    notes: Optional[str] = None
    funding_contributions: list[FundingContribution] = Field(default_factory=list)
    funding_cash_sources: list[FundingCashSource] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_account_transaction(self):
        if self.transaction_type == TransactionType.contribution:
            raise ValueError("use the contribution endpoints for contribution records")
        if self.funding_contributions and self.funding_cash_sources:
            raise ValueError("use either funding contributions or funding cash sources")
        if len({funding.contribution_id for funding in self.funding_contributions}) != len(self.funding_contributions):
            raise ValueError("funding contributions must be unique")
        if len({source.platform_name.lower() for source in self.funding_cash_sources}) != len(self.funding_cash_sources):
            raise ValueError("funding cash sources must be unique")
        if self.transaction_type == TransactionType.withdrawal and (
            self.amount <= 0
            or self.symbol
            or self.instrument_id
            or self.quantity is not None
            or self.funding_contributions
            or self.funding_cash_sources
        ):
            raise ValueError("withdrawals require a positive amount and no symbol, quantity or funding")
        if self.transaction_type == TransactionType.dividend_reinvestment and (
            (not self.symbol and not self.instrument_id) or self.quantity is None or self.quantity <= 0 or self.amount <= 0
        ):
            raise ValueError("dividend reinvestments require a symbol, positive quantity, and positive amount")
        if self.transaction_type == TransactionType.quantity_adjustment and (
            not self.symbol
            and not self.instrument_id
            or self.quantity is None
            or self.quantity == 0
            or self.amount != 0
            or self.fees
            or self.funding_contributions
            or self.funding_cash_sources
        ):
            raise ValueError("quantity adjustments require a symbol, non-zero quantity, and no cash or funding")
        if self.transaction_type == TransactionType.currency_exchange and (
            self.amount <= 0
            or self.source_amount is None
            or self.source_amount <= 0
            or not self.source_currency
            or self.source_currency == self.currency
            or self.symbol
            or self.instrument_id
            or self.quantity is not None
            or self.funding_contributions
            or self.funding_cash_sources
        ):
            raise ValueError("currency exchanges require different source and destination currencies with positive amounts and no funding")
        return self


class TransactionRead(BaseModel):
    id: int
    transaction_type: TransactionType
    transaction_date: date
    account_name: Optional[str]
    platform_name: Optional[str]
    source_platform_name: Optional[str] = None
    instrument_id: Optional[int] = None
    symbol: Optional[str]
    broad_category: Optional[str]
    precise_category: Optional[str]
    amount: float
    currency: str
    source_amount: Optional[float] = None
    source_currency: Optional[str] = None
    quantity: Optional[float]
    fees: Optional[float]
    fee_currency: Optional[str] = None
    notes: Optional[str]
    funding_contributions: list[FundingContribution] = Field(default_factory=list)


class PaginatedTransactionRead(BaseModel):
    items: list[TransactionRead]
    total: int
    page: int
    page_size: int


class ContributionRead(BaseModel):
    id: int
    transaction_date: date
    account_name: Optional[str]
    platform_name: Optional[str]
    amount: float
    currency: str
    notes: Optional[str]


class AccountTransactionRead(BaseModel):
    id: int
    transaction_type: TransactionType
    transaction_date: date
    account_name: Optional[str]
    platform_name: Optional[str]
    source_platform_name: Optional[str] = None
    instrument_id: Optional[int] = None
    symbol: Optional[str]
    broad_category: Optional[str]
    precise_category: Optional[str]
    amount: float
    currency: str
    source_amount: Optional[float] = None
    source_currency: Optional[str] = None
    quantity: Optional[float]
    fees: Optional[float]
    fee_currency: Optional[str] = None
    notes: Optional[str]
    funding_contributions: list[FundingContribution] = Field(default_factory=list)


class PaginatedAccountTransactionRead(BaseModel):
    items: list[AccountTransactionRead]
    total: int
    page: int
    page_size: int


class ContributionFundingRead(BaseModel):
    id: int
    platform_name: str
    source_label: str
    remaining_amount: float


class HoldingRead(BaseModel):
    id: str
    as_of_date: date
    account_name: str
    platform_name: Optional[str]
    instrument_id: Optional[int] = None
    symbol: str
    broad_category: Optional[str]
    precise_category: Optional[str]
    record_type: str
    quantity: Optional[float]
    book_value: float
    currency: str
    average_price: Optional[float] = None
    children: list["HoldingRead"] = Field(default_factory=list)


class ContributionRoomRead(BaseModel):
    account: str
    tax_year: str
    total_room: float
    used: float
    remaining: float


class ContributionLimitRead(BaseModel):
    account: str
    tax_year: str
    unused_room: float
    new_room: float
    total_room: float


class ContributionLimitUpdate(BaseModel):
    new_room: float = Field(ge=0)


class DistributionPoint(BaseModel):
    label: str
    value: float


class TimeSeriesPoint(BaseModel):
    month: str
    contributions: float
    investments: float


class SymbolRead(BaseModel):
    id: int
    symbol: str
    provider_symbol: str
    name: Optional[str] = None
    exchange: Optional[str] = None
    currency: Optional[str] = None
    asset_type: Optional[str] = None
    provider: str


class ManualValuationUpsert(BaseModel):
    account_name: AccountName
    platform_name: Optional[PlatformName] = None
    instrument_id: Optional[int] = Field(default=None, gt=0)
    symbol: Optional[SymbolText] = None
    instrument_name: Optional[str] = Field(default=None, max_length=200)
    broad_category: Optional[CategoryName] = None
    precise_category: Optional[CategoryName] = None
    market_value: float = Field(ge=0)
    snapshot_date: date


class MarketPriceRefreshResult(BaseModel):
    instrument_id: int
    symbol: str
    provider_symbol: str
    status: str
    price: Optional[float] = None
    currency: Optional[str] = None
    priced_at: Optional[datetime] = None
    error: Optional[str] = None


class PortfolioPLRow(BaseModel):
    id: str
    as_of_date: date
    account_name: str
    platform_name: Optional[str]
    instrument_id: Optional[int] = None
    symbol: str
    provider_symbol: Optional[str] = None
    name: Optional[str] = None
    broad_category: Optional[str]
    precise_category: Optional[str]
    record_type: str
    quantity: Optional[float]
    book_value: float
    currency: str
    average_price: Optional[float] = None
    current_price: Optional[float] = None
    price_currency: Optional[str] = None
    priced_at: Optional[datetime] = None
    market_value: Optional[float] = None
    unrealized_pl: Optional[float] = None
    unrealized_pl_pct: Optional[float] = None
    reporting_currency: str = "CAD"
    fx_rate_to_reporting: Optional[float] = None
    book_value_reporting: Optional[float] = None
    market_value_reporting: Optional[float] = None
    unrealized_pl_reporting: Optional[float] = None
    price_status: str
    manual_valuation_date: Optional[date] = None
    children: list["PortfolioPLRow"] = Field(default_factory=list)


class PaginatedPortfolioPLRead(BaseModel):
    items: list[PortfolioPLRow]
    total: int
    page: int
    page_size: int


class AccountPLSummary(BaseModel):
    account: str
    book: float
    market: float
    pl: float
    bookReporting: float
    marketReporting: float
    plReporting: float
    plPct: Optional[float] = None


class PortfolioSummaryRead(BaseModel):
    investable_cash: list[PortfolioPLRow]
    allocation: list[DistributionPoint]
    account_pl: list[AccountPLSummary]
