from datetime import date, datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.models import Account, Instrument, MarketPrice, Platform, PortfolioSnapshot, Transaction, TransactionType
from app.schemas.portfolio import SymbolCreate
from app.services.market_data import FX_SYMBOL, latest_fx_rate, refresh_market_prices, save_symbol, search_symbols
from app.services.portfolio import portfolio_pl, record_portfolio_snapshots


def _session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)()


def _buy(db, instrument, currency="CAD", quantity=10):
    account = Account(name="TFSA")
    platform = Platform(canonical_name="Wealthsimple")
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
            currency=currency,
            quantity=quantity,
            fees=0,
        )
    )
    db.commit()


def test_symbol_search_returns_unsaved_candidates_and_save_persists_one(monkeypatch):
    class FakeSearch:
        def __init__(self, _query, max_results=8, news_count=0, timeout=30):
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

    with _session() as db:
        results = search_symbols(db, "xeqt")

        assert results[0]["id"] is None
        assert results[0]["symbol"] == "XEQT"
        assert results[0]["provider_symbol"] == "XEQT.TO"
        assert db.query(Instrument).count() == 0

        saved = save_symbol(db, SymbolCreate(**{key: value for key, value in results[0].items() if key not in {"id", "provider"}}))

        assert saved["id"] is not None
        assert db.get(Instrument, saved["id"]).provider_symbol == "XEQT.TO"
        assert search_symbols(db, "xeqt")[0]["id"] == saved["id"]


def test_symbol_search_hides_fx_instrument(monkeypatch):
    monkeypatch.setattr("app.services.market_data._yf", lambda: None)  # provider unavailable: DB rows only

    with _session() as db:
        db.add_all([Instrument(symbol=FX_SYMBOL, provider_symbol="CAD=X", asset_type="fx"), Instrument(symbol="USDCAD2")])
        db.commit()

        assert [row["symbol"] for row in search_symbols(db, "usdcad")] == ["USDCAD2"]


def test_refresh_batches_resolved_symbols_and_stores_fx(monkeypatch):
    batches = []

    def fake_fetch_prices(symbols):
        batches.append(symbols)
        return {"XEQT.TO": 25.0, "CAD=X": 1.35}

    def unexpected_fetch_price(_symbol):
        raise AssertionError("resolved symbols should come from the batch")

    monkeypatch.setattr("app.services.market_data.fetch_prices", fake_fetch_prices)
    monkeypatch.setattr("app.services.market_data.fetch_price", unexpected_fetch_price)

    with _session() as db:
        instrument = Instrument(symbol="XEQT", provider_symbol="XEQT.TO", provider="yfinance", currency="CAD")
        _buy(db, instrument)

        refreshed = refresh_market_prices(db)
        refresh_market_prices(db)  # same UTC day: replaces today's row instead of adding one
        rows = portfolio_pl(db, account="TFSA", year=2026)
        row = next(row for row in rows if row["symbol"] == "XEQT")

        assert batches[0] == ["XEQT.TO", "CAD=X"]
        assert {result["status"] for result in refreshed} == {"ok"}
        assert db.query(MarketPrice).filter(MarketPrice.instrument_id == instrument.id).count() == 1
        assert latest_fx_rate(db) == 1.35
        assert row["current_price"] == 25
        assert row["market_value"] == 250
        assert row["unrealized_pl"] == 50
        assert row["unrealized_pl_pct"] == 25
        assert row["price_status"] == "ok"


def test_refresh_prices_prefers_tsx_symbol_for_cad_holdings(monkeypatch):
    calls = []

    def fake_fetch_price(provider_symbol):
        calls.append(provider_symbol)
        if provider_symbol == "VEQT.TO":
            return 56.0, "CAD", datetime(2026, 1, 10, 12, 0, 0)
        raise ValueError("no recent price returned")

    monkeypatch.setattr("app.services.market_data.fetch_prices", lambda symbols: {"CAD=X": 1.35})
    monkeypatch.setattr("app.services.market_data.fetch_price", fake_fetch_price)

    with _session() as db:
        instrument = Instrument(symbol="VEQT", provider_symbol="VEQT", provider="yfinance")
        _buy(db, instrument)

        refreshed = refresh_market_prices(db)

        assert calls == ["VEQT.TO"]
        assert refreshed[0]["status"] == "ok"
        assert refreshed[0]["provider_symbol"] == "VEQT.TO"
        assert instrument.provider_symbol == "VEQT.TO"


