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
            TransactionType.dividend_interest,
        } and not self.symbol:
            raise ValueError("symbol is required for investment and dividend transactions")
        if self.transaction_type == TransactionType.transfer and not self.notes:
            raise ValueError("notes are required for transfer transactions")
        return self


class ContributionCreate(BaseModel):
    transaction_date: date
    account_name: Optional[str] = None
    platform_name: Optional[str] = None
    amount: float = Field(ge=0)
    notes: Optional[str] = None


class AccountTransactionCreate(BaseModel):
    transaction_type: TransactionType
    transaction_date: date
    account_name: str = Field(min_length=1)
    platform_name: str = Field(min_length=1)
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
    def validate_account_transaction(self):
        if self.transaction_type == TransactionType.contribution:
            raise ValueError("use the contribution endpoints for contribution records")
        return self


class TransactionRead(BaseModel):
    id: int
    transaction_type: TransactionType
    transaction_date: date
    account_name: Optional[str]
    platform_name: Optional[str]
    symbol: Optional[str]
    broad_category: Optional[str]
    precise_category: Optional[str]
    amount: float
    quantity: Optional[float]
    fees: Optional[float]
    notes: Optional[str]


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
    symbol: Optional[str]
    broad_category: Optional[str]
    precise_category: Optional[str]
    amount: float
    quantity: Optional[float]
    fees: Optional[float]
    notes: Optional[str]


class HoldingRead(BaseModel):
    id: int
    snapshot_date: date
    snapshot_year: Optional[int]
    snapshot_type: str
    holding_date: Optional[date]
    account_name: Optional[str]
    platform_name: Optional[str]
    symbol: Optional[str]
    broad_category: Optional[str]
    precise_category: Optional[str]
    record_type: str
    market_value: float


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
