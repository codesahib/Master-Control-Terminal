import json
from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.models import Platform, Transaction, TransactionType
from app.schemas.schemas import (
    AccountTransactionCreate,
    AccountTransactionRead,
    PaginatedAccountTransactionRead,
    ContributionCreate,
    ContributionFundingRead,
    ContributionLimitRead,
    ContributionLimitUpdate,
    ContributionRead,
    ContributionRoomRead,
    DistributionPoint,
    GicMaturityCreate,
    HoldingRead,
    MarketPriceRefreshResult,
    ManualValuationUpsert,
    PaginatedTransactionRead,
    PaginatedPortfolioPLRead,
    PortfolioSummaryRead,
)
from app.services.finance import (
    BACKUP_FORMAT,
    BACKUP_FORMAT_VERSION,
    ConflictError,
    create_account_transaction,
    create_contribution,
    delete_transaction,
    export_all_data,
    get_all_contribution_room,
    get_contribution_room,
    list_available_contributions,
    list_contribution_limits,
    mature_gic,
    restore_all_data,
    tracked_years,
    upsert_manual_valuation,
    upsert_contribution_limit,
    update_account_transaction,
    update_contribution,
)
from app.services.market_data import refresh_market_prices, search_symbols
from app.schemas.portfolio import SymbolCandidateRead, TimeSeriesRead
from app.services.portfolio import distribution, grouped_holdings, portfolio_pl, portfolio_summary, record_portfolio_snapshots, sort_pl_rows, timeseries
from app.services.transaction_reads import (
    account_transaction_reads,
    contribution_read,
    contribution_reads,
    transaction_read,
    transaction_reads,
)

router = APIRouter()


def _run(db: Session, operation, *args):
    try:
        return operation(db, *args)
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ConflictError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/years", response_model=list[int])
def list_years(db: Session = Depends(get_db)):
    return tracked_years(db)


@router.get("/platforms", response_model=list[str])
def list_platforms(db: Session = Depends(get_db)):
    return list(db.scalars(select(Platform.canonical_name).order_by(Platform.canonical_name)))


@router.get("/symbols/search", response_model=list[SymbolCandidateRead])
def search_symbols_endpoint(
    q: str = Query(min_length=1),
    limit: int = Query(default=8, ge=1, le=20),
    db: Session = Depends(get_db),
):
    return search_symbols(db, q, limit)


@router.post("/market-prices/refresh", response_model=list[MarketPriceRefreshResult])
def refresh_market_prices_endpoint(db: Session = Depends(get_db)):
    results = refresh_market_prices(db)
    record_portfolio_snapshots(db)
    return results


@router.post("/manual-valuations")
def upsert_manual_valuation_endpoint(payload: ManualValuationUpsert, db: Session = Depends(get_db)):
    snapshot = _run(db, upsert_manual_valuation, payload)
    return {
        "id": snapshot.id,
        "snapshot_date": snapshot.snapshot_date,
        "market_value": float(snapshot.market_value),
    }


@router.get("/portfolio/pl", response_model=PaginatedPortfolioPLRead)
def portfolio_pl_endpoint(
    account: str | None = Query(default=None),
    platform: str | None = Query(default=None),
    status: str | None = Query(default=None),
    year: int | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=500),
    sort_direction: Literal["asc", "desc"] = Query(default="desc"),
    sort_by: Annotated[Literal["symbol", "market_value", "unrealized_pl", "unrealized_pl_pct"], Query()] = "symbol",
    db: Session = Depends(get_db),
):
    rows = portfolio_pl(db, account=account, platform=platform, status=status, year=year)
    rows = sort_pl_rows(rows, sort_by, sort_direction)
    total = len(rows)
    start = (page - 1) * page_size
    return PaginatedPortfolioPLRead(items=rows[start:start + page_size], total=total, page=page, page_size=page_size)


