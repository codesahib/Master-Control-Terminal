from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.models import Account, Platform, Transaction, TransactionFunding, TransactionType
from app.services.finance import list_account_transactions, list_transactions
from app.services.transaction_reads import account_transaction_reads, transaction_reads
from app.schemas.schemas import AccountTransactionRead


def test_transaction_lists_page_filter_and_sort_on_the_server():
    engine = create_engine("sqlite:///:memory:", future=True)
    Session = sessionmaker(bind=engine, future=True)
    Base.metadata.create_all(engine)

    with Session() as db:
        account = Account(name="TFSA")
        questrade = Platform(canonical_name="Questrade")
        cibc = Platform(canonical_name="CIBC")
        db.add_all([account, questrade, cibc])
        db.flush()
        db.add_all(
            [
                Transaction(
                    transaction_type=TransactionType.investment_buy if number % 2 else TransactionType.investment_sell,
                    transaction_date=date(2026, 1, number),
                    account_id=account.id,
                    platform_id=questrade.id if number <= 8 else cibc.id,
                    amount=number,
                )
                for number in range(1, 13)
            ]
        )
        db.commit()

        page_one, total = list_transactions(db, page=1)
        assert total == 12
        assert [row[0].id for row in page_one] == list(range(12, 2, -1))

        page_two, total = list_transactions(db, page=2)
        assert total == 12
        assert [row[0].id for row in page_two] == [2, 1]

        filtered, total = list_transactions(
            db, transaction_type=TransactionType.investment_buy, platform="Questrade", sort_direction="asc"
        )
        assert total == 4
        assert [row[0].id for row in filtered] == [1, 3, 5, 7]

        account_rows, total = list_account_transactions(
            db, account="TFSA", platform="Questrade", transaction_type=TransactionType.investment_buy
        )
        assert total == 4
        assert [row[0].id for row in account_rows] == [7, 5, 3, 1]


def test_transaction_reads_include_source_platform_and_funding_rows():
    engine = create_engine("sqlite:///:memory:", future=True)
    Session = sessionmaker(bind=engine, future=True)
    Base.metadata.create_all(engine)

    with Session() as db:
        account = Account(name="TFSA")
        source_platform = Platform(canonical_name="CIBC")
        platform = Platform(canonical_name="Questrade")
        db.add_all([account, source_platform, platform])
        db.flush()
        contribution = Transaction(
            transaction_type=TransactionType.contribution,
            transaction_date=date(2026, 1, 1),
            account_id=account.id,
            platform_id=source_platform.id,
            amount=100,
        )
        transfer = Transaction(
            transaction_type=TransactionType.transfer,
            transaction_date=date(2026, 1, 2),
            account_id=account.id,
            platform_id=platform.id,
            source_platform_id=source_platform.id,
            amount=100,
        )
        db.add_all([contribution, transfer])
        db.flush()
        db.add(TransactionFunding(transaction_id=transfer.id, contribution_id=contribution.id, amount=100))
        db.commit()

        reads, total = transaction_reads(db)

        assert total == 2
        assert reads[0].source_platform_name == "CIBC"
        assert [funding.model_dump() for funding in reads[0].funding_contributions] == [
            {"contribution_id": contribution.id, "amount": 100.0, "platform_name": "CIBC"}
        ]


def test_account_transaction_reads_return_account_transaction_models():
    engine = create_engine("sqlite:///:memory:", future=True)
    Session = sessionmaker(bind=engine, future=True)
    Base.metadata.create_all(engine)

    with Session() as db:
        account = Account(name="RRSP")
        platform = Platform(canonical_name="Wealthsimple")
        db.add_all([account, platform])
        db.flush()
        db.add(
            Transaction(
                transaction_type=TransactionType.dividend_interest,
                transaction_date=date(2026, 1, 1),
                account_id=account.id,
                platform_id=platform.id,
                amount=1,
            )
        )
        db.commit()

        reads, total = account_transaction_reads(db, account="RRSP")

        assert total == 1
        assert isinstance(reads[0], AccountTransactionRead)
