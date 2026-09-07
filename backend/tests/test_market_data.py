from datetime import date, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.models import Account, Instrument, MarketPrice, Platform, Transaction, TransactionType
from app.services.market_data import refresh_market_prices, search_symbols
from app.services.portfolio import portfolio_pl


def test_symbol_search_persists_yfinance_results(monkeypatch):
    engine = create_engine("sqlite:///:memory:", future=True)
    Session = sessionmaker(bind=engine, future=True)
    Base.metadata.create_all(engine)

    class FakeSearch:
        def __init__(self, _query, max_results=8, news_count=0):
            self.quotes = [
                {
                    "symbol": "XEQT.TO",
                    "shortname": "iShares Core Equity ETF",
                    "exchDisp": "Toronto",
                    "currency": "CAD",
                    "quoteType": "ETF",
                }
            ][:max_results]

    class FakeYFinance:
        Search = FakeSearch

    monkeypatch.setattr("app.services.market_data._yf", lambda: FakeYFinance)

    with Session() as db:
        results = search_symbols(db, "xeqt")

        assert results[0]["symbol"] == "XEQT"
        assert results[0]["provider_symbol"] == "XEQT.TO"
        assert results[0]["currency"] == "CAD"
        assert db.get(Instrument, results[0]["id"]).provider_symbol == "XEQT.TO"


def test_refresh_prices_and_portfolio_pl_use_cached_prices(monkeypatch):
    engine = create_engine("sqlite:///:memory:", future=True)
    Session = sessionmaker(bind=engine, future=True)
    Base.metadata.create_all(engine)

    monkeypatch.setattr(
        "app.services.market_data.fetch_price",
        lambda provider_symbol: (25.0, "CAD", datetime(2026, 1, 10, 12, 0, 0)),
    )

    with Session() as db:
        account = Account(name="TFSA")
        platform = Platform(canonical_name="Wealthsimple")
        instrument = Instrument(symbol="XEQT", provider_symbol="XEQT.TO", provider="yfinance", currency="CAD")
        db.add_all([account, platform, instrument])
        db.flush()
        db.add(
            Transaction(
                transaction_type=TransactionType.investment_buy,
                transaction_date=date(2026, 1, 2),
                account_id=account.id,
                platform_id=platform.id,
                instrument_id=instrument.id,
                amount=200,
                currency="CAD",
                quantity=10,
                fees=0,
            )
        )
        db.commit()

        refreshed = refresh_market_prices(db)
        rows = portfolio_pl(db, account="TFSA", year=2026)
        row = next(row for row in rows if row["symbol"] == "XEQT")

        assert refreshed[0]["status"] == "ok"
        assert db.query(MarketPrice).count() == 1
        assert row["current_price"] == 25
        assert row["market_value"] == 250
        assert row["unrealized_pl"] == 50
        assert row["unrealized_pl_pct"] == 25


def test_refresh_prices_prefers_tsx_symbol_for_cad_holdings(monkeypatch):
    engine = create_engine("sqlite:///:memory:", future=True)
    Session = sessionmaker(bind=engine, future=True)
    Base.metadata.create_all(engine)

    calls = []

    def fake_fetch_price(provider_symbol):
        calls.append(provider_symbol)
        if provider_symbol == "VEQT.TO":
            return 56.0, "CAD", datetime(2026, 1, 10, 12, 0, 0)
        raise ValueError("no recent price returned")

    monkeypatch.setattr("app.services.market_data.fetch_price", fake_fetch_price)

    with Session() as db:
        account = Account(name="TFSA")
        platform = Platform(canonical_name="Wealthsimple")
        instrument = Instrument(symbol="VEQT", provider_symbol="VEQT", provider="yfinance")
        db.add_all([account, platform, instrument])
        db.flush()
        db.add(
            Transaction(
                transaction_type=TransactionType.investment_buy,
                transaction_date=date(2026, 1, 2),
                account_id=account.id,
                platform_id=platform.id,
                instrument_id=instrument.id,
                amount=200,
                currency="CAD",
                quantity=10,
                fees=0,
            )
        )
        db.commit()

        refreshed = refresh_market_prices(db)

        assert calls == ["VEQT.TO"]
        assert refreshed[0]["status"] == "ok"
        assert refreshed[0]["provider_symbol"] == "VEQT.TO"
        assert instrument.provider_symbol == "VEQT.TO"


def test_refresh_prices_keeps_us_symbols_on_us_exchange(monkeypatch):
    engine = create_engine("sqlite:///:memory:", future=True)
    Session = sessionmaker(bind=engine, future=True)
    Base.metadata.create_all(engine)

    calls = []

    def fake_fetch_price(provider_symbol):
        calls.append(provider_symbol)
        return 360.0, "USD", datetime(2026, 1, 10, 12, 0, 0)

    monkeypatch.setattr("app.services.market_data.fetch_price", fake_fetch_price)

    with Session() as db:
        account = Account(name="TFSA")
        platform = Platform(canonical_name="Wealthsimple")
        instrument = Instrument(symbol="TSLA", provider_symbol="TSLA.TO", provider="yfinance")
        db.add_all([account, platform, instrument])
        db.flush()
        db.add(
            Transaction(
                transaction_type=TransactionType.investment_buy,
                transaction_date=date(2026, 1, 2),
                account_id=account.id,
                platform_id=platform.id,
                instrument_id=instrument.id,
                amount=200,
                currency="CAD",
                quantity=1,
                fees=0,
            )
        )
        db.commit()

        refreshed = refresh_market_prices(db)

        assert calls == ["TSLA"]
        assert refreshed[0]["provider_symbol"] == "TSLA"
        assert instrument.provider_symbol == "TSLA"
        assert instrument.currency == "USD"
