import json
from datetime import date

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.models import Account, AuditLog, Platform, TransactionType
from app.schemas.schemas import AccountTransactionCreate, ContributionCreate
from app.services.finance import create_account_transaction, create_contribution, update_account_transaction


def test_account_transaction_update_writes_audit_log_with_before_and_after():
    engine = create_engine("sqlite:///:memory:", future=True)
    Session = sessionmaker(bind=engine, future=True)
    Base.metadata.create_all(engine)

    with Session() as db:
        db.add_all([Account(name="TFSA"), Platform(canonical_name="Wealthsimple")])
        db.commit()
        contribution = create_contribution(
            db,
            ContributionCreate(
                transaction_date=date(2026, 1, 1),
                account_name="TFSA",
                platform_name="Wealthsimple",
                amount=100,
            ),
        )
        txn = create_account_transaction(
            db,
            AccountTransactionCreate(
                transaction_type=TransactionType.investment_buy,
                transaction_date=date(2026, 1, 2),
                account_name="TFSA",
                platform_name="Wealthsimple",
                amount=25,
                contribution_id=contribution.id,
            ),
        )

        update_account_transaction(
            db,
            txn.id,
            AccountTransactionCreate(
                transaction_type=TransactionType.investment_buy,
                transaction_date=date(2026, 1, 3),
                account_name="TFSA",
                platform_name="Wealthsimple",
                amount=40,
                contribution_id=contribution.id,
            ),
        )

        audit = db.scalars(
            select(AuditLog)
            .where(AuditLog.operation == "update", AuditLog.table_name == "transactions", AuditLog.row_id == str(txn.id))
        ).one()
        before = json.loads(audit.before_json)
        after = json.loads(audit.after_json)

        assert before["amount"] == 25.0
        assert after["amount"] == 40
        assert before["funding_contributions"][0]["amount"] == 25.0
        assert after["funding_contributions"][0]["amount"] == 40.0
