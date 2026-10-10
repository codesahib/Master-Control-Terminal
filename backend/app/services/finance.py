import json
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum

from sqlalchemy import Date, DateTime, Enum as SqlEnum, and_, case, func, or_, select, text
from sqlalchemy.orm import Session

from app.db.session import Base
from app.models.models import (
    Account,
    AuditLog,
    Category,
    ContributionLimit,
    HoldingSnapshot,
    Import,
    ImportRow,
    ImportStatus,
    ImportType,
    Instrument,
    Platform,
    PlatformAlias,
    Transaction,
    TransactionFunding,
    TransactionType,
)
from app.schemas.schemas import AccountTransactionCreate, ContributionCreate

FIRST_TRACKED_YEAR = 2021
FHSA_ANNUAL_LIMIT = 8000.0
FHSA_CARRY_FORWARD_LIMIT = 8000.0
FHSA_LIFETIME_LIMIT = 40000.0
BACKUP_FORMAT = "master-control-terminal-export"
BACKUP_FORMAT_VERSION = 2
FUNDING_SOURCE_TYPES = {TransactionType.contribution, TransactionType.dividend_interest, TransactionType.transfer}
CENT = Decimal("0.01")
LEGACY_BACKUP_TABLE_NAMES = {"holding_snapshots": "holdings_snapshots"}
BACKUP_EXCLUDED_TABLE_NAMES = {"audit_logs"}
CATEGORY_OPTIONS = {
    "Cash": ["Cash"],
    "Bond": ["Bond", "GIC", "Money Market"],
    "Balanced": ["Balanced", "Target Date Fund"],
    "All Equity": [
        "All Equity",
        "Canadian Equity",
        "US Equity",
        "International Equity",
        "Emerging Markets",
        "Stock",
        "REIT",
        "Gold ETF",
        "Crypto",
    ],
    "Income": ["Dividend", "Interest"],
    "Other": ["Other"],
}


class ConflictError(ValueError):
    """The request is valid but clashes with saved data (HTTP 409)."""


