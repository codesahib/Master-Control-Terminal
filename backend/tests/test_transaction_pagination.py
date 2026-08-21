from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.models import Account, Platform, Transaction, TransactionType
from app.services.finance import list_account_transactions, list_transactions


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
