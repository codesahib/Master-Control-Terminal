import json
from datetime import date, datetime, timedelta

from sqlalchemy import Date, DateTime, Enum as SqlEnum, and_, case, func, or_, select, text
from sqlalchemy.orm import Session, aliased

from app.db.session import Base
from app.models.models import (
    Account,
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
from app.schemas.schemas import AccountTransactionCreate, ContributionCreate, TransactionCreate

TRACKED_YEARS = ["2023", "2024", "2025", "2026"]
LEGACY_BACKUP_TABLE_NAMES = {"holding_snapshots": "holdings_snapshots"}
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


def _backup_tables():
    return Base.metadata.sorted_tables


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
    if tuple(seed_counts) >= (3, 5, 10, sum(len(options) for options in CATEGORY_OPTIONS.values())):
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
    db.commit()
    db.refresh(created)
    return created


def get_or_create_account(db: Session, name: str | None) -> Account | None:
    if not name:
        return None
    normalized = name.strip().upper()
    acc = db.scalar(select(Account).where(func.lower(Account.name) == normalized.lower()))
    if acc:
        return acc
    acc = Account(name=normalized)
    db.add(acc)
    db.commit()
    db.refresh(acc)
    return acc


def get_or_create_instrument(db: Session, symbol: str | None, name: str | None = None) -> Instrument | None:
    if not symbol:
        return None
    normalized = symbol.strip().upper()
    inst = db.scalar(select(Instrument).where(func.lower(Instrument.symbol) == normalized.lower()))
    if inst:
        return inst
    inst = Instrument(symbol=normalized, name=name)
    db.add(inst)
    db.commit()
    db.refresh(inst)
    return inst


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
    db.commit()
    db.refresh(category)
    return category


def _save_transaction(
    db: Session,
    payload: TransactionCreate | ContributionCreate | AccountTransactionCreate,
    txn: Transaction | None = None,
    transaction_type: TransactionType | None = None,
) -> Transaction:
    account = get_or_create_account(db, payload.account_name)
    platform = normalize_platform(db, payload.platform_name)
    source_platform = normalize_platform(db, getattr(payload, "source_platform_name", None))
    symbol = getattr(payload, "symbol", None)
    instrument_name = getattr(payload, "instrument_name", None)
    broad_category = getattr(payload, "broad_category", None)
    precise_category = getattr(payload, "precise_category", None)
    quantity = getattr(payload, "quantity", None)
    fees = getattr(payload, "fees", 0)
    reversal_of_id = getattr(payload, "reversal_of_id", None)
    contribution_id = getattr(payload, "contribution_id", None)
    resolved_type = transaction_type or getattr(payload, "transaction_type")
    instrument = get_or_create_instrument(db, symbol, instrument_name)
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
    txn.quantity = quantity
    txn.fees = fees
    txn.notes = payload.notes
    txn.reversal_of_id = reversal_of_id
    txn.contribution_id = contribution_id
    db.flush()
    if isinstance(payload, AccountTransactionCreate):
        _replace_transaction_fundings(db, txn, payload)
    db.commit()
    db.refresh(txn)
    return txn


def create_transaction(db: Session, payload: TransactionCreate) -> Transaction:
    return _save_transaction(db, payload)


def update_transaction(db: Session, transaction_id: int, payload: TransactionCreate) -> Transaction | None:
    txn = db.get(Transaction, transaction_id)
    if not txn:
        return None
    return _save_transaction(db, payload, txn=txn)


def create_contribution(db: Session, payload: ContributionCreate) -> Transaction:
    return _save_transaction(db, payload, transaction_type=TransactionType.contribution)


def update_contribution(db: Session, transaction_id: int, payload: ContributionCreate) -> Transaction | None:
    txn = db.get(Transaction, transaction_id)
    if not txn or txn.transaction_type != TransactionType.contribution:
        return None
    return _save_transaction(db, payload, txn=txn, transaction_type=TransactionType.contribution)


def create_account_transaction(db: Session, payload: AccountTransactionCreate) -> Transaction:
    _validate_contribution_funding(db, payload)
    return _save_transaction(db, payload)


def update_account_transaction(db: Session, transaction_id: int, payload: AccountTransactionCreate) -> Transaction | None:
    txn = db.get(Transaction, transaction_id)
    if not txn or txn.transaction_type == TransactionType.contribution:
        return None
    _validate_contribution_funding(db, payload, txn)
    return _save_transaction(db, payload, txn=txn)


def _funding_contributions(
    db: Session, payload: AccountTransactionCreate, transaction: Transaction | None = None
):
    if payload.funding_cash_sources:
        sources = _available_funding_transactions(db, payload.account_name, transaction)
        allocations = []
        for cash_source in payload.funding_cash_sources:
            remaining_to_allocate = float(cash_source.amount)
            platform_sources = [
                source
                for source in sources
                if source["platform_name"].lower() == cash_source.platform_name.lower()
            ]
            available = round(sum(source["remaining_amount"] for source in platform_sources), 2)
            if round(remaining_to_allocate, 2) > available:
                raise ValueError(f"{cash_source.platform_name} cash has only ${available:.2f} remaining")
            for source in platform_sources:
                amount = min(remaining_to_allocate, source["remaining_amount"])
                if amount:
                    allocations.append({"contribution_id": source["id"], "amount": amount})
                    remaining_to_allocate = round(remaining_to_allocate - amount, 2)
                if not remaining_to_allocate:
                    break
        return allocations
    if payload.funding_contributions:
        return payload.funding_contributions
    if payload.contribution_id:
        return [
            {
                "contribution_id": payload.contribution_id,
                "amount": payload.amount + (payload.fees or 0),
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
    funding_total = sum(float(funding.amount if hasattr(funding, "amount") else funding["amount"]) for funding in fundings)
    transaction_total = payload.amount + (payload.fees or 0)
    if round(funding_total, 2) != round(transaction_total, 2):
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
        remaining = float(contribution.amount) - _contribution_usage(db, contribution.id, transaction)
        if round(amount, 2) > round(remaining, 2):
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
        remaining = round(float(contribution.amount) - _contribution_usage(db, contribution.id, transaction), 2)
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


def list_transaction_fundings(db: Session, transaction: Transaction):
    fundings = db.scalars(
        select(TransactionFunding)
        .where(TransactionFunding.transaction_id == transaction.id)
        .order_by(TransactionFunding.id)
    ).all()
    if fundings:
        result = []
        for funding in fundings:
            source = db.get(Transaction, funding.contribution_id)
            platform = db.get(Platform, source.platform_id) if source and source.platform_id else None
            result.append({
                "contribution_id": funding.contribution_id,
                "amount": float(funding.amount),
                "platform_name": platform.canonical_name if platform else None,
            })
        return result
    if transaction.contribution_id:
        source = db.get(Transaction, transaction.contribution_id)
        return [{
            "contribution_id": transaction.contribution_id,
            "amount": float(transaction.amount) + float(transaction.fees or 0),
            "platform_name": db.get(Platform, source.platform_id).canonical_name if source and source.platform_id else None,
        }]
    return []


def list_transactions(db: Session, transaction_type=None, account=None, platform=None, symbol=None, year=None):
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
        .order_by(Transaction.transaction_date.desc(), Transaction.id.desc())
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
    return db.execute(q).all()


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


def list_account_transactions(db: Session, account=None, platform=None, symbol=None, year=None):
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
        .order_by(Transaction.transaction_date.desc(), Transaction.id.desc())
    )
    if account:
        q = q.where(func.lower(Account.name) == account.lower())
    if platform:
        q = q.where(func.lower(Platform.canonical_name) == platform.lower())
    if symbol:
        q = q.where(func.lower(Instrument.symbol) == symbol.lower())
    if year:
        q = q.where(_rrsp_tax_year_filter(year))
    return db.execute(q).all()


def list_holdings(db: Session, account=None, year=None):
    as_of_date = date.today() if year is None or year >= date.today().year else date(year, 12, 31)
    source_platform = aliased(Platform)
    q = (
        select(
            Transaction,
            Account,
            Platform,
            source_platform,
            Instrument,
            Category,
        )
        .outerjoin(Account, Transaction.account_id == Account.id)
        .outerjoin(Platform, Transaction.platform_id == Platform.id)
        .outerjoin(source_platform, Transaction.source_platform_id == source_platform.id)
        .outerjoin(Instrument, Transaction.instrument_id == Instrument.id)
        .outerjoin(Category, Transaction.category_id == Category.id)
        .where(Transaction.transaction_date <= as_of_date)
        .order_by(Transaction.transaction_date, Transaction.id)
    )
    if account:
        q = q.where(func.lower(Account.name) == account.lower())

    cash = {}
    positions = {}
    for txn, account_row, platform, source_platform_row, instrument, category in db.execute(q):
        if not account_row:
            continue

        cash_key = (account_row.id, platform.id if platform else None)
        cash.setdefault(
            cash_key,
            {
                "account_name": account_row.name,
                "platform_name": platform.canonical_name if platform else None,
                "book_value": 0.0,
            },
        )

        if txn.transaction_type == TransactionType.contribution:
            cash[cash_key]["book_value"] += float(txn.amount)
            continue
        if txn.transaction_type == TransactionType.dividend_interest:
            cash[cash_key]["book_value"] += float(txn.amount) - float(txn.fees or 0)
            continue
        if txn.transaction_type == TransactionType.transfer:
            if source_platform_row:
                source_cash_key = (account_row.id, source_platform_row.id)
                cash.setdefault(
                    source_cash_key,
                    {
                        "account_name": account_row.name,
                        "platform_name": source_platform_row.canonical_name,
                        "book_value": 0.0,
                    },
                )
                cash[source_cash_key]["book_value"] -= float(txn.amount) + float(txn.fees or 0)
                cash[cash_key]["book_value"] += float(txn.amount)
            continue
        if txn.transaction_type not in {
            TransactionType.investment_buy,
            TransactionType.investment_sell,
            TransactionType.dividend_reinvestment,
        }:
            continue

        amount = float(txn.amount)
        fees = float(txn.fees or 0)
        if txn.transaction_type == TransactionType.investment_buy:
            cash[cash_key]["book_value"] -= amount + fees
        elif txn.transaction_type == TransactionType.investment_sell:
            cash[cash_key]["book_value"] += amount - fees
        else:
            cash[cash_key]["book_value"] -= fees

        position_key = (account_row.id, platform.id if platform else None, instrument.id if instrument else None)
        position = positions.setdefault(
            position_key,
            {
                "account_name": account_row.name,
                "platform_name": platform.canonical_name if platform else None,
                "symbol": instrument.symbol if instrument else "Unspecified",
                "broad_category": None,
                "precise_category": None,
                "quantity": 0.0,
                "book_value": 0.0,
                "has_quantity": False,
            },
        )
        if category:
            position["broad_category"] = category.broad
            position["precise_category"] = category.precise

        if txn.transaction_type in {TransactionType.investment_buy, TransactionType.dividend_reinvestment}:
            position["book_value"] += amount + fees
            if txn.quantity is not None:
                position["quantity"] += txn.quantity
                position["has_quantity"] = True
            continue

        if txn.quantity is not None and position["quantity"]:
            position["book_value"] -= position["book_value"] * (txn.quantity / position["quantity"])
            position["quantity"] -= txn.quantity
            position["has_quantity"] = True
        else:
            position["book_value"] -= amount

    holdings = []
    for (account_id, platform_id), row in cash.items():
        book_value = round(row["book_value"], 2)
        if book_value:
            holdings.append(
                {
                    "id": f"cash:{account_id}:{platform_id or 0}",
                    "as_of_date": as_of_date,
                    "account_name": row["account_name"],
                    "platform_name": row["platform_name"],
                    "symbol": "Cash",
                    "broad_category": "Cash",
                    "precise_category": "Cash",
                    "record_type": "cash",
                    "quantity": None,
                    "book_value": book_value,
                }
            )
    for (account_id, platform_id, instrument_id), row in positions.items():
        if row["quantity"] or row["book_value"]:
            holdings.append(
                {
                    "id": f"holding:{account_id}:{platform_id or 0}:{instrument_id or 0}",
                    "as_of_date": as_of_date,
                    "account_name": row["account_name"],
                    "platform_name": row["platform_name"],
                    "symbol": row["symbol"],
                    "broad_category": row["broad_category"],
                    "precise_category": row["precise_category"],
                    "record_type": "holding",
                    "quantity": row["quantity"] if row["has_quantity"] else None,
                    "book_value": row["book_value"],
                }
            )
    return sorted(holdings, key=lambda row: (row["account_name"], row["record_type"], row["symbol"]))


def get_contribution_room(db: Session, tax_year: int):
    result = []
    accounts = db.scalars(select(Account)).all()
    for acc in accounts:
        limit = compute_contribution_limit_for_account(db, acc, str(tax_year))
        if not limit:
            continue
        used = get_contribution_used(db, acc.id, tax_year)
        result.append(
            {
                "account": acc.name,
                "tax_year": str(tax_year),
                "total_room": limit["total_room"],
                "used": used,
                "remaining": limit["total_room"] - used,
            }
        )
    return result


def get_contribution_used(db: Session, account_id: int, tax_year: int):
    account = db.get(Account, account_id)
    tax_year_start, next_tax_year_start = _contribution_tax_year_bounds(account.name if account else None, tax_year)
    return float(
        db.scalar(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.account_id == account_id,
                Transaction.transaction_type == TransactionType.contribution,
                Transaction.transaction_date >= tax_year_start,
                Transaction.transaction_date < next_tax_year_start,
            )
        )
        or 0
    )


def get_new_room(db: Session, account_id: int, tax_year: str):
    limit = db.scalar(
        select(ContributionLimit).where(
            ContributionLimit.account_id == account_id,
            ContributionLimit.tax_year == tax_year,
        )
    )
    return float(limit.new_room) if limit else 0


def compute_contribution_limits_for_account(db: Session, account: Account):
    rows = []
    previous_total = 0.0
    for tax_year in TRACKED_YEARS:
        previous_year = int(tax_year) - 1
        previous_used = get_contribution_used(db, account.id, previous_year) if rows else 0.0
        unused_room = previous_total - previous_used if rows else 0.0
        new_room = get_new_room(db, account.id, tax_year)
        total_room = unused_room + new_room
        rows.append(
            {
                "account": account.name,
                "tax_year": tax_year,
                "unused_room": unused_room,
                "new_room": new_room,
                "total_room": total_room,
            }
        )
        previous_total = total_room
    return rows


def compute_contribution_limit_for_account(db: Session, account: Account, tax_year: str):
    rows = compute_contribution_limits_for_account(db, account)
    return next((row for row in rows if row["tax_year"] == tax_year), None)


def list_contribution_limits(db: Session):
    accounts = db.scalars(select(Account).order_by(Account.name)).all()
    rows = []
    for acc in accounts:
        rows.extend(compute_contribution_limits_for_account(db, acc))
    return rows


def upsert_contribution_limit(db: Session, account_name: str, tax_year: str, new_room: float):
    account = get_or_create_account(db, account_name)
    limit = db.scalar(
        select(ContributionLimit).where(
            ContributionLimit.account_id == account.id,
            ContributionLimit.tax_year == tax_year,
        )
    )
    if not limit:
        limit = ContributionLimit(account_id=account.id, tax_year=tax_year)
        db.add(limit)

    limit.new_room = new_room
    db.commit()
    return compute_contribution_limit_for_account(db, account, tax_year)


def distribution(db: Session, group_by: str, year: int | None = None, category_level: str = "precise"):
    totals = {}
    for holding in list_holdings(db, year=year):
        if group_by == "sector":
            label = holding["broad_category"] if category_level == "broad" else holding["precise_category"]
        elif group_by == "account":
            label = holding["account_name"]
        else:
            label = holding["platform_name"]
        label = label or "Uncategorized"
        totals[label] = totals.get(label, 0.0) + holding["book_value"]
    return [{"label": label, "value": value} for label, value in sorted(totals.items())]


def timeseries(db: Session, year: int | None = None):
    q = (
        select(
            func.to_char(Transaction.transaction_date, "YYYY-MM").label("month"),
            func.coalesce(func.sum(case((Transaction.transaction_type == TransactionType.contribution, Transaction.amount), else_=0)), 0).label("contributions"),
            func.coalesce(
                func.sum(
                    case(
                        (Transaction.transaction_type.in_([TransactionType.investment_buy, TransactionType.investment_sell]), Transaction.amount),
                        else_=0,
                    )
                ),
                0,
            ).label("investments"),
        )
        .group_by("month")
        .order_by("month")
    )
    if year:
        q = q.where(func.extract("year", Transaction.transaction_date) == year)
    rows = db.execute(q).all()
    return [{"month": r.month, "contributions": float(r.contributions or 0), "investments": float(r.investments or 0)} for r in rows]


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
    db.commit()
