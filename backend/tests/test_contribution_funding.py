from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.models import Account, Platform, TransactionFunding, TransactionType
from app.schemas.schemas import AccountTransactionCreate, ContributionCreate
from app.services.finance import create_account_transaction, create_contribution, list_available_contributions, list_holdings


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
                transaction_date=date(2026, 1, 1), account_name="TFSA", platform_name="Wealthsimple", amount=3105.58
            ),
        )
        for amount in (3000,):
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
                "id": 1,
                "platform_name": "Wealthsimple",
                "source_label": "Cash",
                "remaining_amount": 105.58,
            }
        ]
        create_account_transaction(
            db,
            AccountTransactionCreate(
                transaction_type=TransactionType.investment_buy,
                transaction_date=date(2026, 1, 2),
                account_name="TFSA",
                platform_name="Wealthsimple",
                amount=105.58,
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


def test_investment_buy_can_use_multiple_or_no_funding_contributions():
    engine = create_engine("sqlite:///:memory:", future=True)
    Session = sessionmaker(bind=engine, future=True)
    Base.metadata.create_all(engine)

    with Session() as db:
        db.add_all([Account(name="TFSA"), Platform(canonical_name="Wealthsimple")])
        db.commit()
        first = create_contribution(
            db,
            ContributionCreate(
                transaction_date=date(2026, 1, 1), account_name="TFSA", platform_name="Wealthsimple", amount=100
            ),
        )
        second = create_contribution(
            db,
            ContributionCreate(
                transaction_date=date(2026, 1, 2), account_name="TFSA", platform_name="Wealthsimple", amount=100
            ),
        )

        create_account_transaction(
            db,
            AccountTransactionCreate(
                transaction_type=TransactionType.investment_buy,
                transaction_date=date(2026, 1, 3),
                account_name="TFSA",
                platform_name="Wealthsimple",
                amount=150,
                funding_contributions=[
                    {"contribution_id": first.id, "amount": 100},
                    {"contribution_id": second.id, "amount": 50},
                ],
            ),
        )
        create_account_transaction(
            db,
            AccountTransactionCreate(
                transaction_type=TransactionType.investment_buy,
                transaction_date=date(2026, 1, 4),
                account_name="TFSA",
                platform_name="Wealthsimple",
                amount=25,
            ),
        )

        assert list_available_contributions(db, "TFSA") == [
            {
                "id": 1,
                "platform_name": "Wealthsimple",
                "source_label": "Cash",
                "remaining_amount": 50.0,
            }
        ]

        with pytest.raises(ValueError, match="must total the transaction amount plus fees"):
            create_account_transaction(
                db,
                AccountTransactionCreate(
                    transaction_type=TransactionType.investment_buy,
                    transaction_date=date(2026, 1, 5),
                    account_name="TFSA",
                    platform_name="Wealthsimple",
                    amount=10,
                    funding_contributions=[{"contribution_id": second.id, "amount": 5}],
                ),
            )


def test_cross_currency_buy_funding_uses_source_amount():
    engine = create_engine("sqlite:///:memory:", future=True)
    Session = sessionmaker(bind=engine, future=True)
    Base.metadata.create_all(engine)

    with Session() as db:
        db.add_all([Account(name="TFSA"), Platform(canonical_name="Wealthsimple")])
        db.commit()
        contribution = create_contribution(
            db,
            ContributionCreate(
                transaction_date=date(2026, 1, 1), account_name="TFSA", platform_name="Wealthsimple", amount=121.37
            ),
        )
        create_account_transaction(
            db,
            AccountTransactionCreate(
                transaction_type=TransactionType.investment_buy,
                transaction_date=date(2026, 1, 2),
                account_name="TFSA",
                platform_name="Wealthsimple",
                symbol="GOOG",
                amount=88.2242,
                currency="USD",
                source_amount=121.37,
                source_currency="CAD",
                quantity=1,
                funding_contributions=[{"contribution_id": contribution.id, "amount": 121.37}],
            ),
        )

        assert list_available_contributions(db, "TFSA") == []


def test_transfer_replaces_source_lots_with_destination_cash():
    engine = create_engine("sqlite:///:memory:", future=True)
    Session = sessionmaker(bind=engine, future=True)
    Base.metadata.create_all(engine)

    with Session() as db:
        db.add_all([Account(name="FHSA"), Platform(canonical_name="CIBC"), Platform(canonical_name="Questrade")])
        db.commit()
        first = create_contribution(db, ContributionCreate(transaction_date=date(2023, 12, 31), account_name="FHSA", platform_name="CIBC", amount=8000))
        second = create_contribution(db, ContributionCreate(transaction_date=date(2024, 12, 31), account_name="FHSA", platform_name="CIBC", amount=8000))
        interest = create_account_transaction(
            db,
            AccountTransactionCreate(transaction_type=TransactionType.dividend_interest, transaction_date=date(2026, 1, 23), account_name="FHSA", platform_name="CIBC", amount=741.09),
        )
        create_account_transaction(
            db,
            AccountTransactionCreate(
                transaction_type=TransactionType.transfer,
                transaction_date=date(2026, 1, 23),
                account_name="FHSA",
                platform_name="Questrade",
                source_platform_name="CIBC",
                amount=16741.09,
                funding_contributions=[
                    {"contribution_id": first.id, "amount": 8000},
                    {"contribution_id": second.id, "amount": 8000},
                    {"contribution_id": interest.id, "amount": 741.09},
                ],
            ),
        )

        assert list_available_contributions(db, "FHSA") == [
            {
                "id": 2,
                "platform_name": "Questrade",
                "source_label": "Cash",
                "remaining_amount": 16741.09,
            }
        ]
        assert {row["platform_name"]: row["book_value"] for row in list_holdings(db, account="FHSA") if row["record_type"] == "cash"} == {
            "Questrade": 16741.09
        }


def test_cash_pool_combines_sources_and_allocates_oldest_first():
    engine = create_engine("sqlite:///:memory:", future=True)
    Session = sessionmaker(bind=engine, future=True)
    Base.metadata.create_all(engine)

    with Session() as db:
        db.add_all([Account(name="TFSA"), Platform(canonical_name="Wealthsimple")])
        db.commit()
        contribution = create_contribution(
            db,
            ContributionCreate(transaction_date=date(2026, 1, 1), account_name="TFSA", platform_name="Wealthsimple", amount=100),
        )
        interest = create_account_transaction(
            db,
            AccountTransactionCreate(transaction_type=TransactionType.dividend_interest, transaction_date=date(2026, 1, 2), account_name="TFSA", platform_name="Wealthsimple", amount=20),
        )
        dividend = create_account_transaction(
            db,
            AccountTransactionCreate(transaction_type=TransactionType.dividend_interest, transaction_date=date(2026, 1, 3), account_name="TFSA", platform_name="Wealthsimple", amount=30),
        )

        assert list_available_contributions(db, "TFSA") == [
            {"id": 1, "platform_name": "Wealthsimple", "source_label": "Cash", "remaining_amount": 150.0}
        ]
        buy = create_account_transaction(
            db,
            AccountTransactionCreate(
                transaction_type=TransactionType.investment_buy,
                transaction_date=date(2026, 1, 4),
                account_name="TFSA",
                platform_name="Wealthsimple",
                amount=115,
                funding_cash_sources=[{"platform_name": "Wealthsimple", "amount": 115}],
            ),
        )

        fundings = db.query(TransactionFunding).filter(TransactionFunding.transaction_id == buy.id).order_by(TransactionFunding.id).all()
        assert [(funding.contribution_id, float(funding.amount)) for funding in fundings] == [
            (contribution.id, 100.0),
            (interest.id, 15.0),
        ]
        assert list_available_contributions(db, "TFSA")[0]["remaining_amount"] == 35.0
