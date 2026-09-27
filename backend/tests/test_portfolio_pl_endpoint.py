from app.api import routes


def _pl_row(row_id: str, platform: str, status: str = "ok", symbol: str = "XEQT"):
    return {
        "id": row_id,
        "as_of_date": "2026-01-01",
        "account_name": "TFSA",
        "platform_name": platform,
        "instrument_id": 1,
        "symbol": symbol,
        "provider_symbol": f"{symbol}.TO",
        "name": symbol,
        "broad_category": "All Equity",
        "precise_category": "All Equity",
        "record_type": "holding",
        "quantity": 1,
        "book_value": 10,
        "currency": "CAD",
        "current_price": 12,
        "price_currency": "CAD",
        "priced_at": "2026-01-01T12:00:00",
        "market_value": 12,
        "unrealized_pl": 2,
        "unrealized_pl_pct": 20,
        "price_status": status,
    }


def test_portfolio_pl_endpoint_forwards_filters_and_paginates(monkeypatch):
    calls = {}
    rows = [_pl_row(f"ok-{index}", "Questrade") for index in range(11)]

    def fake_portfolio_pl(_db, account=None, platform=None, status=None, year=None):
        calls.update({"account": account, "platform": platform, "status": status, "year": year})
        return rows

    monkeypatch.setattr(routes, "portfolio_pl", fake_portfolio_pl)

    result = routes.portfolio_pl_endpoint(
        account="TFSA",
        platform="Questrade",
        status="ok",
        year=2026,
        page=2,
        page_size=10,
        sort_direction="desc",
        db=object(),
    )

    assert calls == {"account": "TFSA", "platform": "Questrade", "status": "ok", "year": 2026}
    assert result.total == 11
    assert result.page == 2
    assert result.page_size == 10
    assert [row.id for row in result.items] == ["ok-10"]


def test_portfolio_pl_endpoint_sorts_symbols_desc_before_pagination(monkeypatch):
    rows = [
        _pl_row("a", "Questrade", symbol="AAPL"),
        _pl_row("z", "Questrade", symbol="ZMMK"),
        _pl_row("m", "Questrade", symbol="MSFT"),
    ]

    monkeypatch.setattr(routes, "portfolio_pl", lambda *_args, **_kwargs: rows)

    result = routes.portfolio_pl_endpoint(page=1, page_size=2, sort_direction="desc", db=object())

    assert [row.symbol for row in result.items] == ["ZMMK", "MSFT"]