@router.get("/portfolio/summary", response_model=PortfolioSummaryRead)
def portfolio_summary_endpoint(
    year: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    return portfolio_summary(db, year=year)


@router.get("/transactions", response_model=PaginatedTransactionRead)
def list_transactions_endpoint(
    transaction_type: TransactionType | None = Query(default=None),
    account: str | None = Query(default=None),
    platform: str | None = Query(default=None),
    symbol: str | None = Query(default=None),
    year: int | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    sort_direction: Literal["asc", "desc"] = Query(default="desc"),
    db: Session = Depends(get_db),
):
    items, total = transaction_reads(
        db, transaction_type=transaction_type, account=account, platform=platform, symbol=symbol,
        year=year, page=page, page_size=page_size, sort_direction=sort_direction,
    )
    return PaginatedTransactionRead(
        items=items, total=total, page=page, page_size=page_size
    )


@router.post("/contributions", response_model=ContributionRead)
def create_contribution_endpoint(payload: ContributionCreate, db: Session = Depends(get_db)):
    txn = _run(db, create_contribution, payload)
    return contribution_read(db, txn)


@router.put("/contributions/{transaction_id}", response_model=ContributionRead)
def update_contribution_endpoint(transaction_id: int, payload: ContributionCreate, db: Session = Depends(get_db)):
    txn = _run(db, update_contribution, transaction_id, payload)
    if not txn:
        raise HTTPException(status_code=404, detail="Contribution not found")
    return contribution_read(db, txn)


@router.delete("/contributions/{transaction_id}", status_code=204)
def delete_contribution_endpoint(transaction_id: int, db: Session = Depends(get_db)):
    _run(db, delete_transaction, transaction_id, True)
    return Response(status_code=204)


@router.get("/contributions", response_model=list[ContributionRead])
def list_contributions_endpoint(
    account: str | None = Query(default=None),
    platform: str | None = Query(default=None),
    year: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    return contribution_reads(db, account=account, platform=platform, year=year)


@router.get("/available-contributions", response_model=list[ContributionFundingRead])
def list_available_contributions_endpoint(
    account: str,
    exclude_transaction_id: int | None = None,
    db: Session = Depends(get_db),
):
    return list_available_contributions(db, account, db.get(Transaction, exclude_transaction_id) if exclude_transaction_id else None)


@router.post("/account-transactions", response_model=AccountTransactionRead)
def create_account_transaction_endpoint(payload: AccountTransactionCreate, db: Session = Depends(get_db)):
    txn = _run(db, create_account_transaction, payload)
    return transaction_read(db, txn)


@router.post("/gic-maturities", response_model=list[AccountTransactionRead])
def mature_gic_endpoint(payload: GicMaturityCreate, db: Session = Depends(get_db)):
    return [transaction_read(db, txn) for txn in _run(db, mature_gic, payload)]


@router.put("/account-transactions/{transaction_id}", response_model=AccountTransactionRead)
def update_account_transaction_endpoint(transaction_id: int, payload: AccountTransactionCreate, db: Session = Depends(get_db)):
    txn = _run(db, update_account_transaction, transaction_id, payload)
    if not txn:
        raise HTTPException(status_code=404, detail="Account transaction not found")
    return transaction_read(db, txn)


@router.delete("/account-transactions/{transaction_id}", status_code=204)
def delete_account_transaction_endpoint(transaction_id: int, db: Session = Depends(get_db)):
    _run(db, delete_transaction, transaction_id, False)
    return Response(status_code=204)


@router.get("/account-transactions", response_model=PaginatedAccountTransactionRead)
def list_account_transactions_endpoint(
    account: str | None = Query(default=None),
    platform: str | None = Query(default=None),
    symbol: str | None = Query(default=None),
    year: int | None = Query(default=None),
    transaction_type: TransactionType | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    sort_direction: Literal["asc", "desc"] = Query(default="desc"),
    db: Session = Depends(get_db),
):
    items, total = account_transaction_reads(
        db, account=account, platform=platform, symbol=symbol, year=year,
        transaction_type=transaction_type, page=page, page_size=page_size, sort_direction=sort_direction,
    )
    return PaginatedAccountTransactionRead(
        items=items, total=total, page=page, page_size=page_size
    )


@router.get("/holdings", response_model=list[HoldingRead])
def list_holdings_endpoint(
    account: str | None = Query(default=None),
    year: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    return grouped_holdings(db, account=account, year=year)


@router.get("/limits/{year}", response_model=list[ContributionRoomRead])
def get_limits(year: int, db: Session = Depends(get_db)):
    return get_contribution_room(db, year)


@router.get("/limits", response_model=list[ContributionRoomRead])
def get_all_limits(db: Session = Depends(get_db)):
    return get_all_contribution_room(db)


@router.get("/contribution-limits", response_model=list[ContributionLimitRead])
def get_contribution_limits(db: Session = Depends(get_db)):
    return list_contribution_limits(db)


@router.put("/contribution-limits/{account}/{tax_year}", response_model=ContributionLimitRead)
def update_contribution_limit(
    account: str,
    tax_year: str,
    payload: ContributionLimitUpdate,
    db: Session = Depends(get_db),
):
    if not tax_year.isdigit() or len(tax_year) != 4:
        raise HTTPException(status_code=422, detail="tax_year must be a 4-digit year")
    return _run(db, upsert_contribution_limit, account, tax_year, payload.new_room)


@router.get("/analytics/distribution", response_model=list[DistributionPoint])
def get_distribution(
    group_by: str = Query(pattern="^(sector|account|platform)$"),
    year: int | None = Query(default=None),
    category_level: str = Query(default="precise", pattern="^(broad|precise)$"),
    currency: str = Query(default="CAD", pattern="^(CAD|USD)$"),
    db: Session = Depends(get_db),
):
    return distribution(db, group_by, year, category_level, currency)


@router.get("/analytics/timeseries", response_model=list[TimeSeriesRead])
def get_timeseries(
    year: int | None = Query(default=None),
    currency: str = Query(default="CAD", pattern="^(CAD|USD)$"),
    db: Session = Depends(get_db),
):
    return timeseries(db, year, currency)


@router.get("/export")
def export_data(db: Session = Depends(get_db)):
    exported_at = datetime.now(timezone.utc)
    payload = {
        "meta": {
            "exported_at": exported_at,
            "format": BACKUP_FORMAT,
            "version": BACKUP_FORMAT_VERSION,
        },
        "data": export_all_data(db),
    }
    filename = f"master-control-terminal-export-{exported_at.strftime('%Y%m%dT%H%M%SZ')}.json"
    return JSONResponse(
        content=jsonable_encoder(payload),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/import-backup")
def import_backup(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename or not file.filename.lower().endswith(".json"):
        raise HTTPException(status_code=400, detail="Please upload a JSON backup file")

    try:
        payload = json.loads(file.file.read())
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Backup file is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Backup file must contain a JSON object")
    meta = payload.get("meta") or {}
    if meta.get("format") != BACKUP_FORMAT:
        raise HTTPException(status_code=400, detail="Unsupported backup format")
    version = meta.get("version", 1)
    if not isinstance(version, int) or not 1 <= version <= BACKUP_FORMAT_VERSION:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported backup version {version}; this app restores versions 1 to {BACKUP_FORMAT_VERSION}",
        )

    try:
        restore_all_data(db, payload)
    except (ValueError, SQLAlchemyError) as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"status": "ok", "message": "Backup restored successfully"}


from app.api.portfolio_routes import router as portfolio_router  # noqa: E402

router.include_router(portfolio_router)
