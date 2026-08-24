from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.models import Account, Category, HoldingSnapshot, Instrument, MarketPrice, Platform, Transaction, TransactionType
from app.services.finance import distribution, grouped_holdings, portfolio_pl, list_holdings


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


def test_cross_currency_buy_uses_source_cash_and_holding_currency():
    engine = create_engine("sqlite:///:memory:", future=True)
    Session = sessionmaker(bind=engine, future=True)
    Base.metadata.create_all(engine)

    with Session() as db:
        account = Account(name="TFSA")
        platform = Platform(canonical_name="Wealthsimple")
        instrument = Instrument(symbol="GOOG")
        db.add_all([account, platform, instrument])
        db.flush()
        db.add(
            Transaction(
                transaction_type=TransactionType.investment_buy,
                transaction_date=date(2026, 1, 1),
                account_id=account.id,
                platform_id=platform.id,
                instrument_id=instrument.id,
                amount=0.1573,
                currency="USD",
                source_amount=0.22,
                source_currency="CAD",
                quantity=0.0009,
                fees=0,
            )
        )
        db.commit()

        holdings = list_holdings(db, account="TFSA", year=2026)
        cash = next(row for row in holdings if row["record_type"] == "cash")
        position = next(row for row in holdings if row["symbol"] == "GOOG")

        assert cash["currency"] == "CAD"
        assert cash["book_value"] == -0.22
        assert position["currency"] == "USD"
        assert position["book_value"] == 0.1573


def test_cross_currency_dividend_reinvestment_consumes_source_cash():
    engine = create_engine("sqlite:///:memory:", future=True)
    Session = sessionmaker(bind=engine, future=True)
    Base.metadata.create_all(engine)

    with Session() as db:
        account = Account(name="TFSA")
        platform = Platform(canonical_name="Wealthsimple")
        instrument = Instrument(symbol="GOOG")
        db.add_all([account, platform, instrument])
        db.flush()
        db.add_all(
            [
                Transaction(
                    transaction_type=TransactionType.dividend_interest,
                    transaction_date=date(2026, 1, 1),
                    account_id=account.id,
                    platform_id=platform.id,
                    instrument_id=instrument.id,
                    amount=0.22,
                    currency="CAD",
                    fees=0,
                ),
                Transaction(
                    transaction_type=TransactionType.dividend_reinvestment,
                    transaction_date=date(2026, 1, 1),
                    account_id=account.id,
                    platform_id=platform.id,
                    instrument_id=instrument.id,
                    amount=0.1573,
                    currency="USD",
                    source_amount=0.22,
                    source_currency="CAD",
                    quantity=0.0009,
                    fees=0,
                ),
            ]
        )
        db.commit()

        holdings = list_holdings(db, account="TFSA", year=2026)
        position = next(row for row in holdings if row["symbol"] == "GOOG")

        assert not [row for row in holdings if row["record_type"] == "cash"]
        assert position["currency"] == "USD"
        assert position["book_value"] == 0.1573


def test_portfolio_pl_uses_manual_snapshot_for_holdings_without_quantity():
    engine = create_engine("sqlite:///:memory:", future=True)
    Session = sessionmaker(bind=engine, future=True)
    Base.metadata.create_all(engine)

    with Session() as db:
        account = Account(name="FHSA")
        platform = Platform(canonical_name="EQ Bank")
        category = Category(broad="Bond", precise="GIC")
        instrument = Instrument(symbol="GIC", currency="CAD")
        db.add_all([account, platform, category, instrument])
        db.flush()
        db.add_all(
            [
                Transaction(
                    transaction_type=TransactionType.investment_buy,
                    transaction_date=date(2026, 1, 1),
                    account_id=account.id,
                    platform_id=platform.id,
                    instrument_id=instrument.id,
                    category_id=category.id,
                    amount=3000,
                    currency="CAD",
                    fees=0,
                ),
                HoldingSnapshot(
                    snapshot_date=date(2026, 8, 24),
                    account_id=account.id,
                    platform_id=platform.id,
                    instrument_id=instrument.id,
                    category_id=category.id,
                    market_value=3043.89,
                ),
            ]
        )
        db.commit()

        row = portfolio_pl(db, status="ok")[0]

        assert row["symbol"] == "GIC"
        assert row["quantity"] is None
        assert row["market_value"] == 3043.89
        assert row["unrealized_pl"] == 43.89
        assert row["manual_valuation_date"] == date(2026, 8, 24)


def test_holdings_and_pl_group_symbol_with_platform_children():
    engine = create_engine("sqlite:///:memory:", future=True)
    Session = sessionmaker(bind=engine, future=True)
    Base.metadata.create_all(engine)

    with Session() as db:
        account = Account(name="TFSA")
        questrade = Platform(canonical_name="Questrade")
        wealthsimple = Platform(canonical_name="Wealthsimple")
        instrument = Instrument(symbol="VEQT", provider_symbol="VEQT.TO")
        db.add_all([account, questrade, wealthsimple, instrument])
        db.flush()
        db.add_all(
            [
                Transaction(
                    transaction_type=TransactionType.investment_buy,
                    transaction_date=date(2026, 1, 1),
                    account_id=account.id,
                    platform_id=questrade.id,
                    instrument_id=instrument.id,
                    amount=100,
                    quantity=2,
                ),
                Transaction(
                    transaction_type=TransactionType.investment_buy,
                    transaction_date=date(2026, 1, 2),
                    account_id=account.id,
                    platform_id=wealthsimple.id,
                    instrument_id=instrument.id,
                    amount=180,
                    quantity=3,
                ),
                MarketPrice(
                    instrument_id=instrument.id,
                    price=70,
                    currency="CAD",
                    priced_at=date(2026, 1, 3),
                ),
            ]
        )
        db.commit()

        holding = next(row for row in grouped_holdings(db, account="TFSA", year=2026) if row["symbol"] == "VEQT")
        pl = next(row for row in portfolio_pl(db, account="TFSA", year=2026) if row["symbol"] == "VEQT")

        assert holding["quantity"] == 5
        assert holding["book_value"] == 280
        assert holding["average_price"] == 56
        assert [child["platform_name"] for child in holding["children"]] == ["Questrade", "Wealthsimple"]
        assert [child["quantity"] for child in holding["children"]] == [2, 3]
        assert pl["market_value"] == 350
        assert pl["unrealized_pl"] == 70
        assert pl["unrealized_pl_pct"] == 25
