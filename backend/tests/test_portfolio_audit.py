from datetime import date, datetime, timedelta

import pytest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.time import market_date, utcnow
from app.db.session import Base, get_db
from app.main import app
from app.models.models import (
    Account,
    Category,
    Instrument,
    MarketPrice,
    Platform,
    PortfolioSnapshot,
    Transaction,
    TransactionType,
)
from app.services.portfolio import (
    distribution,
    list_holdings,
    portfolio_health,
    portfolio_history,
    portfolio_overview,
    portfolio_summary,
    record_portfolio_snapshots,
    sort_pl_rows,
    timeseries,
)

NOW = datetime.utcnow()


def _sessionmaker():
    engine = create_engine(
        "sqlite://", future=True, connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)


def _txn(account, platform, kind, amount, day=1, **extra):
    return Transaction(
        transaction_type=kind,
        transaction_date=date(2026, 1, day),
        account_id=account.id,
        platform_id=platform.id,
        amount=amount,
        currency=extra.pop("currency", "CAD"),
        **extra,
    )


def _portfolio(db, fx_rate=1.4, priced_at=NOW):
    """TFSA: CAD ETF (stale or fresh price) + USD stock + cash. RRSP: an overdrawn platform."""
    tfsa, rrsp = Account(name="TFSA"), Account(name="RRSP")
    ws, qt = Platform(canonical_name="Wealthsimple"), Platform(canonical_name="Questrade")
    equity = Category(broad="All Equity", precise="US Equity")
    xeqt = Instrument(symbol="XEQT", provider_symbol="XEQT.TO", currency="CAD")
    nvda = Instrument(symbol="NVDA", provider_symbol="NVDA", currency="USD")
    db.add_all([tfsa, rrsp, ws, qt, equity, xeqt, nvda])
    db.flush()
    db.add_all(
        [
            _txn(tfsa, ws, TransactionType.contribution, 1000),
            _txn(tfsa, ws, TransactionType.investment_buy, 500, day=2, instrument_id=xeqt.id, quantity=10, fees=0),
            _txn(tfsa, ws, TransactionType.contribution, 200, day=3, currency="USD"),
            _txn(tfsa, ws, TransactionType.investment_buy, 100, day=4, currency="USD", instrument_id=nvda.id, category_id=equity.id, quantity=1, fees=0),
            _txn(tfsa, ws, TransactionType.withdrawal, 100, day=5),
            _txn(rrsp, qt, TransactionType.investment_buy, 50, day=6, instrument_id=xeqt.id, quantity=1, fees=0),
            MarketPrice(instrument_id=xeqt.id, price=60, currency="CAD", priced_at=priced_at),
            MarketPrice(instrument_id=nvda.id, price=150, currency="USD", priced_at=NOW),
        ]
    )
    if fx_rate:
        fx = Instrument(symbol="USDCAD", provider_symbol="CAD=X", asset_type="fx", currency="CAD")
        db.add(fx)
        db.flush()
        db.add(MarketPrice(instrument_id=fx.id, price=fx_rate, currency="CAD", priced_at=NOW))
    db.commit()


def test_stale_prices_still_count_in_account_pl_and_keep_their_status():
    with _sessionmaker()() as db:
        _portfolio(db, priced_at=NOW - timedelta(days=3))

        summary = portfolio_summary(db)
        tfsa = next(row for row in summary["account_pl"] if row["account"] == "TFSA")

        # XEQT stale: 10 * 60 = 600 market on 500 book; NVDA fresh: 150 USD * 1.4 = 210 on 140.
        assert tfsa["bookReporting"] == 640
        assert tfsa["marketReporting"] == 810
        assert portfolio_health(db)["stale"] == 2  # TFSA and RRSP XEQT lots


def test_allocation_converts_usd_uses_market_value_and_matches_distribution():
    with _sessionmaker()() as db:
        _portfolio(db)

        allocation = {row["label"]: row["value"] for row in portfolio_summary(db)["allocation"]}
        sector = {row["label"]: row["value"] for row in distribution(db, "sector")}
        accounts = {row["label"]: row["value"] for row in distribution(db, "account")}

        # Cash: TFSA CAD 1000-500-100=400, USD 100*1.4=140; RRSP Questrade -50 nets the Cash slice.
        assert allocation == sector
        assert sector["US Equity"] == 210
        assert sector["Cash"] == 490
        assert sector["Uncategorized"] == 660  # XEQT market value 600 + 60, no category
        assert accounts == {"TFSA": 1350, "RRSP": 10}
        assert {row["label"]: row["value"] for row in distribution(db, "account", currency="USD")}["TFSA"] == pytest.approx(1350 / 1.4, abs=0.01)