def _cents(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(CENT, rounding=ROUND_HALF_UP)


def tracked_years(db: Session, today: date | None = None) -> list[int]:
    current_year = (today or date.today()).year
    first_transaction = db.scalar(select(func.min(Transaction.transaction_date)))
    first_limit = db.scalar(select(func.min(ContributionLimit.tax_year)))
    candidates = [current_year]
    if first_transaction:
        candidates.append(first_transaction.year)
    if first_limit:
        candidates.append(int(first_limit))
    return list(range(max(FIRST_TRACKED_YEAR, min(candidates)), current_year + 1))


def _backup_tables():
    return [table for table in Base.metadata.sorted_tables if table.name not in BACKUP_EXCLUDED_TABLE_NAMES]


def _dump_json(value):
    return json.dumps(value, sort_keys=True) if value is not None else None


def _audit_value(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return value


def _row_payload(row, extra: dict | None = None) -> dict:
    payload = {column.name: _audit_value(getattr(row, column.name)) for column in row.__table__.columns}
    if extra:
        payload.update(extra)
    return payload


def _funding_payload(db: Session, transaction_id: int):
    return [
        _row_payload(funding)
        for funding in db.scalars(
            select(TransactionFunding)
            .where(TransactionFunding.transaction_id == transaction_id)
            .order_by(TransactionFunding.id)
        )
    ]


def _transaction_payload(db: Session, txn: Transaction) -> dict:
    return _row_payload(txn, {"funding_contributions": _funding_payload(db, txn.id)})


def log_audit(
    db: Session,
    operation: str,
    table_name: str,
    *,
    row_id=None,
    summary: str | None = None,
    before=None,
    after=None,
    source: str | None = None,
) -> None:
    db.add(
        AuditLog(
            operation=operation,
            table_name=table_name,
            row_id=str(row_id) if row_id is not None else None,
            summary=summary,
            before_json=_dump_json(before),
            after_json=_dump_json(after),
            source=source,
        )
    )


def _rows_for_export(db: Session, table):
    statement = select(table)
    if "id" in table.c:
        statement = statement.order_by(table.c.id)
    return [dict(row) for row in db.execute(statement).mappings()]


def _restore_value(column, value):
    if value is None:
        return None
    if isinstance(column.type, DateTime) and isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    if isinstance(column.type, Date) and isinstance(value, str):
        return date.fromisoformat(value)
    if isinstance(column.type, SqlEnum) and isinstance(value, str):
        return column.type.python_type(value)
    return value


def _reset_sequence(db: Session, table) -> None:
    if db.bind is None or db.bind.dialect.name != "postgresql":
        return
    if "id" not in table.c:
        return
    max_id = db.scalar(select(func.max(table.c.id))) or 0
    db.execute(
        text(
            f"SELECT setval(pg_get_serial_sequence('{table.name}', 'id'), :value, :is_called)"
        ),
        {"value": max_id or 1, "is_called": max_id > 0},
    )


def seed_reference_data(db: Session) -> None:
    seed_counts = db.execute(
        select(
            select(func.count(Account.id)).scalar_subquery(),
            select(func.count(Platform.id)).scalar_subquery(),
            select(func.count(PlatformAlias.id)).scalar_subquery(),
            select(func.count(Category.id)).scalar_subquery(),
        )
    ).one()
    minimum_counts = (3, 5, 10, sum(len(options) for options in CATEGORY_OPTIONS.values()))
    if all(count >= minimum for count, minimum in zip(seed_counts, minimum_counts)):
        return

    for account_name in ["RRSP", "TFSA", "FHSA"]:
        if not db.scalar(select(Account).where(Account.name == account_name)):
            db.add(Account(name=account_name))

    for name in ["Wealthsimple", "EQ Bank", "CIBC", "Quest Trade", "Sun Life"]:
        if not db.scalar(select(Platform).where(Platform.canonical_name == name)):
            db.add(Platform(canonical_name=name))

    db.flush()

    alias_map = {
        "ws": "Wealthsimple",
        "wealthsimple": "Wealthsimple",
        "eq": "EQ Bank",
        "eq bank": "EQ Bank",
        "qt": "Quest Trade",
        "quest trade": "Quest Trade",
        "questrade": "Quest Trade",
        "sunlife": "Sun Life",
        "sun life": "Sun Life",
        "cibc": "CIBC",
    }
    for alias, target in alias_map.items():
        platform = db.scalar(select(Platform).where(Platform.canonical_name == target))
        exists = db.scalar(select(PlatformAlias).where(func.lower(PlatformAlias.alias) == alias))
        if platform and not exists:
            db.add(PlatformAlias(alias=alias, platform_id=platform.id))

    for broad, precise_options in CATEGORY_OPTIONS.items():
        for precise in precise_options:
            exists = db.scalar(
                select(Category).where(
                    func.lower(Category.broad) == broad.lower(),
                    func.lower(Category.precise) == precise.lower(),
                )
            )
            if not exists:
                db.add(Category(broad=broad, precise=precise))

    db.commit()


def seed_contribution_limits(db: Session, today: date | None = None) -> None:
    # Baseline rows for a fresh database, plus the current year's row once a new year starts.
    current_year = (today or date.today()).year
    seeded = {
        "RRSP": {2024: 16840, 2025: 17324, 2026: 0},
        "FHSA": {2024: 8000, 2025: 8000, 2026: 8000},
        "TFSA": {2024: 7000, 2025: 7000, 2026: 7000},
    }
    existing = {
        (account_id, tax_year): new_room
        for account_id, tax_year, new_room in db.execute(
            select(ContributionLimit.account_id, ContributionLimit.tax_year, ContributionLimit.new_room)
        )
    }
    for account_name, years in seeded.items():
        account = db.scalar(select(Account).where(Account.name == account_name))
        if not account:
            continue
        rows = {str(year): new_room for year, new_room in years.items()}
        if str(current_year) not in rows:
            previous_tfsa_room = existing.get((account.id, str(current_year - 1)), years.get(current_year - 1, 0))
            rows[str(current_year)] = {"FHSA": FHSA_ANNUAL_LIMIT, "TFSA": previous_tfsa_room}.get(account_name, 0)
        for tax_year, new_room in rows.items():
            if (account.id, tax_year) not in existing:
                db.add(ContributionLimit(account_id=account.id, tax_year=tax_year, new_room=new_room))
    db.commit()


def normalize_platform(db: Session, raw_name: str | None) -> Platform | None:
    if not raw_name:
        return None
    normalized = raw_name.strip().lower()
    alias = db.scalar(select(PlatformAlias).where(func.lower(PlatformAlias.alias) == normalized))
    if alias:
        return db.get(Platform, alias.platform_id)
    direct = db.scalar(select(Platform).where(func.lower(Platform.canonical_name) == normalized))
    if direct:
        return direct
    created = Platform(canonical_name=raw_name.strip())
    db.add(created)
    db.flush()
    db.add(PlatformAlias(alias=normalized, platform_id=created.id))
    db.flush()
    return created


def get_account(db: Session, name: str) -> Account:
    account = db.scalar(select(Account).where(func.lower(Account.name) == name.strip().lower()))
    if not account:
        raise LookupError(f"account {name} was not found")
    return account


def get_or_create_instrument(db: Session, symbol: str | None, name: str | None = None) -> Instrument | None:
    if not symbol:
        return None
    normalized = symbol.strip().upper()
    inst = db.scalar(select(Instrument).where(func.lower(Instrument.symbol) == normalized.lower()))
    if inst:
        return inst
    inst = Instrument(symbol=normalized, name=name, provider_symbol=normalized, provider="yfinance")
    db.add(inst)
    db.flush()
    return inst


def get_or_create_custom_instrument(db: Session, symbol: str | None, name: str | None = None) -> Instrument | None:
    if not symbol:
        return None
    value = symbol.strip()
    inst = db.scalar(select(Instrument).where(func.lower(Instrument.symbol) == value.lower()))
    if inst and inst.provider:
        # A priced instrument owns this symbol; never strip its provider data, use a manual twin instead.
        value = f"{value} (manual)"
        inst = db.scalar(select(Instrument).where(func.lower(Instrument.symbol) == value.lower()))
    if not inst:
        inst = Instrument(symbol=value, asset_type="manual", is_active=False)
        db.add(inst)
    inst.name = name or inst.name or value
    db.flush()
    return inst


def resolve_instrument(db: Session, payload: AccountTransactionCreate) -> Instrument | None:
    instrument_id = getattr(payload, "instrument_id", None)
    if instrument_id:
        instrument = db.get(Instrument, instrument_id)
        if not instrument:
            raise ValueError("selected symbol was not found")
        return instrument
    symbol = getattr(payload, "symbol", None)
    instrument_name = getattr(payload, "instrument_name", None)
    if not symbol:
        return None
    if getattr(payload, "is_custom_symbol", False):
        return get_or_create_custom_instrument(db, symbol, instrument_name)
    return get_or_create_instrument(db, symbol, instrument_name)


def upsert_manual_valuation(db: Session, payload) -> HoldingSnapshot:
    account = get_account(db, payload.account_name)
    platform = normalize_platform(db, payload.platform_name)
    instrument = resolve_instrument(db, payload)
    category = get_or_create_category(db, payload.broad_category, payload.precise_category)
    snapshot = db.scalar(
        select(HoldingSnapshot)
        .where(
            HoldingSnapshot.account_id == (account.id if account else None),
            HoldingSnapshot.platform_id == (platform.id if platform else None),
            HoldingSnapshot.instrument_id == (instrument.id if instrument else None),
            HoldingSnapshot.category_id == (category.id if category else None),
            HoldingSnapshot.record_type == "holding",
        )
        .order_by(HoldingSnapshot.snapshot_date.desc(), HoldingSnapshot.id.desc())
    )
    before = _row_payload(snapshot) if snapshot else None
    if not snapshot:
        snapshot = HoldingSnapshot(record_type="holding")
        db.add(snapshot)
    snapshot.snapshot_date = payload.snapshot_date
    snapshot.account_id = account.id if account else None
    snapshot.platform_id = platform.id if platform else None
    snapshot.instrument_id = instrument.id if instrument else None
    snapshot.category_id = category.id if category else None
    snapshot.market_value = payload.market_value
    db.flush()
    log_audit(
        db,
        "update" if before else "create",
        "holdings_snapshots",
        row_id=snapshot.id,
        summary="Manual valuation saved",
        before=before,
        after=_row_payload(snapshot),
        source="manual-valuations",
    )
    db.commit()
    db.refresh(snapshot)
    return snapshot


def get_or_create_category(db: Session, broad: str | None, precise: str | None) -> Category | None:
    if not broad and not precise:
        return None
    broad_value = (broad or "Other").strip()
    precise_value = (precise or broad_value).strip()
    category = db.scalar(
        select(Category).where(
            func.lower(Category.broad) == broad_value.lower(),
            func.lower(Category.precise) == precise_value.lower(),
        )
    )
    if category:
        return category
    category = Category(broad=broad_value, precise=precise_value)
    db.add(category)
    db.flush()
    return category


def _save_transaction(
    db: Session,
    payload: ContributionCreate | AccountTransactionCreate,
    txn: Transaction | None = None,
    transaction_type: TransactionType | None = None,
) -> Transaction:
    before = _transaction_payload(db, txn) if txn else None
    account = get_account(db, payload.account_name)
    platform = normalize_platform(db, payload.platform_name)
    source_platform = normalize_platform(db, getattr(payload, "source_platform_name", None))
    broad_category = getattr(payload, "broad_category", None)
    precise_category = getattr(payload, "precise_category", None)
    quantity = getattr(payload, "quantity", None)
    fees = getattr(payload, "fees", 0)
    currency = getattr(payload, "currency", "CAD")
    source_amount = getattr(payload, "source_amount", None)
    source_currency = getattr(payload, "source_currency", None)
    fee_currency = getattr(payload, "fee_currency", None)
    reversal_of_id = getattr(payload, "reversal_of_id", None)
    contribution_id = getattr(payload, "contribution_id", None)
    resolved_type = transaction_type or getattr(payload, "transaction_type")
    instrument = resolve_instrument(db, payload)
    category = get_or_create_category(db, broad_category, precise_category)

    if txn is None:
        txn = Transaction()
        db.add(txn)

    txn.transaction_type = resolved_type
    txn.transaction_date = payload.transaction_date
    txn.account_id = account.id if account else None
    txn.platform_id = platform.id if platform else None
    txn.source_platform_id = source_platform.id if source_platform else None
    txn.instrument_id = instrument.id if instrument else None
    txn.category_id = category.id if category else None
    txn.amount = payload.amount
    txn.currency = currency
    txn.source_amount = source_amount
    txn.source_currency = source_currency
    txn.quantity = quantity
    txn.fees = fees
    txn.fee_currency = fee_currency
    txn.notes = payload.notes
    txn.reversal_of_id = reversal_of_id
    txn.contribution_id = contribution_id
    db.flush()
    if isinstance(payload, AccountTransactionCreate):
        _replace_transaction_fundings(db, txn, payload)
        db.flush()

    _validate_sell_quantity(db, txn)
    log_audit(
        db,
        "update" if before else "create",
        "transactions",
        row_id=txn.id,
        summary=f"{txn.transaction_type.value} transaction saved",
        before=before,
        after=_transaction_payload(db, txn),
        source="transactions",
    )
    db.commit()
    db.refresh(txn)
    return txn


def create_contribution(db: Session, payload: ContributionCreate) -> Transaction:
    return _save_transaction(db, payload, transaction_type=TransactionType.contribution)


def update_contribution(db: Session, transaction_id: int, payload: ContributionCreate) -> Transaction | None:
    txn = db.get(Transaction, transaction_id)
    if not txn or txn.transaction_type != TransactionType.contribution:
        return None
    _check_funding_source_edit(db, txn, TransactionType.contribution, payload.account_name, payload.amount)
    return _save_transaction(db, payload, txn=txn, transaction_type=TransactionType.contribution)


def create_account_transaction(db: Session, payload: AccountTransactionCreate) -> Transaction:
    _validate_contribution_funding(db, payload)
    return _save_transaction(db, payload)


def update_account_transaction(db: Session, transaction_id: int, payload: AccountTransactionCreate) -> Transaction | None:
    txn = db.get(Transaction, transaction_id)
    if not txn or txn.transaction_type == TransactionType.contribution:
        return None
    _check_funding_source_edit(db, txn, payload.transaction_type, payload.account_name, payload.amount)
    _validate_contribution_funding(db, payload, txn)
    return _save_transaction(db, payload, txn=txn)


def delete_transaction(db: Session, transaction_id: int, contribution: bool) -> None:
    txn = db.get(Transaction, transaction_id)
    if not txn or (txn.transaction_type == TransactionType.contribution) != contribution:
        raise LookupError("transaction not found")
    if db.scalar(select(func.count()).select_from(TransactionFunding).where(TransactionFunding.contribution_id == txn.id)):
        raise ConflictError("other transactions are funded by this entry; edit or delete them first")
    before = _transaction_payload(db, txn)
    summary = f"{txn.transaction_type.value} transaction deleted"
    db.query(TransactionFunding).filter(TransactionFunding.transaction_id == txn.id).delete()
    db.delete(txn)
    db.flush()
    log_audit(db, "delete", "transactions", row_id=transaction_id, summary=summary, before=before, source="transactions")
    db.commit()


def _check_funding_source_edit(
    db: Session, txn: Transaction, new_type: TransactionType, new_account_name: str, new_amount: float
) -> None:
    used = _cents(_contribution_usage(db, txn.id))
    if not used:
        return
    account = db.get(Account, txn.account_id) if txn.account_id else None
    if new_type not in FUNDING_SOURCE_TYPES or not account or account.name.lower() != new_account_name.strip().lower():
        raise ConflictError(f"this entry already funds ${used:.2f} of other transactions, so its type and account cannot change")
    if _cents(new_amount) < used:
        raise ConflictError(f"this entry already funds ${used:.2f} of other transactions, so its amount cannot go below that")


def _validate_sell_quantity(db: Session, txn: Transaction) -> None:
    if txn.transaction_type != TransactionType.investment_sell or not txn.quantity:
        return
    signed_quantity = case(
        (Transaction.transaction_type == TransactionType.investment_sell, -Transaction.quantity),
        else_=Transaction.quantity,
    )
    held = db.scalar(
        select(func.coalesce(func.sum(signed_quantity), 0)).where(
            Transaction.account_id == txn.account_id,
            Transaction.platform_id == txn.platform_id,
            Transaction.instrument_id == txn.instrument_id,
            Transaction.transaction_type.in_(
                [
                    TransactionType.investment_buy,
                    TransactionType.dividend_reinvestment,
                    TransactionType.quantity_adjustment,
                    TransactionType.investment_sell,
                ]
            ),
            Transaction.quantity.is_not(None),
            Transaction.transaction_date <= txn.transaction_date,
            Transaction.id != txn.id,
        )
    )
    # ponytail: tolerance absorbs float quantities until the column is exact numeric.
    if float(txn.quantity) > float(held or 0) + 1e-9:
        raise ValueError(f"cannot sell {float(txn.quantity):g} units: only {float(held or 0):g} held on {txn.transaction_date}")


def _funding_contributions(
    db: Session, payload: AccountTransactionCreate, transaction: Transaction | None = None
):
    if payload.funding_cash_sources:
        sources = _available_funding_transactions(db, payload.account_name, transaction)
        allocations = []
        for cash_source in payload.funding_cash_sources:
            remaining_to_allocate = _cents(cash_source.amount)
            platform_sources = [
                source
                for source in sources
                if source["platform_name"].lower() == cash_source.platform_name.lower()
            ]
            available = sum((_cents(source["remaining_amount"]) for source in platform_sources), Decimal("0"))
            if remaining_to_allocate > available:
                raise ValueError(f"{cash_source.platform_name} cash has only ${available:.2f} remaining")
            for source in platform_sources:
                amount = min(remaining_to_allocate, _cents(source["remaining_amount"]))
                if amount:
                    allocations.append({"contribution_id": source["id"], "amount": float(amount)})
                    remaining_to_allocate -= amount
                if not remaining_to_allocate:
                    break
        return allocations
    if payload.funding_contributions:
        return payload.funding_contributions
    if payload.contribution_id:
        return [
            {
                "contribution_id": payload.contribution_id,
                "amount": (payload.source_amount if payload.source_amount is not None else payload.amount) + (payload.fees or 0),
            }
        ]
    return []


def _replace_transaction_fundings(db: Session, transaction: Transaction, payload: AccountTransactionCreate) -> None:
    db.query(TransactionFunding).filter(TransactionFunding.transaction_id == transaction.id).delete()
    db.add_all(
        [
            TransactionFunding(
                transaction_id=transaction.id,
                contribution_id=funding.contribution_id if hasattr(funding, "contribution_id") else funding["contribution_id"],
                amount=funding.amount if hasattr(funding, "amount") else funding["amount"],
            )
            for funding in _funding_contributions(db, payload, transaction)
        ]
    )


def _contribution_usage(db: Session, contribution_id: int, transaction: Transaction | None = None) -> float:
    funding_usage = select(func.coalesce(func.sum(TransactionFunding.amount), 0)).where(
        TransactionFunding.contribution_id == contribution_id
    )
    legacy_usage = select(func.coalesce(func.sum(Transaction.amount + func.coalesce(Transaction.fees, 0)), 0)).outerjoin(
        TransactionFunding, TransactionFunding.transaction_id == Transaction.id
    ).where(
        Transaction.contribution_id == contribution_id,
        Transaction.transaction_type == TransactionType.investment_buy,
        TransactionFunding.id.is_(None),
    )
    if transaction:
        funding_usage = funding_usage.where(TransactionFunding.transaction_id != transaction.id)
        legacy_usage = legacy_usage.where(Transaction.id != transaction.id)
    return float(db.scalar(funding_usage) or 0) + float(db.scalar(legacy_usage) or 0)


def _validate_contribution_funding(
    db: Session, payload: AccountTransactionCreate, transaction: Transaction | None = None
) -> None:
    fundings = _funding_contributions(db, payload, transaction)
    if payload.transaction_type not in {TransactionType.investment_buy, TransactionType.transfer}:
        if fundings:
            raise ValueError("funding sources are only supported for investment buys and transfers")
        return

    if payload.transaction_type == TransactionType.transfer:
        if not payload.source_platform_name:
            raise ValueError("source platform is required for transfers")
        if payload.source_platform_name.lower() == payload.platform_name.lower():
            raise ValueError("transfer source and destination platforms must differ")

    if not fundings:
        return
    funding_total = _cents(sum(Decimal(str(funding.amount if hasattr(funding, "amount") else funding["amount"])) for funding in fundings))
    cash_amount = payload.source_amount if payload.source_amount is not None else payload.amount
    if funding_total != _cents(Decimal(str(cash_amount)) + Decimal(str(payload.fees or 0))):
        raise ValueError("funding contributions must total the transaction amount plus fees")

    for funding in fundings:
        contribution_id = funding.contribution_id if hasattr(funding, "contribution_id") else funding["contribution_id"]
        amount = float(funding.amount if hasattr(funding, "amount") else funding["amount"])
        contribution = db.get(Transaction, contribution_id)
        if not contribution or contribution.transaction_type not in {
            TransactionType.contribution,
            TransactionType.dividend_interest,
            TransactionType.transfer,
        }:
            raise ValueError("selected funding source was not found")

        contribution_account = db.get(Account, contribution.account_id) if contribution.account_id else None
        if not contribution_account or contribution_account.name.lower() != payload.account_name.lower():
            raise ValueError("selected funding source belongs to a different account")
        if payload.transaction_type == TransactionType.transfer:
            funding_platform = db.get(Platform, contribution.platform_id) if contribution.platform_id else None
            if not funding_platform or funding_platform.canonical_name.lower() != payload.source_platform_name.lower():
                raise ValueError("transfer funding sources must belong to the source platform")
        remaining = _cents(contribution.amount) - _cents(_contribution_usage(db, contribution.id, transaction))
        if _cents(amount) > remaining:
            raise ValueError(f"selected funding source has only ${remaining:.2f} remaining")


def list_available_contributions(
    db: Session,
    account: str,
    transaction: Transaction | None = None,
):
    sources = _available_funding_transactions(db, account, transaction)
    available = {}
    for source in sources:
        platform_name = source["platform_name"]
        if not platform_name:
            continue
        pool = available.setdefault(
            platform_name,
            {
                "id": source["platform_id"],
                "platform_name": platform_name,
                "source_label": "Cash",
                "remaining_amount": 0.0,
            },
        )
        pool["remaining_amount"] = round(pool["remaining_amount"] + source["remaining_amount"], 2)
    return sorted(available.values(), key=lambda pool: pool["platform_name"].lower())


def _available_funding_transactions(
    db: Session, account: str, transaction: Transaction | None = None
):
    contributions = db.execute(
        select(Transaction, Platform.canonical_name)
        .join(Account, Transaction.account_id == Account.id)
        .outerjoin(Platform, Transaction.platform_id == Platform.id)
        .where(
            Transaction.transaction_type.in_(
                [TransactionType.contribution, TransactionType.dividend_interest, TransactionType.transfer]
            ),
            func.lower(Account.name) == account.lower(),
        )
        .order_by(Transaction.transaction_date, Transaction.id)
    ).all()
    available = []
    for contribution, platform_name in contributions:
        remaining = float(_cents(contribution.amount) - _cents(_contribution_usage(db, contribution.id, transaction)))
        if remaining <= 0:
            continue
        available.append(
            {
                "id": contribution.id,
                "platform_name": platform_name,
                "platform_id": contribution.platform_id,
                "remaining_amount": remaining,
            }
        )
    return available


def list_transactions(
    db: Session, transaction_type=None, account=None, platform=None, symbol=None, year=None, page=1, sort_direction="desc", page_size=10
):
    q = (
        select(
            Transaction,
            Account.name.label("account_name"),
            Platform.canonical_name.label("platform_name"),
            Instrument.symbol.label("symbol"),
            Category.broad.label("broad_category"),
            Category.precise.label("precise_category"),
        )
        .outerjoin(Account, Transaction.account_id == Account.id)
        .outerjoin(Platform, Transaction.platform_id == Platform.id)
        .outerjoin(Instrument, Transaction.instrument_id == Instrument.id)
        .outerjoin(Category, Transaction.category_id == Category.id)
    )
    if transaction_type:
        q = q.where(Transaction.transaction_type == transaction_type)
    if account:
        q = q.where(func.lower(Account.name) == account.lower())
    if platform:
        q = q.where(func.lower(Platform.canonical_name) == platform.lower())
    if symbol:
        q = q.where(func.lower(Instrument.symbol) == symbol.lower())
    if year:
        q = q.where(func.extract("year", Transaction.transaction_date) == year)
    return _page(db, q, page, page_size, sort_direction)


def _page(db: Session, q, page: int, page_size: int, sort_direction: str):
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    order = Transaction.transaction_date.asc() if sort_direction == "asc" else Transaction.transaction_date.desc()
    id_order = Transaction.id.asc() if sort_direction == "asc" else Transaction.id.desc()
    return db.execute(q.order_by(order, id_order).offset((page - 1) * page_size).limit(page_size)).all(), total


def _rrsp_contribution_deadline(tax_year: int):
    deadline = date(tax_year + 1, 1, 1) + timedelta(days=59)
    if deadline.weekday() == 5:
        return deadline + timedelta(days=2)
    if deadline.weekday() == 6:
        return deadline + timedelta(days=1)
    return deadline


def _contribution_tax_year_bounds(account_name: str | None, tax_year: int):
    if account_name and account_name.lower() == "rrsp":
        return _rrsp_contribution_deadline(tax_year - 1) + timedelta(days=1), _rrsp_contribution_deadline(tax_year) + timedelta(days=1)
    return date(tax_year, 1, 1), date(tax_year + 1, 1, 1)


def _rrsp_tax_year_filter(tax_year: int):
    calendar_start, calendar_end = _contribution_tax_year_bounds(None, tax_year)
    rrsp_start, rrsp_end = _contribution_tax_year_bounds("RRSP", tax_year)
    return or_(
        and_(
            func.lower(Account.name) == "rrsp",
            Transaction.transaction_date >= rrsp_start,
            Transaction.transaction_date < rrsp_end,
        ),
        and_(
            or_(Account.name.is_(None), func.lower(Account.name) != "rrsp"),
            Transaction.transaction_date >= calendar_start,
            Transaction.transaction_date < calendar_end,
        ),
    )


def list_contributions(db: Session, account=None, platform=None, year=None):
    q = (
        select(
            Transaction,
            Account.name.label("account_name"),
            Platform.canonical_name.label("platform_name"),
            Instrument.symbol.label("symbol"),
            Category.broad.label("broad_category"),
            Category.precise.label("precise_category"),
        )
        .outerjoin(Account, Transaction.account_id == Account.id)
        .outerjoin(Platform, Transaction.platform_id == Platform.id)
        .outerjoin(Instrument, Transaction.instrument_id == Instrument.id)
        .outerjoin(Category, Transaction.category_id == Category.id)
        .where(Transaction.transaction_type == TransactionType.contribution)
        .order_by(Transaction.transaction_date.desc(), Transaction.id.desc())
    )
    if account:
        q = q.where(func.lower(Account.name) == account.lower())
    if platform:
        q = q.where(func.lower(Platform.canonical_name) == platform.lower())
    if year:
        q = q.where(_rrsp_tax_year_filter(year))
    return db.execute(q).all()


def list_account_transactions(
    db: Session, account=None, platform=None, symbol=None, year=None, transaction_type=None, page=1, sort_direction="desc", page_size=10
):
    q = (
        select(
            Transaction,
            Account.name.label("account_name"),
            Platform.canonical_name.label("platform_name"),
            Instrument.symbol.label("symbol"),
            Category.broad.label("broad_category"),
            Category.precise.label("precise_category"),
        )
        .outerjoin(Account, Transaction.account_id == Account.id)
        .outerjoin(Platform, Transaction.platform_id == Platform.id)
        .outerjoin(Instrument, Transaction.instrument_id == Instrument.id)
        .outerjoin(Category, Transaction.category_id == Category.id)
        .where(Transaction.transaction_type != TransactionType.contribution)
    )
    if account:
        q = q.where(func.lower(Account.name) == account.lower())
    if platform:
        q = q.where(func.lower(Platform.canonical_name) == platform.lower())
    if symbol:
        q = q.where(func.lower(Instrument.symbol) == symbol.lower())
    if year:
        # Activity lists use calendar years; RRSP tax-year bounds apply only to contribution room and the contribution list.
        q = q.where(func.extract("year", Transaction.transaction_date) == year)
    if transaction_type:
        q = q.where(Transaction.transaction_type == transaction_type)
    return _page(db, q, page, page_size, sort_direction)


def _contribution_tax_year(account_name: str | None, transaction_date: date) -> int:
    year = transaction_date.year
    if account_name and account_name.lower() == "rrsp" and transaction_date <= _rrsp_contribution_deadline(year - 1):
        return year - 1
    return year


def _room_ledger(db: Session):
    new_rooms = {
        (account_id, int(tax_year)): float(new_room)
        for account_id, tax_year, new_room in db.execute(
            select(ContributionLimit.account_id, ContributionLimit.tax_year, ContributionLimit.new_room)
        )
    }
    used = {}
    withdrawn = {}
    rows = db.execute(
        select(Transaction.account_id, Account.name, Transaction.transaction_type, Transaction.transaction_date, Transaction.amount)
        .join(Account, Transaction.account_id == Account.id)
        .where(Transaction.transaction_type.in_([TransactionType.contribution, TransactionType.withdrawal]))
    )
    for account_id, account_name, transaction_type, transaction_date, amount in rows:
        if transaction_type == TransactionType.contribution:
            key = (account_id, _contribution_tax_year(account_name, transaction_date))
            used[key] = used.get(key, 0.0) + float(amount)
        else:
            key = (account_id, transaction_date.year)
            withdrawn[key] = withdrawn.get(key, 0.0) + float(amount)
    return new_rooms, used, withdrawn


def _account_room_rows(account: Account, years: list[int], ledger) -> list[dict]:
    new_rooms, used, withdrawn = ledger
    kind = account.name.upper()
    rows = []
    previous = None
    contributed_before = 0.0
    for year in years:
        new_room = new_rooms.get((account.id, year), 0.0)
        unused_room = previous["total_room"] - previous["used"] if previous else 0.0
        if kind == "FHSA":
            # CRA: unused FHSA room carries forward at most $8,000, and room never exceeds the $40,000 lifetime limit.
            unused_room = min(max(unused_room, 0.0), FHSA_CARRY_FORWARD_LIMIT)
            total_room = min(unused_room + new_room, max(FHSA_LIFETIME_LIMIT - contributed_before, 0.0))
        else:
            if kind == "TFSA":
                # CRA: TFSA withdrawals are added back as room at the start of the next year.
                unused_room += withdrawn.get((account.id, year - 1), 0.0)
            total_room = unused_room + new_room
        year_used = used.get((account.id, year), 0.0)
        previous = {
            "account": account.name,
            "tax_year": str(year),
            "unused_room": unused_room,
            "new_room": new_room,
            "total_room": total_room,
            "used": year_used,
            "remaining": total_room - year_used,
        }
        rows.append(previous)
        contributed_before += year_used
    return rows


def get_contribution_room(db: Session, tax_year: int):
    years = tracked_years(db)
    if tax_year not in years:
        return []
    ledger = _room_ledger(db)
    result = []
    for account in db.scalars(select(Account).order_by(Account.name)):
        row = next(row for row in _account_room_rows(account, years, ledger) if row["tax_year"] == str(tax_year))
        result.append({key: row[key] for key in ("account", "tax_year", "total_room", "used", "remaining")})
    return result


def get_all_contribution_room(db: Session):
    years = tracked_years(db)
    ledger = _room_ledger(db)
    result = []
    for account in db.scalars(select(Account).order_by(Account.name)):
        rows = _account_room_rows(account, years, ledger)
        used = sum(row["used"] for row in rows)
        remaining = rows[-1]["remaining"]
        result.append({"account": account.name, "tax_year": "All", "total_room": remaining + used, "used": used, "remaining": remaining})
    return result


def get_contribution_used(db: Session, account_id: int, tax_year: int):
    return _room_ledger(db)[1].get((account_id, tax_year), 0.0)


def list_contribution_limits(db: Session):
    years = tracked_years(db)
    ledger = _room_ledger(db)
    rows = []
    for account in db.scalars(select(Account).order_by(Account.name)):
        rows.extend(_account_room_rows(account, years, ledger))
    return rows


def upsert_contribution_limit(db: Session, account_name: str, tax_year: str, new_room: float):
    account = get_account(db, account_name)
    limit = db.scalar(
        select(ContributionLimit).where(
            ContributionLimit.account_id == account.id,
            ContributionLimit.tax_year == tax_year,
        )
    )
    before = _row_payload(limit) if limit else None
    if not limit:
        limit = ContributionLimit(account_id=account.id, tax_year=tax_year)
        db.add(limit)

    limit.new_room = new_room
    db.flush()
    log_audit(
        db,
        "update" if before else "create",
        "contribution_limits",
        row_id=limit.id,
        summary=f"{account.name} {tax_year} contribution limit saved",
        before=before,
        after=_row_payload(limit),
        source="contribution-limits",
    )
    db.commit()
    years = sorted(set(tracked_years(db)) | {int(tax_year)})
    return next(row for row in _account_room_rows(account, years, _room_ledger(db)) if row["tax_year"] == tax_year)


def create_import_preview(db: Session, import_type: ImportType, source_filename: str, preview_rows: list[dict]):
    imp = Import(import_type=import_type, source_filename=source_filename, status=ImportStatus.parsed)
    db.add(imp)
    db.flush()
    for i, row in enumerate(preview_rows, start=1):
        db.add(ImportRow(import_id=imp.id, row_number=i, payload_json=json.dumps(row), error=None))
    db.commit()
    return imp


def export_all_data(db: Session):
    return {table.name: _rows_for_export(db, table) for table in _backup_tables()}


def restore_all_data(db: Session, payload: dict):
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("Backup payload is missing a data object")
    data = dict(data)
    for legacy_name, table_name in LEGACY_BACKUP_TABLE_NAMES.items():
        if legacy_name in data and table_name not in data:
            data[table_name] = data.pop(legacy_name)
    data = {table_name: rows for table_name, rows in data.items() if table_name not in BACKUP_EXCLUDED_TABLE_NAMES}

    tables = _backup_tables()
    table_names = {table.name for table in tables}
    unknown_tables = sorted(set(data) - table_names)
    if unknown_tables:
        raise ValueError(f"Backup contains unsupported tables: {', '.join(unknown_tables)}")
    if any(not isinstance(rows, list) for rows in data.values()):
        raise ValueError("Backup table data must be a list of rows")
    if any(not isinstance(row, dict) for rows in data.values() for row in rows):
        raise ValueError("Backup rows must be objects")

    for table in reversed(tables):
        db.execute(table.delete())
    db.flush()

    deferred_references = []
    for table in tables:
        self_references = {foreign_key.parent.name for foreign_key in table.foreign_keys if foreign_key.column.table is table}
        rows = []
        for row in data.get(table.name, []):
            values = {
                column.name: _restore_value(column, row[column.name])
                for column in table.columns
                if column.name in row
            }
            if self_references:
                references = {name: values[name] for name in self_references if values.get(name) is not None}
                if references:
                    deferred_references.append((table, {column.name: values[column.name] for column in table.primary_key}, references))
                    values.update({name: None for name in references})
            rows.append(values)
        if rows:
            db.execute(table.insert(), rows)
    db.flush()

    for table, primary_key, references in deferred_references:
        db.execute(
            table.update().where(and_(*(table.c[name] == value for name, value in primary_key.items()))).values(**references)
        )

    for table in tables:
        _reset_sequence(db, table)
    log_audit(db, "restore", "all", summary="Backup restored", source="import-backup")
    db.commit()