def test_refresh_never_adopts_a_listing_in_another_currency(monkeypatch):
    calls = []

    def fake_fetch_price(provider_symbol):
        calls.append(provider_symbol)
        if provider_symbol == "SHOP":
            return 150.0, "USD", datetime(2026, 1, 10, 12, 0, 0)  # NYSE listing
        raise ValueError("no recent price returned")  # SHOP.TO hiccup

    monkeypatch.setattr("app.services.market_data.fetch_prices", lambda symbols: {"CAD=X": 1.35})
    monkeypatch.setattr("app.services.market_data.fetch_price", fake_fetch_price)

    with _session() as db:
        instrument = Instrument(symbol="SHOP", provider_symbol="SHOP", provider="yfinance")
        _buy(db, instrument, currency="CAD", quantity=1)

        result = next(row for row in refresh_market_prices(db) if row["symbol"] == "SHOP")

        assert calls == ["SHOP.TO", "SHOP"]
        assert result["status"] == "error" and "trades in USD" in result["error"]
        assert (instrument.provider_symbol, instrument.currency) == ("SHOP", None)
        assert db.query(MarketPrice).filter(MarketPrice.instrument_id == instrument.id).count() == 0


def test_resolved_us_symbol_held_in_usd_stays_batched(monkeypatch):
    calls = []
    monkeypatch.setattr("app.services.market_data.fetch_price", lambda symbol: calls.append(symbol) or (360.0, "USD", datetime(2026, 1, 10)))
    monkeypatch.setattr("app.services.market_data.fetch_prices", lambda symbols: {"CAD=X": 1.35})

    with _session() as db:
        instrument = Instrument(symbol="TSLA", provider_symbol="TSLA", provider="yfinance")
        _buy(db, instrument, currency="USD", quantity=1)

        refresh_market_prices(db)
        assert calls == ["TSLA"]
        assert (instrument.provider_symbol, instrument.currency) == ("TSLA", "USD")

        batches = []
        monkeypatch.setattr("app.services.market_data.fetch_prices", lambda symbols: batches.append(symbols) or {"TSLA": 361.0, "CAD=X": 1.35})
        calls.clear()
        refresh_market_prices(db)
        assert calls == []
        assert batches == [["TSLA", "CAD=X"]]


def test_picking_other_listing_creates_twin_instead_of_repointing_held_one():
    with _session() as db:
        tsx = Instrument(symbol="SHOP", provider_symbol="SHOP.TO", provider="yfinance", currency="CAD", exchange="Toronto")
        _buy(db, tsx, currency="CAD", quantity=2)

        nyse = save_symbol(db, SymbolCreate(provider_symbol="SHOP", symbol="SHOP", exchange="NYSE", currency="USD"))
        again = save_symbol(db, SymbolCreate(provider_symbol="SHOP", symbol="SHOP", exchange="NYSE", currency="USD"))

        assert nyse["symbol"] == "SHOP (NYSE)" and nyse["currency"] == "USD"
        assert again["id"] == nyse["id"]
        db.refresh(tsx)
        assert (tsx.provider_symbol, tsx.currency, tsx.exchange) == ("SHOP.TO", "CAD", "Toronto")


def test_placeholder_instrument_can_still_be_upgraded_in_place():
    with _session() as db:
        placeholder = Instrument(symbol="VEQT", provider_symbol="VEQT", provider="yfinance")
        _buy(db, placeholder, currency="CAD")

        saved = save_symbol(db, SymbolCreate(provider_symbol="VEQT.TO", symbol="VEQT", currency="CAD"))

        assert saved["id"] == placeholder.id
        assert saved["provider_symbol"] == "VEQT.TO"


def test_price_day_follows_toronto_calendar(monkeypatch):
    # 03:30 UTC on Oct 10 is 23:30 on Oct 9 in Toronto (EDT).
    late_evening = datetime(2026, 10, 10, 3, 30, tzinfo=timezone.utc)
    monkeypatch.setattr("app.services.market_data.utcnow", lambda: late_evening)
    monkeypatch.setattr("app.services.market_data.fetch_prices", lambda symbols: {"XEQT.TO": 47.0, "CAD=X": 1.35})
    monkeypatch.setattr("app.core.time.utcnow", lambda: late_evening)

    with _session() as db:
        instrument = Instrument(symbol="XEQT", provider_symbol="XEQT.TO", provider="yfinance", currency="CAD")
        _buy(db, instrument)
        db.add_all(
            [
                # Oct 9 18:00 Toronto: same Toronto day, replaced by the 23:30 refresh.
                MarketPrice(instrument_id=instrument.id, price=46, currency="CAD", priced_at=datetime(2026, 10, 9, 22, 0)),
                # Oct 8 23:00 Toronto: previous day, kept.
                MarketPrice(instrument_id=instrument.id, price=45, currency="CAD", priced_at=datetime(2026, 10, 9, 3, 0)),
            ]
        )
        db.commit()

        refresh_market_prices(db)
        record_portfolio_snapshots(db)

        prices = sorted(float(row.price) for row in db.query(MarketPrice).filter(MarketPrice.instrument_id == instrument.id))
        assert prices == [45, 47]
        assert {row.snapshot_date for row in db.query(PortfolioSnapshot)} == {date(2026, 10, 9)}