def test_missing_fx_rate_is_flagged_not_silently_dropped():
    with _sessionmaker()() as db:
        _portfolio(db, fx_rate=None)

        health = portfolio_health(db)
        overview = portfolio_overview(db)

        assert health["fx_missing"] == 2  # NVDA holding and USD cash
        assert overview["health"]["fx_missing"] == 2
        assert overview["totals"]["book_value"] == 400 + 500 + 50 - 50  # CAD rows only


def test_withdrawal_reduces_cash_and_health_reports_negative_and_idle_cash():
    with _sessionmaker()() as db:
        _portfolio(db)

        cash = {
            (row["account_name"], row["currency"]): row["book_value"]
            for row in list_holdings(db)
            if row["record_type"] == "cash"
        }
        health = portfolio_health(db)

        assert cash[("TFSA", "CAD")] == 400
        assert health["negative_cash"] == [{"account_name": "RRSP", "platform_name": "Questrade", "currency": "CAD", "amount": -50}]
        assert {(row["account_name"], row["currency"]) for row in health["idle_cash"]} == {("TFSA", "CAD"), ("TFSA", "USD")}
        assert health["prices_updated_at"] is not None


def test_fractional_sell_of_whole_position_leaves_no_ghost_holding():
    with _sessionmaker()() as db:
        account, platform = Account(name="TFSA"), Platform(canonical_name="Wealthsimple")
        instrument = Instrument(symbol="VFV")
        db.add_all([account, platform, instrument])
        db.flush()
        db.add_all(
            [
                _txn(account, platform, TransactionType.investment_buy, 10, instrument_id=instrument.id, quantity=0.1),
                _txn(account, platform, TransactionType.investment_buy, 20, instrument_id=instrument.id, quantity=0.2),
                _txn(account, platform, TransactionType.investment_sell, 35, day=2, instrument_id=instrument.id, quantity=0.3),
            ]
        )
        db.commit()

        assert [row for row in list_holdings(db) if row["record_type"] == "holding"] == []


def test_timeseries_nets_sells_and_reports_withdrawals_and_dividends_in_cad():
    with _sessionmaker()() as db:
        _portfolio(db)
        account = db.query(Account).filter_by(name="TFSA").one()
        platform = db.query(Platform).filter_by(canonical_name="Wealthsimple").one()
        xeqt = db.query(Instrument).filter_by(symbol="XEQT").one()
        db.add_all(
            [
                _txn(account, platform, TransactionType.investment_sell, 120, day=20, instrument_id=xeqt.id, quantity=2),
                _txn(account, platform, TransactionType.dividend_interest, 10, day=21),
                Transaction(
                    transaction_type=TransactionType.contribution,
                    transaction_date=date(2025, 12, 31),
                    account_id=account.id,
                    platform_id=platform.id,
                    amount=999,
                    currency="CAD",
                ),
            ]
        )
        db.commit()

        assert timeseries(db, year=2026) == [
            {
                "month": "2026-01",
                "currency": "CAD",
                "contributions": 1000 + 200 * 1.4,
                "investments": 500 + 140 + 50 - 120,
                "withdrawals": 100,
                "dividends": 10,
            }
        ]


def test_overview_totals_and_snapshot_history():
    with _sessionmaker()() as db:
        _portfolio(db)

        totals = portfolio_overview(db)["totals"]
        record_portfolio_snapshots(db)
        record_portfolio_snapshots(db)  # same day: upsert, not duplicate

        # Book: cash 400 + 140 - 50, XEQT 500 + 50, NVDA 140. Market adds XEQT 660 and NVDA 210.
        assert totals["book_value"] == 1180
        assert totals["market_value"] == 1360
        assert totals["unrealized_pl"] == 180
        assert totals["unrealized_pl_pct"] == round(180 / 690 * 100, 2)
        assert totals["investable_cash"] == 540
        assert db.query(PortfolioSnapshot).count() == 2

        client = _client(db)
        history = client.get("/portfolio/history", headers={"X-Requested-With": "master-terminal"}).json()
        assert history == [{"date": str(market_date()), "book_value": 1180, "market_value": 1360, "currency": "CAD"}]


