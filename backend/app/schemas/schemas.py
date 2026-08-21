from datetime import date
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from app.models.models import TransactionType


class TransactionCreate(BaseModel):
    transaction_type: TransactionType
    transaction_date: date
    account_name: Optional[str] = None
    platform_name: Optional[str] = None
    symbol: Optional[str] = None
    instrument_name: Optional[str] = None
    broad_category: Optional[str] = None
    precise_category: Optional[str] = None
    amount: float = Field(ge=0)
    quantity: Optional[float] = None
    fees: Optional[float] = Field(default=0, ge=0)
    notes: Optional[str] = None
    reversal_of_id: Optional[int] = None

    @model_validator(mode="after")
    def validate_by_type(self):
        if self.transaction_type in {
            TransactionType.investment_buy,
            TransactionType.investment_sell,
            TransactionType.dividend_reinvestment,
            TransactionType.quantity_adjustment,
        } and not self.symbol:
            raise ValueError("symbol is required for investment and dividend transactions")
        if self.transaction_type in {
            TransactionType.investment_buy,
            TransactionType.investment_sell,
            TransactionType.dividend_reinvestment,
        } and (
            self.quantity is None or self.quantity <= 0
        ):
            raise ValueError("quantity is required for investment buys and sells")
        if self.transaction_type == TransactionType.quantity_adjustment and (
            self.quantity is None or self.quantity == 0 or self.amount != 0 or self.fees
        ):
            raise ValueError("quantity adjustments require a non-zero quantity and zero amount and fees")
        if self.transaction_type == TransactionType.transfer and not self.notes:
            raise ValueError("notes are required for transfer transactions")
        return self


class ContributionCreate(BaseModel):
    transaction_date: date
    account_name: Optional[str] = None
    platform_name: Optional[str] = None
    amount: float = Field(ge=0)
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
    account_name: str = Field(min_length=1)
    platform_name: str = Field(min_length=1)
    source_platform_name: Optional[str] = None
    symbol: Optional[str] = None
    instrument_name: Optional[str] = None
    broad_category: Optional[str] = None
    precise_category: Optional[str] = None
    amount: float = Field(ge=0)
    quantity: Optional[float] = None
    fees: Optional[float] = Field(default=0, ge=0)
    notes: Optional[str] = None
    reversal_of_id: Optional[int] = None
    contribution_id: Optional[int] = Field(default=None, gt=0)
    funding_contributions: list[FundingContribution] = Field(default_factory=list)
    funding_cash_sources: list[FundingCashSource] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_account_transaction(self):
        if self.transaction_type == TransactionType.contribution:
            raise ValueError("use the contribution endpoints for contribution records")
        if (self.contribution_id or self.funding_contributions) and self.funding_cash_sources:
            raise ValueError("use either funding contributions or funding cash sources")
        if self.contribution_id and self.funding_contributions:
            raise ValueError("use either contribution_id or funding_contributions")
        if len({funding.contribution_id for funding in self.funding_contributions}) != len(self.funding_contributions):
            raise ValueError("funding contributions must be unique")
        if len({source.platform_name.lower() for source in self.funding_cash_sources}) != len(self.funding_cash_sources):
            raise ValueError("funding cash sources must be unique")
        if self.transaction_type == TransactionType.dividend_reinvestment and (
            not self.symbol or self.quantity is None or self.quantity <= 0 or self.amount <= 0
        ):
            raise ValueError("dividend reinvestments require a symbol, positive quantity, and positive amount")
        if self.transaction_type == TransactionType.quantity_adjustment and (
            not self.symbol
            or self.quantity is None
            or self.quantity == 0
            or self.amount != 0
            or self.fees
            or self.contribution_id
            or self.funding_contributions
            or self.funding_cash_sources
        ):
            raise ValueError("quantity adjustments require a symbol, non-zero quantity, and no cash or funding")
        return self


class TransactionRead(BaseModel):
    id: int
    transaction_type: TransactionType
    transaction_date: date
    account_name: Optional[str]
    platform_name: Optional[str]
    source_platform_name: Optional[str] = None
    symbol: Optional[str]
    broad_category: Optional[str]
    precise_category: Optional[str]
    amount: float
    quantity: Optional[float]
    fees: Optional[float]
    notes: Optional[str]
    contribution_id: Optional[int] = None
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
    notes: Optional[str]


class AccountTransactionRead(BaseModel):
    id: int
    transaction_type: TransactionType
    transaction_date: date
    account_name: Optional[str]
    platform_name: Optional[str]
    source_platform_name: Optional[str] = None
    symbol: Optional[str]
    broad_category: Optional[str]
    precise_category: Optional[str]
    amount: float
    quantity: Optional[float]
    fees: Optional[float]
    notes: Optional[str]
    contribution_id: Optional[int] = None
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
    symbol: str
    broad_category: Optional[str]
    precise_category: Optional[str]
    record_type: str
    quantity: Optional[float]
    book_value: float


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


class ImportPreviewRow(BaseModel):
    row_number: int
    payload: dict
    error: Optional[str] = None


class ImportPreviewResponse(BaseModel):
    import_id: int
    rows: list[ImportPreviewRow]
    row_count: int
