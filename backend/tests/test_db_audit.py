from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.models import Account, ContributionLimit, HoldingSnapshot, Transaction, TransactionType
from app.services.finance import export_all_data, restore_all_data


def _session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)()


def test_restore_accepts_backups_from_before_the_audit_migration():
    db = _session()
    legacy_payload = {
        "data": {
            "accounts": [{"id": 1, "name": "TFSA"}],
            "transactions": [
                {
                    "id": 1,
                    "transaction_type": "contribution",
                    "transaction_date": "2026-01-01",
                    "account_id": 1,
                    "amount": 500,
                    "currency": "CAD",
                    "quantity": 0.5,
                    "contribution_id": None,
                    "reversal_of_id": None,
                    "created_at": "2026-01-01T00:00:00",
                }
            ],
            "imports": [],
            "import_rows": [],
        }
    }

    restore_all_data(db, legacy_payload)

    exported = export_all_data(db)
    assert "imports" not in exported
    assert exported["transactions"][0]["amount"] == 500
    assert "contribution_id" not in exported["transactions"][0]


def test_check_and_unique_constraints_hold_in_sqlite_too():
    db = _session()
    account = Account(name="TFSA")
    db.add(account)
    db.commit()

    db.add(Transaction(transaction_type=TransactionType.contribution, transaction_date=date(2026, 1, 1), account_id=account.id, amount=-1))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    db.add_all([
        ContributionLimit(account_id=account.id, tax_year="2026", new_room=7000),
        ContributionLimit(account_id=account.id, tax_year="2026", new_room=7000),
    ])
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    db.add(HoldingSnapshot(snapshot_date=date(2026, 1, 1), record_type="holding", market_value=-5))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    # "unused" rows track contribution room and may go negative.
    db.add(HoldingSnapshot(snapshot_date=date(2026, 1, 1), record_type="unused", market_value=-5))
    db.commit()


def test_quantity_keeps_eight_decimals_as_float():
    db = _session()
    account = Account(name="TFSA")
    db.add(account)
    db.commit()
    txn = Transaction(
        transaction_type=TransactionType.quantity_adjustment,
        transaction_date=date(2026, 1, 1),
        account_id=account.id,
        amount=0,
        quantity=1.23456789,
    )
    db.add(txn)
    db.commit()
    db.expire_all()

    assert isinstance(txn.quantity, float)
    assert txn.quantity == 1.23456789