def test_sort_pl_rows_by_market_value_puts_unpriced_rows_last():
    rows = [
        {"symbol": "A", "market_value_reporting": 10},
        {"symbol": "B", "market_value_reporting": None},
        {"symbol": "C", "market_value_reporting": 30},
    ]

    assert [row["symbol"] for row in sort_pl_rows(rows, "market_value", "desc")] == ["C", "A", "B"]
    assert [row["symbol"] for row in sort_pl_rows(rows, "market_value", "asc")] == ["A", "C", "B"]


def _client(db):
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app, base_url="http://localhost")


def test_portfolio_endpoints_respond_and_symbol_conflict_is_409():
    with _sessionmaker()() as db:
        _portfolio(db)
        db.add(Instrument(symbol="MYFUND", asset_type="manual"))
        db.commit()
        client = _client(db)
        headers = {"X-Requested-With": "master-terminal"}
        try:
            overview = client.get("/portfolio/overview", headers=headers)
            health = client.get("/portfolio/health", headers=headers)
            pl = client.get("/portfolio/pl?sort_by=market_value&page_size=50", headers=headers)
            conflict = client.post("/symbols", json={"provider_symbol": "MYFUND.TO"}, headers=headers)
            saved = client.post("/symbols", json={"provider_symbol": "ZAG.TO", "currency": "CAD"}, headers=headers)
        finally:
            app.dependency_overrides.clear()

        assert overview.status_code == 200
        assert set(overview.json()["distribution"]) == {"sector", "account", "platform"}
        assert health.status_code == 200
        assert pl.status_code == 200
        assert pl.json()["items"][0]["symbol"] == "XEQT"  # 660 CAD beats NVDA 210 CAD
        assert conflict.status_code == 409
        assert saved.status_code == 200 and saved.json()["symbol"] == "ZAG"


def test_usd_reporting_converts_overview_history_and_timeseries():
    with _sessionmaker()() as db:
        _portfolio(db)
        record_portfolio_snapshots(db)

        cad = portfolio_overview(db)["totals"]
        usd = portfolio_overview(db, currency="USD")["totals"]
        history = portfolio_history(db, currency="USD")
        months = timeseries(db, year=2026, currency="USD")

        assert (cad["currency"], cad["fx_missing"]) == ("CAD", False)
        assert (usd["currency"], usd["fx_missing"]) == ("USD", False)
        assert usd["market_value"] == pytest.approx(1360 / 1.4, abs=0.02)
        assert usd["investable_cash"] == pytest.approx(540 / 1.4, abs=0.02)
        assert history[0]["currency"] == "USD"
        assert history[0]["book_value"] == pytest.approx(1180 / 1.4, abs=0.01)
        # USD transactions keep their native amount; CAD ones divide by the rate.
        assert months[0]["currency"] == "USD"
        assert months[0]["contributions"] == pytest.approx(1000 / 1.4 + 200, abs=0.01)


def test_usd_request_without_rate_falls_back_to_cad_and_flags_it():
    with _sessionmaker()() as db:
        _portfolio(db, fx_rate=None)
        client = _client(db)
        headers = {"X-Requested-With": "master-terminal"}
        try:
            overview = client.get("/portfolio/overview?currency=USD", headers=headers).json()
            history = client.get("/portfolio/history?currency=USD", headers=headers)
            months = client.get("/analytics/timeseries?year=2026&currency=USD", headers=headers).json()
            bad = client.get("/portfolio/overview?currency=EUR", headers=headers)
        finally:
            app.dependency_overrides.clear()

        assert (overview["totals"]["currency"], overview["totals"]["fx_missing"]) == ("CAD", True)
        assert overview["totals"]["book_value"] == 900  # CAD rows only; USD rows counted in health
        assert history.status_code == 200
        assert months[0]["currency"] == "CAD" and months[0]["contributions"] == 1000
        assert bad.status_code == 422
