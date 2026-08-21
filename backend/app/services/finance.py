import json
from datetime import date, datetime, timedelta

from sqlalchemy import and_, case, func, or_, select, text
from sqlalchemy.orm import Session

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


def _rows_for_export(db: Session, model):
    return db.scalars(select(model).order_by(model.id)).all()


def _parse_date(value: str | None):
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(value)


def _parse_datetime(value: str | None):
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _reset_sequence(db: Session, model) -> None:
    if db.bind is None or db.bind.dialect.name != "postgresql":
        return
    max_id = db.scalar(select(func.max(model.id))) or 0
    db.execute(
        text(
            f"SELECT setval(pg_get_serial_sequence('{model.__tablename__}', 'id'), :value, :is_called)"
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


def _funding_contributions(payload: AccountTransactionCreate):
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
            for funding in _funding_contributions(payload)
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
    fundings = _funding_contributions(payload)
    if payload.transaction_type != TransactionType.investment_buy:
        if fundings:
            raise ValueError("funding contributions are only supported for investment buys")
        return

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
        if not contribution or contribution.transaction_type != TransactionType.contribution:
            raise ValueError("selected contribution was not found")

        contribution_account = db.get(Account, contribution.account_id) if contribution.account_id else None
        if not contribution_account or contribution_account.name.lower() != payload.account_name.lower():
            raise ValueError("selected contribution belongs to a different account")
        remaining = float(contribution.amount) - _contribution_usage(db, contribution.id, transaction)
        if round(amount, 2) > round(remaining, 2):
            raise ValueError(f"selected contribution has only ${remaining:.2f} remaining")


def list_available_contributions(
    db: Session,
    account: str,
    include_contribution_id: int | None = None,
    include_contribution_ids: set[int] | None = None,
):
    contributions = db.execute(
        select(Transaction, Platform.canonical_name)
        .join(Account, Transaction.account_id == Account.id)
        .outerjoin(Platform, Transaction.platform_id == Platform.id)
        .where(Transaction.transaction_type == TransactionType.contribution, func.lower(Account.name) == account.lower())
        .order_by(Transaction.transaction_date, Transaction.id)
    ).all()
    usage = dict(
        db.execute(
            select(
                TransactionFunding.contribution_id,
                func.coalesce(func.sum(TransactionFunding.amount), 0),
            )
            .group_by(TransactionFunding.contribution_id)
        ).all()
    )
    legacy_usage = db.execute(
        select(
            Transaction.contribution_id,
            func.coalesce(func.sum(Transaction.amount + func.coalesce(Transaction.fees, 0)), 0),
        )
        .outerjoin(TransactionFunding, TransactionFunding.transaction_id == Transaction.id)
        .where(
            Transaction.contribution_id.is_not(None),
            Transaction.transaction_type == TransactionType.investment_buy,
            TransactionFunding.id.is_(None),
        )
        .group_by(Transaction.contribution_id)
    ).all()
    for contribution_id, amount in legacy_usage:
        usage[contribution_id] = float(usage.get(contribution_id, 0)) + float(amount)
    include_ids = set(include_contribution_ids or [])
    if include_contribution_id:
        include_ids.add(include_contribution_id)
    return [
        {
            "id": contribution.id,
            "transaction_date": contribution.transaction_date,
            "platform_name": platform_name,
            "amount": float(contribution.amount),
            "remaining_amount": round(float(contribution.amount) - float(usage.get(contribution.id, 0)), 2),
        }
        for contribution, platform_name in contributions
        if round(float(contribution.amount) - float(usage.get(contribution.id, 0)), 2) > 0
        or contribution.id in include_ids
    ]


def list_transaction_fundings(db: Session, transaction: Transaction):
    fundings = db.scalars(
        select(TransactionFunding)
        .where(TransactionFunding.transaction_id == transaction.id)
        .order_by(TransactionFunding.id)
    ).all()
    if fundings:
        return [{"contribution_id": funding.contribution_id, "amount": float(funding.amount)} for funding in fundings]
    if transaction.contribution_id:
        return [{"contribution_id": transaction.contribution_id, "amount": float(transaction.amount) + float(transaction.fees or 0)}]
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
    q = (
        select(
            Transaction,
            Account,
            Platform,
            Instrument,
            Category,
        )
        .outerjoin(Account, Transaction.account_id == Account.id)
        .outerjoin(Platform, Transaction.platform_id == Platform.id)
        .outerjoin(Instrument, Transaction.instrument_id == Instrument.id)
        .outerjoin(Category, Transaction.category_id == Category.id)
        .where(Transaction.transaction_date <= as_of_date)
        .order_by(Transaction.transaction_date, Transaction.id)
    )
    if account:
        q = q.where(func.lower(Account.name) == account.lower())

    cash = {}
    positions = {}
    for txn, account_row, platform, instrument, category in db.execute(q):
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
        if row["book_value"]:
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
                    "book_value": row["book_value"],
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
    return {
        "accounts": [
            {"id": row.id, "name": row.name}
            for row in _rows_for_export(db, Account)
        ],
        "platforms": [
            {"id": row.id, "canonical_name": row.canonical_name}
            for row in _rows_for_export(db, Platform)
        ],
        "platform_aliases": [
            {"id": row.id, "alias": row.alias, "platform_id": row.platform_id}
            for row in _rows_for_export(db, PlatformAlias)
        ],
        "categories": [
            {"id": row.id, "broad": row.broad, "precise": row.precise}
            for row in _rows_for_export(db, Category)
        ],
        "instruments": [
            {"id": row.id, "symbol": row.symbol, "name": row.name, "category_id": row.category_id}
            for row in _rows_for_export(db, Instrument)
        ],
        "contribution_limits": [
            {
                "id": row.id,
                "account_id": row.account_id,
                "tax_year": row.tax_year,
                "new_room": row.new_room,
            }
            for row in _rows_for_export(db, ContributionLimit)
        ],
        "transactions": [
            {
                "id": row.id,
                "transaction_type": row.transaction_type,
                "transaction_date": row.transaction_date,
                "account_id": row.account_id,
                "platform_id": row.platform_id,
                "instrument_id": row.instrument_id,
                "category_id": row.category_id,
                "amount": row.amount,
                "quantity": row.quantity,
                "fees": row.fees,
                "notes": row.notes,
                "reversal_of_id": row.reversal_of_id,
                "contribution_id": row.contribution_id,
                "created_at": row.created_at,
            }
            for row in _rows_for_export(db, Transaction)
        ],
        "transaction_fundings": [
            {
                "id": row.id,
                "transaction_id": row.transaction_id,
                "contribution_id": row.contribution_id,
                "amount": row.amount,
            }
            for row in _rows_for_export(db, TransactionFunding)
        ],
        "holding_snapshots": [
            {
                "id": row.id,
                "snapshot_date": row.snapshot_date,
                "snapshot_year": row.snapshot_year,
                "snapshot_type": row.snapshot_type,
                "holding_date": row.holding_date,
                "record_type": row.record_type,
                "account_id": row.account_id,
                "platform_id": row.platform_id,
                "instrument_id": row.instrument_id,
                "category_id": row.category_id,
                "market_value": row.market_value,
            }
            for row in _rows_for_export(db, HoldingSnapshot)
        ],
        "imports": [
            {
                "id": row.id,
                "import_type": row.import_type,
                "source_filename": row.source_filename,
                "status": row.status,
                "created_at": row.created_at,
            }
            for row in _rows_for_export(db, Import)
        ],
        "import_rows": [
            {
                "id": row.id,
                "import_id": row.import_id,
                "row_number": row.row_number,
                "payload_json": row.payload_json,
                "error": row.error,
            }
            for row in _rows_for_export(db, ImportRow)
        ],
    }


def restore_all_data(db: Session, payload: dict):
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("Backup payload is missing a data object")

    delete_order = [
        ImportRow,
        Import,
        HoldingSnapshot,
        TransactionFunding,
        Transaction,
        ContributionLimit,
        Instrument,
        Category,
        PlatformAlias,
        Platform,
        Account,
    ]
    for model in delete_order:
        db.query(model).delete()
    db.flush()

    for row in data.get("accounts", []):
        db.add(Account(id=row["id"], name=row["name"]))

    for row in data.get("platforms", []):
        db.add(Platform(id=row["id"], canonical_name=row["canonical_name"]))

    for row in data.get("platform_aliases", []):
        db.add(PlatformAlias(id=row["id"], alias=row["alias"], platform_id=row["platform_id"]))

    for row in data.get("categories", []):
        db.add(Category(id=row["id"], broad=row["broad"], precise=row["precise"]))

    for row in data.get("instruments", []):
        db.add(
            Instrument(
                id=row["id"],
                symbol=row["symbol"],
                name=row.get("name"),
                category_id=row.get("category_id"),
            )
        )

    for row in data.get("contribution_limits", []):
        db.add(
            ContributionLimit(
                id=row["id"],
                account_id=row["account_id"],
                tax_year=row["tax_year"],
                new_room=row["new_room"],
            )
        )

    transaction_rows = data.get("transactions", [])
    for row in transaction_rows:
        db.add(
            Transaction(
                id=row["id"],
                transaction_type=TransactionType(row["transaction_type"]),
                transaction_date=_parse_date(row["transaction_date"]),
                account_id=row.get("account_id"),
                platform_id=row.get("platform_id"),
                instrument_id=row.get("instrument_id"),
                category_id=row.get("category_id"),
                amount=row["amount"],
                quantity=row.get("quantity"),
                fees=row.get("fees"),
                notes=row.get("notes"),
                reversal_of_id=None,
                contribution_id=None,
                created_at=_parse_datetime(row.get("created_at")),
            )
        )
    db.flush()
    for row in transaction_rows:
        txn = db.get(Transaction, row["id"])
        if txn:
            if row.get("reversal_of_id") is not None:
                txn.reversal_of_id = row["reversal_of_id"]
            if row.get("contribution_id") is not None:
                txn.contribution_id = row.get("contribution_id")

    for row in data.get("transaction_fundings", []):
        db.add(
            TransactionFunding(
                id=row["id"],
                transaction_id=row["transaction_id"],
                contribution_id=row["contribution_id"],
                amount=row["amount"],
            )
        )

    for row in data.get("holding_snapshots", []):
        db.add(
            HoldingSnapshot(
                id=row["id"],
                snapshot_date=_parse_date(row["snapshot_date"]),
                snapshot_year=row.get("snapshot_year"),
                snapshot_type=row.get("snapshot_type") or "current",
                holding_date=_parse_date(row.get("holding_date")),
                record_type=row.get("record_type") or "holding",
                account_id=row.get("account_id"),
                platform_id=row.get("platform_id"),
                instrument_id=row.get("instrument_id"),
                category_id=row.get("category_id"),
                market_value=row["market_value"],
            )
        )

    for row in data.get("imports", []):
        db.add(
            Import(
                id=row["id"],
                import_type=ImportType(row["import_type"]),
                source_filename=row["source_filename"],
                status=ImportStatus(row["status"]),
                created_at=_parse_datetime(row.get("created_at")),
            )
        )

    for row in data.get("import_rows", []):
        db.add(
            ImportRow(
                id=row["id"],
                import_id=row["import_id"],
                row_number=row["row_number"],
                payload_json=row["payload_json"],
                error=row.get("error"),
            )
        )

    db.commit()

    for model in [Account, Platform, PlatformAlias, Category, Instrument, ContributionLimit, Transaction, TransactionFunding, HoldingSnapshot, Import, ImportRow]:
        _reset_sequence(db, model)
    db.commit()
