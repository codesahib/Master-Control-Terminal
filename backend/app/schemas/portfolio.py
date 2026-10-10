import datetime as dt
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.schemas import DistributionPoint, PortfolioSummaryRead


class CashPositionRead(BaseModel):
    account_name: str
    platform_name: Optional[str] = None
    currency: str
    amount: float


class PortfolioHealthRead(BaseModel):
    missing_price: int
    missing_quantity: int
    stale: int
    fx_missing: int
    negative_cash: list[CashPositionRead]
    idle_cash: list[CashPositionRead]
    prices_updated_at: Optional[dt.datetime] = None


class PortfolioTotalsRead(BaseModel):
    book_value: float
    market_value: float
    unrealized_pl: float
    unrealized_pl_pct: Optional[float] = None
    investable_cash: float


class DistributionSetRead(BaseModel):
    sector: list[DistributionPoint]
    account: list[DistributionPoint]
    platform: list[DistributionPoint]


class PortfolioOverviewRead(BaseModel):
    totals: PortfolioTotalsRead
    summary: PortfolioSummaryRead
    distribution: DistributionSetRead
    health: PortfolioHealthRead


class PortfolioHistoryPoint(BaseModel):
    date: dt.date
    book_value: float
    market_value: float


class TimeSeriesRead(BaseModel):
    month: str
    contributions: float
    investments: float
    withdrawals: float
    dividends: float


class SymbolCandidateRead(BaseModel):
    id: Optional[int] = None
    symbol: str
    provider_symbol: str
    name: Optional[str] = None
    exchange: Optional[str] = None
    currency: Optional[str] = None
    asset_type: Optional[str] = None
    provider: str


class SymbolCreate(BaseModel):
    provider_symbol: str = Field(min_length=1, max_length=80)
    symbol: Optional[str] = Field(default=None, max_length=50)
    name: Optional[str] = Field(default=None, max_length=200)
    exchange: Optional[str] = Field(default=None, max_length=80)
    currency: Optional[str] = Field(default=None, pattern="^[A-Z]{3}$")
    asset_type: Optional[str] = Field(default=None, max_length=50)
