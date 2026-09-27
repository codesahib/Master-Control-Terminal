from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import Account, Category, Instrument, Platform, Transaction, TransactionFunding
from app.schemas.schemas import AccountTransactionRead, ContributionRead, TransactionRead
from app.services import finance


def transaction_read(db: Session, transaction: Transaction) -> TransactionRead:
    row = db.execute(
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
        .where(Transaction.id == transaction.id)
    ).one()
    return _transaction_reads(db, [row])[0]


def transaction_reads(db: Session, **filters):
    rows, total = finance.list_transactions(db, **filters)
    return _transaction_reads(db, rows), total


def account_transaction_reads(db: Session, **filters):
    rows, total = finance.list_account_transactions(db, **filters)
    return _transaction_reads(db, rows, AccountTransactionRead), total


def contribution_read(db: Session, transaction: Transaction) -> ContributionRead:
    row = db.execute(
        select(Transaction, Account.name.label("account_name"), Platform.canonical_name.label("platform_name"))
        .outerjoin(Account, Transaction.account_id == Account.id)
        .outerjoin(Platform, Transaction.platform_id == Platform.id)
        .where(Transaction.id == transaction.id)
    ).one()
    return _contribution_read(row)


def contribution_reads(db: Session, **filters) -> list[ContributionRead]:
    return [_contribution_read(row) for row in finance.list_contributions(db, **filters)]


def _transaction_reads(db: Session, rows, read_model=TransactionRead) -> list[TransactionRead]:
    transactions = [row[0] for row in rows]
    if not transactions:
        return []

    transaction_ids = [transaction.id for transaction in transactions]
    source_platform_names = dict(
        db.execute(
            select(Platform.id, Platform.canonical_name).where(
                Platform.id.in_({transaction.source_platform_id for transaction in transactions if transaction.source_platform_id})
            )
        ).all()
    )
    funding_rows = db.execute(
        select(TransactionFunding.transaction_id, TransactionFunding.contribution_id, TransactionFunding.amount, Platform.canonical_name)
        .join(Transaction, TransactionFunding.contribution_id == Transaction.id)
        .outerjoin(Platform, Transaction.platform_id == Platform.id)
        .where(TransactionFunding.transaction_id.in_(transaction_ids))
        .order_by(TransactionFunding.transaction_id, TransactionFunding.id)
    ).all()
    fundings = {transaction_id: [] for transaction_id in transaction_ids}
    for transaction_id, contribution_id, amount, platform_name in funding_rows:
        fundings[transaction_id].append(
            {"contribution_id": contribution_id, "amount": float(amount), "platform_name": platform_name}
        )

    legacy_ids = {transaction.contribution_id for transaction in transactions if transaction.contribution_id and not fundings[transaction.id]}
    legacy_platform_names = dict(
        db.execute(
            select(Transaction.id, Platform.canonical_name)
            .outerjoin(Platform, Transaction.platform_id == Platform.id)
            .where(Transaction.id.in_(legacy_ids))
        ).all()
    ) if legacy_ids else {}

    return [_transaction_read(row, source_platform_names, fundings, legacy_platform_names, read_model) for row in rows]


def _transaction_read(row, source_platform_names, fundings, legacy_platform_names, read_model) -> TransactionRead:
    transaction, account_name, platform_name, symbol, broad_category, precise_category = row
    funding_contributions = fundings[transaction.id]
    if not funding_contributions and transaction.contribution_id:
        funding_contributions = [{
            "contribution_id": transaction.contribution_id,
            "amount": float(transaction.amount) + float(transaction.fees or 0),
            "platform_name": legacy_platform_names.get(transaction.contribution_id),
        }]
    return read_model(
        id=transaction.id,
        transaction_type=transaction.transaction_type,
        transaction_date=transaction.transaction_date,
        account_name=account_name,
        platform_name=platform_name,
        source_platform_name=source_platform_names.get(transaction.source_platform_id),
        instrument_id=transaction.instrument_id,
        symbol=symbol,
        broad_category=broad_category,
        precise_category=precise_category,
        amount=float(transaction.amount),
        currency=transaction.currency,
        source_amount=float(transaction.source_amount) if transaction.source_amount is not None else None,
        source_currency=transaction.source_currency,
        quantity=transaction.quantity,
        fees=float(transaction.fees or 0),
        fee_currency=transaction.fee_currency,
        notes=transaction.notes,
        contribution_id=transaction.contribution_id,
        funding_contributions=funding_contributions,
    )


def _contribution_read(row) -> ContributionRead:
    transaction, account_name, platform_name, *_ = row
    return ContributionRead(
        id=transaction.id,
        transaction_date=transaction.transaction_date,
        account_name=account_name,
        platform_name=platform_name,
        amount=float(transaction.amount),
        currency=transaction.currency,
        notes=transaction.notes,
    )
