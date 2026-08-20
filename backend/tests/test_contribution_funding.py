from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.models import Account, Platform, TransactionType
from app.schemas.schemas import AccountTransactionCreate, ContributionCreate
from app.services.finance import create_account_transaction, create_contribution, list_available_contributions


def test_contribution_can_fund_partial_and_full_investment_buys():
    engine = create_engine("sqlite:///:memory:", future=True)
    Session = sessionmaker(bind=engine, future=True)
    Base.metadata.create_all(engine)

    with Session() as db:
        db.add_all([Account(name="TFSA"), Platform(canonical_name="Wealthsimple")])
        db.commit()
        contribution = create_contribution(
            db,
            ContributionCreate(
                transaction_date=date(2026, 1, 1), account_name="TFSA", platform_name="Wealthsimple", amount=100
            ),
        )
        for amount in (60,):
            create_account_transaction(
                db,
                AccountTransactionCreate(
                    transaction_type=TransactionType.investment_buy,
                    transaction_date=date(2026, 1, 2),
                    account_name="TFSA",
                    platform_name="Wealthsimple",
                    amount=amount,
                    contribution_id=contribution.id,
                ),
            )

        assert list_available_contributions(db, "TFSA") == [
            {
                "id": contribution.id,
                "transaction_date": date(2026, 1, 1),
                "platform_name": "Wealthsimple",
                "amount": 100.0,
                "remaining_amount": 40.0,
            }
        ]
        create_account_transaction(
            db,
            AccountTransactionCreate(
                transaction_type=TransactionType.investment_buy,
                transaction_date=date(2026, 1, 2),
                account_name="TFSA",
                platform_name="Wealthsimple",
                amount=40,
                contribution_id=contribution.id,
            ),
        )

        assert list_available_contributions(db, "TFSA") == []
        with pytest.raises(ValueError, match=r"only \$0.00 remaining"):
            create_account_transaction(
                db,
                AccountTransactionCreate(
                    transaction_type=TransactionType.investment_buy,
                    transaction_date=date(2026, 1, 3),
                    account_name="TFSA",
                    platform_name="Wealthsimple",
                    amount=1,
                    contribution_id=contribution.id,
                ),
            )
