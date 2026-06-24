import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from openpyxl import load_workbook

from app.db.session import get_db
from app.models.models import Account, Category, ImportType, Instrument, Platform
from app.schemas.schemas import (
    AccountTransactionCreate,
    AccountTransactionRead,
    ContributionCreate,
    ContributionLimitRead,
    ContributionLimitUpdate,
    ContributionRead,
    ContributionRoomRead,
    DistributionPoint,
    HoldingRead,
    ImportPreviewResponse,
    ImportPreviewRow,
    TimeSeriesPoint,
    TransactionCreate,
    TransactionRead,
)
from app.services.finance import (
    create_account_transaction,
    create_contribution,
    create_import_preview,
    create_transaction,
    distribution,
    export_all_data,
    get_contribution_room,
    list_account_transactions,
    list_contributions,
    list_holdings,
    list_contribution_limits,
    list_transactions,
    restore_all_data,
    timeseries,
    upsert_contribution_limit,
    update_account_transaction,
    update_contribution,
    update_transaction,
)

router = APIRouter()


def serialize_transaction(txn, db: Session) -> TransactionRead:
    account = db.get(Account, txn.account_id) if txn.account_id else None
    platform = db.get(Platform, txn.platform_id) if txn.platform_id else None
    instrument = db.get(Instrument, txn.instrument_id) if txn.instrument_id else None
    category = db.get(Category, txn.category_id) if txn.category_id else None
    return TransactionRead(
        id=txn.id,
        transaction_type=txn.transaction_type,
        transaction_date=txn.transaction_date,
        account_name=account.name if account else None,
        platform_name=platform.canonical_name if platform else None,
        symbol=instrument.symbol if instrument else None,
        broad_category=category.broad if category else None,
        precise_category=category.precise if category else None,
        amount=float(txn.amount),
        quantity=txn.quantity,
        fees=float(txn.fees or 0),
        notes=txn.notes,
    )


def serialize_transaction_row(row) -> TransactionRead:
    txn, account_name, platform_name, symbol_name, broad_category, precise_category = row
    return TransactionRead(
        id=txn.id,
        transaction_type=txn.transaction_type,
        transaction_date=txn.transaction_date,
        account_name=account_name,
        platform_name=platform_name,
        symbol=symbol_name,
        broad_category=broad_category,
        precise_category=precise_category,
        amount=float(txn.amount),
        quantity=txn.quantity,
        fees=float(txn.fees or 0),
        notes=txn.notes,
    )


def serialize_contribution_row(row) -> ContributionRead:
    txn, account_name, platform_name, _symbol_name, _broad_category, _precise_category = row
    return ContributionRead(
        id=txn.id,
        transaction_date=txn.transaction_date,
        account_name=account_name,
        platform_name=platform_name,
        amount=float(txn.amount),
        notes=txn.notes,
    )


def serialize_account_transaction_row(row) -> AccountTransactionRead:
    txn, account_name, platform_name, symbol_name, broad_category, precise_category = row
    return AccountTransactionRead(
        id=txn.id,
        transaction_type=txn.transaction_type,
        transaction_date=txn.transaction_date,
        account_name=account_name,
        platform_name=platform_name,
        symbol=symbol_name,
        broad_category=broad_category,
        precise_category=precise_category,
        amount=float(txn.amount),
        quantity=txn.quantity,
        fees=float(txn.fees or 0),
        notes=txn.notes,
    )


def serialize_holding_row(row) -> HoldingRead:
    snapshot, account_name, platform_name, symbol_name, broad_category, precise_category = row
    return HoldingRead(
        id=snapshot.id,
        snapshot_date=snapshot.snapshot_date,
        snapshot_year=snapshot.snapshot_year,
        snapshot_type=snapshot.snapshot_type,
        holding_date=snapshot.holding_date,
        account_name=account_name,
        platform_name=platform_name,
        symbol=symbol_name,
        broad_category=broad_category,
        precise_category=precise_category,
        record_type=snapshot.record_type,
        market_value=float(snapshot.market_value),
    )


@router.post("/transactions", response_model=TransactionRead)
def create_transaction_endpoint(payload: TransactionCreate, db: Session = Depends(get_db)):
    txn = create_transaction(db, payload)
    return serialize_transaction(txn, db)


