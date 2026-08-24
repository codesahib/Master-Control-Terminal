from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.models import Account, Platform, Transaction, TransactionType
from app.services.finance import list_account_transactions, list_contributions


def test_list_contributions_and_account_transactions_are_separated():
    engine = create_engine("sqlite:///:memory:", future=True)
    Session = sessionmaker(bind=engine, future=True)
    Base.metadata.create_all(engine)

    with Session() as db:
        account = Account(name="TFSA")
        platform = Platform(canonical_name="Wealthsimple")
        db.add_all([account, platform])
        db.flush()

        db.add_all(
            [
                Transaction(
                    transaction_type=TransactionType.contribution,
                    transaction_date=date(2026, 1, 5),
                    account_id=account.id,
                    platform_id=platform.id,
                    amount=1000,
                    notes="Contribution",
                ),
                Transaction(
                    transaction_type=TransactionType.investment_buy,
                    transaction_date=date(2026, 1, 6),
                    account_id=account.id,
                    platform_id=platform.id,
                    amount=800,
                    notes="Bought ETF",
                ),
            ]
        )
        db.commit()

        contributions = list_contributions(db, account="TFSA", year=2026)
        activity, total = list_account_transactions(db, account="TFSA", year=2026)

        assert len(contributions) == 1
        assert contributions[0][0].transaction_type == TransactionType.contribution
        assert total == 1
        assert len(activity) == 1
        assert activity[0][0].transaction_type == TransactionType.investment_buy


def test_rrsp_account_transactions_use_the_rrsp_contribution_period():
    engine = create_engine("sqlite:///:memory:", future=True)
    Session = sessionmaker(bind=engine, future=True)
    Base.metadata.create_all(engine)

    with Session() as db:
        account = Account(name="RRSP")
        platform = Platform(canonical_name="QuestTrade")
        db.add_all([account, platform])
        db.flush()
        db.add_all(
            [
                Transaction(
                    transaction_type=TransactionType.investment_buy,
                    transaction_date=date(2026, 1, 9),
                    account_id=account.id,
                    platform_id=platform.id,
                    amount=1000,
                ),
                Transaction(
                    transaction_type=TransactionType.investment_buy,
                    transaction_date=date(2026, 3, 3),
                    account_id=account.id,
                    platform_id=platform.id,
                    amount=1000,
                ),
            ]
        )
        db.commit()

        rows, total = list_account_transactions(db, account="RRSP", year=2025)
        assert total == 1
        assert [row[0].transaction_date for row in rows] == [date(2026, 1, 9)]
        rows, total = list_account_transactions(db, account="RRSP", year=2026)
        assert total == 1
        assert [row[0].transaction_date for row in rows] == [date(2026, 3, 3)]
