from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.models import Account, Category, HoldingSnapshot, Instrument, Platform, Transaction, TransactionType
from app.services.finance import distribution, list_holdings


def test_holdings_are_derived_from_transactions_not_snapshots():
    engine = create_engine("sqlite:///:memory:", future=True)
    Session = sessionmaker(bind=engine, future=True)
    Base.metadata.create_all(engine)

    with Session() as db:
        account = Account(name="TFSA")
        platform = Platform(canonical_name="Wealthsimple")
        category = Category(broad="All Equity", precise="All Equity")
        instrument = Instrument(symbol="XEQT")
        db.add_all([account, platform, category, instrument])
        db.flush()
        db.add_all(
            [
                Transaction(
                    transaction_type=TransactionType.contribution,
                    transaction_date=date(2025, 1, 1),
                    account_id=account.id,
                    platform_id=platform.id,
                    amount=1000,
                ),
                Transaction(
                    transaction_type=TransactionType.investment_buy,
                    transaction_date=date(2025, 1, 2),
                    account_id=account.id,
                    platform_id=platform.id,
                    instrument_id=instrument.id,
                    category_id=category.id,
                    amount=600,
                    quantity=6,
                    fees=0,
                ),
                Transaction(
                    transaction_type=TransactionType.investment_sell,
                    transaction_date=date(2025, 1, 3),
                    account_id=account.id,
                    platform_id=platform.id,
                    instrument_id=instrument.id,
                    amount=300,
                    quantity=2,
                    fees=0,
                ),
                Transaction(
                    transaction_type=TransactionType.dividend_interest,
                    transaction_date=date(2025, 1, 4),
                    account_id=account.id,
                    platform_id=platform.id,
                    instrument_id=instrument.id,
                    amount=20,
                    fees=0,
                ),
                Transaction(
                    transaction_type=TransactionType.dividend_reinvestment,
                    transaction_date=date(2025, 1, 5),
                    account_id=account.id,
                    platform_id=platform.id,
                    instrument_id=instrument.id,
                    category_id=category.id,
                    amount=20,
                    quantity=0.2,
                    fees=0,
                ),
                Transaction(
                    transaction_type=TransactionType.quantity_adjustment,
                    transaction_date=date(2025, 1, 6),
                    account_id=account.id,
                    platform_id=platform.id,
                    instrument_id=instrument.id,
                    category_id=category.id,
                    amount=0,
                    quantity=1,
                    fees=0,
                ),
                HoldingSnapshot(
                    snapshot_date=date(2025, 1, 4),
                    account_id=account.id,
                    platform_id=platform.id,
                    instrument_id=instrument.id,
                    category_id=category.id,
                    market_value=9999,
                ),
            ]
        )
        db.commit()

        holdings = {row["symbol"]: row for row in list_holdings(db, account="TFSA", year=2025)}

        assert holdings["Cash"]["book_value"] == 720
        assert holdings["XEQT"]["quantity"] == 5.2
        assert holdings["XEQT"]["book_value"] == 420
        assert {row["label"]: row["value"] for row in distribution(db, "sector", year=2025)} == {
            "All Equity": 420,
            "Cash": 720,
        }


def test_currency_exchange_keeps_cash_and_positions_in_their_native_currency():
    engine = create_engine("sqlite:///:memory:", future=True)
    Session = sessionmaker(bind=engine, future=True)
    Base.metadata.create_all(engine)

    with Session() as db:
        account = Account(name="TFSA")
        platform = Platform(canonical_name="Questrade")
        instrument = Instrument(symbol="TEST")
        db.add_all([account, platform, instrument])
        db.flush()
        db.add_all(
            [
                Transaction(
                    transaction_type=TransactionType.contribution,
                    transaction_date=date(2026, 1, 1),
                    account_id=account.id,
                    platform_id=platform.id,
                    amount=1000,
                    currency="CAD",
                ),
                Transaction(
                    transaction_type=TransactionType.currency_exchange,
                    transaction_date=date(2026, 1, 2),
                    account_id=account.id,
                    platform_id=platform.id,
                    amount=700,
                    currency="USD",
                    source_amount=950,
                    source_currency="CAD",
                    fees=10,
                    fee_currency="CAD",
                ),
                Transaction(
                    transaction_type=TransactionType.investment_buy,
                    transaction_date=date(2026, 1, 3),
                    account_id=account.id,
                    platform_id=platform.id,
                    instrument_id=instrument.id,
                    amount=600,
                    currency="USD",
                    quantity=6,
                    fees=0,
                ),
            ]
        )
        db.commit()

        holdings = list_holdings(db, account="TFSA", year=2026)
        cash = {(row["symbol"], row["currency"]): row for row in holdings if row["record_type"] == "cash"}
        position = next(row for row in holdings if row["symbol"] == "TEST")

        assert cash[("Cash", "CAD")]["book_value"] == 40
        assert cash[("Cash", "USD")]["book_value"] == 100
        assert position["currency"] == "USD"
        assert position["book_value"] == 600