@router.put("/transactions/{transaction_id}", response_model=TransactionRead)
def update_transaction_endpoint(transaction_id: int, payload: TransactionCreate, db: Session = Depends(get_db)):
    txn = update_transaction(db, transaction_id, payload)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return serialize_transaction(txn, db)


@router.get("/transactions", response_model=list[TransactionRead])
def list_transactions_endpoint(
    transaction_type: str | None = Query(default=None),
    account: str | None = Query(default=None),
    platform: str | None = Query(default=None),
    symbol: str | None = Query(default=None),
    year: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    rows = list_transactions(db, transaction_type, account, platform, symbol, year)
    return [serialize_transaction_row(row) for row in rows]


@router.post("/contributions", response_model=ContributionRead)
def create_contribution_endpoint(payload: ContributionCreate, db: Session = Depends(get_db)):
    txn = create_contribution(db, payload)
    return ContributionRead(
        id=txn.id,
        transaction_date=txn.transaction_date,
        account_name=db.get(Account, txn.account_id).name if txn.account_id else None,
        platform_name=db.get(Platform, txn.platform_id).canonical_name if txn.platform_id else None,
        amount=float(txn.amount),
        notes=txn.notes,
    )


@router.put("/contributions/{transaction_id}", response_model=ContributionRead)
def update_contribution_endpoint(transaction_id: int, payload: ContributionCreate, db: Session = Depends(get_db)):
    txn = update_contribution(db, transaction_id, payload)
    if not txn:
        raise HTTPException(status_code=404, detail="Contribution not found")
    return ContributionRead(
        id=txn.id,
        transaction_date=txn.transaction_date,
        account_name=db.get(Account, txn.account_id).name if txn.account_id else None,
        platform_name=db.get(Platform, txn.platform_id).canonical_name if txn.platform_id else None,
        amount=float(txn.amount),
        notes=txn.notes,
    )


@router.get("/contributions", response_model=list[ContributionRead])
def list_contributions_endpoint(
    account: str | None = Query(default=None),
    platform: str | None = Query(default=None),
    year: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    rows = list_contributions(db, account=account, platform=platform, year=year)
    return [serialize_contribution_row(row) for row in rows]


@router.post("/account-transactions", response_model=AccountTransactionRead)
def create_account_transaction_endpoint(payload: AccountTransactionCreate, db: Session = Depends(get_db)):
    txn = create_account_transaction(db, payload)
    return serialize_transaction(txn, db)


@router.put("/account-transactions/{transaction_id}", response_model=AccountTransactionRead)
def update_account_transaction_endpoint(transaction_id: int, payload: AccountTransactionCreate, db: Session = Depends(get_db)):
    txn = update_account_transaction(db, transaction_id, payload)
    if not txn:
        raise HTTPException(status_code=404, detail="Account transaction not found")
    return serialize_transaction(txn, db)


@router.get("/account-transactions", response_model=list[AccountTransactionRead])
def list_account_transactions_endpoint(
    account: str | None = Query(default=None),
    platform: str | None = Query(default=None),
    symbol: str | None = Query(default=None),
    year: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    rows = list_account_transactions(db, account=account, platform=platform, symbol=symbol, year=year)
    return [serialize_account_transaction_row(row) for row in rows]


@router.get("/holdings", response_model=list[HoldingRead])
def list_holdings_endpoint(
    account: str | None = Query(default=None),
    year: int | None = Query(default=None),
    snapshot_type: str = Query(default="current", pattern="^(current|year_end)$"),
    db: Session = Depends(get_db),
):
    rows = list_holdings(db, account=account, year=year, snapshot_type=snapshot_type)
    return [serialize_holding_row(row) for row in rows]


@router.get("/limits/{year}", response_model=list[ContributionRoomRead])
def get_limits(year: int, db: Session = Depends(get_db)):
    return get_contribution_room(db, year)


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
        raise HTTPException(status_code=400, detail="tax_year must be a 4-digit year")
    return upsert_contribution_limit(
        db,
        account,
        tax_year,
        payload.new_room,
    )


@router.get("/analytics/distribution", response_model=list[DistributionPoint])
def get_distribution(
    group_by: str = Query(pattern="^(sector|account|platform)$"),
    year: int | None = Query(default=None),
    category_level: str = Query(default="precise", pattern="^(broad|precise)$"),
    db: Session = Depends(get_db),
):
    return distribution(db, group_by, year, category_level)


@router.get("/analytics/timeseries", response_model=list[TimeSeriesPoint])
def get_timeseries(year: int | None = Query(default=None), db: Session = Depends(get_db)):
    return timeseries(db, year)


@router.get("/export")
def export_data(db: Session = Depends(get_db)):
    exported_at = datetime.now(timezone.utc)
    payload = {
        "meta": {
            "exported_at": exported_at,
            "format": "master-control-terminal-export",
            "version": 1,
        },
        "data": export_all_data(db),
    }
    filename = f"master-control-terminal-export-{exported_at.strftime('%Y%m%dT%H%M%SZ')}.json"
    return JSONResponse(
        content=jsonable_encoder(payload),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/import-backup")
async def import_backup(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename or not file.filename.lower().endswith(".json"):
        raise HTTPException(status_code=400, detail="Please upload a JSON backup file")

    try:
        payload = json.loads(await file.read())
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Backup file is not valid JSON") from exc

    meta = payload.get("meta", {})
    if meta.get("format") != "master-control-terminal-export":
        raise HTTPException(status_code=400, detail="Unsupported backup format")

    try:
        restore_all_data(db, payload)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"status": "ok", "message": "Backup restored successfully"}


@router.post("/imports/contributions", response_model=ImportPreviewResponse)
async def import_contributions(file: UploadFile = File(...), db: Session = Depends(get_db)):
    wb = load_workbook(file.file, data_only=True)
    rows = []
    for year in [name for name in wb.sheetnames if name.isdigit()]:
        ws = wb[year]
        for r in range(12, 24):
            rrsp_label = ws.cell(r, 9).value
            rrsp_amount = ws.cell(r, 10).value
            tfsa_label = ws.cell(r, 11).value
            tfsa_amount = ws.cell(r, 12).value
            if rrsp_label and rrsp_amount:
                rows.append({"tax_year": int(year), "account": "RRSP", "label": rrsp_label, "amount": float(rrsp_amount)})
            if tfsa_label and tfsa_amount:
                rows.append({"tax_year": int(year), "account": "TFSA", "label": tfsa_label, "amount": float(tfsa_amount)})

    imp = create_import_preview(db, ImportType.contributions, file.filename, rows)
    return ImportPreviewResponse(
        import_id=imp.id,
        rows=[ImportPreviewRow(row_number=i + 1, payload=row) for i, row in enumerate(rows[:250])],
        row_count=len(rows),
    )


@router.post("/imports/holdings", response_model=ImportPreviewResponse)
async def import_holdings(file: UploadFile = File(...), db: Session = Depends(get_db)):
    wb = load_workbook(file.file, data_only=True)
    if "Distrubution" not in wb.sheetnames and "Distribution" not in wb.sheetnames:
        raise HTTPException(status_code=400, detail="Distribution sheet not found")

    sheet_name = "Distrubution" if "Distrubution" in wb.sheetnames else "Distribution"
    ws = wb[sheet_name]
    rows = []

    for r in range(17, 42):
        for start_col, account in [(1, "FHSA"), (9, "RRSP"), (16, "TFSA")]:
            fund = ws.cell(r, start_col).value
            broad = ws.cell(r, start_col + 1).value
            precise = ws.cell(r, start_col + 2).value
            amount = ws.cell(r, start_col + 3).value
            if fund and amount:
                rows.append(
                    {
                        "account": account,
                        "instrument": str(fund),
                        "broad_category": str(broad) if broad else "Unknown",
                        "precise_category": str(precise) if precise else "Unknown",
                        "market_value": float(amount),
                    }
                )

    imp = create_import_preview(db, ImportType.holdings, file.filename, rows)
    return ImportPreviewResponse(
        import_id=imp.id,
        rows=[ImportPreviewRow(row_number=i + 1, payload=row) for i, row in enumerate(rows[:250])],
        row_count=len(rows),
    )
