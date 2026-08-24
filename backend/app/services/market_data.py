from datetime import datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.models import Instrument, MarketPrice, Transaction

PROVIDER = "yfinance"
US_EXCHANGE_SYMBOLS = {"AVGO", "COST", "GOOG", "NVDA", "QQQM", "TSLA"}


def normalize_provider_symbol(symbol: str) -> str:
    return symbol.strip().upper()


def display_symbol(provider_symbol: str) -> str:
    value = normalize_provider_symbol(provider_symbol)
    return value[:-3] if value.endswith(".TO") else value


def provider_symbol_candidates(symbol: str, currency: str | None = None) -> list[str]:
    value = normalize_provider_symbol(symbol)
    base = display_symbol(value)
    if base in US_EXCHANGE_SYMBOLS:
        return [base]
    candidates = []
    if currency == "CAD" and not value.endswith(".TO"):
        candidates.append(f"{value.replace('.', '-')}.TO")
    candidates.append(value)
    return list(dict.fromkeys(candidates))


def _yf():
    import yfinance as yf

    return yf


def _quote_name(quote: dict[str, Any]) -> str | None:
    return quote.get("shortname") or quote.get("longname") or quote.get("name")


def upsert_instrument(
    db: Session,
    *,
    provider_symbol: str,
    symbol: str | None = None,
    name: str | None = None,
    exchange: str | None = None,
    currency: str | None = None,
    asset_type: str | None = None,
) -> Instrument:
    normalized_provider_symbol = normalize_provider_symbol(provider_symbol)
    instrument = db.scalar(
        select(Instrument).where(
            func.lower(Instrument.provider_symbol) == normalized_provider_symbol.lower(),
            Instrument.provider == PROVIDER,
        )
    )
    if not instrument:
        normalized_symbol = normalize_provider_symbol(symbol or display_symbol(normalized_provider_symbol))
        instrument = db.scalar(select(Instrument).where(func.lower(Instrument.symbol) == normalized_symbol.lower()))
    if not instrument:
        instrument = Instrument(symbol=normalize_provider_symbol(symbol or display_symbol(normalized_provider_symbol)))
        db.add(instrument)

    instrument.provider = PROVIDER
    instrument.provider_symbol = normalized_provider_symbol
    instrument.name = name or instrument.name
    instrument.exchange = exchange or instrument.exchange
    instrument.currency = currency or instrument.currency
    instrument.asset_type = asset_type or instrument.asset_type
    instrument.is_active = True
    db.flush()
    return instrument


def search_symbols(db: Session, query: str, limit: int = 8) -> list[dict[str, Any]]:
    term = query.strip()
    if not term:
        return []

    rows: list[Instrument] = list(
        db.scalars(
            select(Instrument)
            .where(
                or_(
                    Instrument.symbol.ilike(f"%{term}%"),
                    Instrument.provider_symbol.ilike(f"%{term}%"),
                    Instrument.name.ilike(f"%{term}%"),
                )
            )
            .order_by(Instrument.symbol)
            .limit(limit)
        )
    )

    try:
        quotes = _yf().Search(term, max_results=limit, news_count=0).quotes
    except Exception:
        quotes = []

    seen = {row.provider_symbol or row.symbol for row in rows}
    for quote in quotes:
        provider_symbol = quote.get("symbol")
        if not provider_symbol or provider_symbol in seen:
            continue
        instrument = upsert_instrument(
            db,
            provider_symbol=provider_symbol,
            name=_quote_name(quote),
            exchange=quote.get("exchDisp") or quote.get("exchange"),
            currency=quote.get("currency"),
            asset_type=quote.get("quoteType"),
        )
        rows.append(instrument)
        seen.add(provider_symbol)
        if len(rows) >= limit:
            break

    db.commit()
    return [serialize_instrument(row) for row in rows[:limit]]


def serialize_instrument(instrument: Instrument) -> dict[str, Any]:
    return {
        "id": instrument.id,
        "symbol": instrument.symbol,
        "provider_symbol": instrument.provider_symbol or instrument.symbol,
        "name": instrument.name,
        "exchange": instrument.exchange,
        "currency": instrument.currency,
        "asset_type": instrument.asset_type,
        "provider": instrument.provider or PROVIDER,
    }


def latest_price_subquery():
    return (
        select(
            MarketPrice.instrument_id,
            func.max(MarketPrice.priced_at).label("priced_at"),
        )
        .group_by(MarketPrice.instrument_id)
        .subquery()
    )


def latest_prices(db: Session) -> dict[int, MarketPrice]:
    latest = latest_price_subquery()
    rows = db.scalars(
        select(MarketPrice)
        .join(
            latest,
            (MarketPrice.instrument_id == latest.c.instrument_id)
            & (MarketPrice.priced_at == latest.c.priced_at),
        )
    ).all()
    return {row.instrument_id: row for row in rows}


def refresh_market_prices(db: Session) -> list[dict[str, Any]]:
    instrument_positions = (
        select(
            Transaction.instrument_id,
            func.max(Transaction.currency).label("currency"),
        )
        .where(Transaction.instrument_id.is_not(None), Transaction.quantity.is_not(None))
        .group_by(Transaction.instrument_id)
        .subquery()
    )
    instruments = list(
        db.execute(
            select(Instrument, instrument_positions.c.currency)
            .join(instrument_positions, instrument_positions.c.instrument_id == Instrument.id)
            .where(Instrument.is_active.is_(True))
            .order_by(Instrument.symbol)
        )
    )
    results = []
    for instrument, trade_currency in instruments:
        provider_symbol = instrument.provider_symbol or instrument.symbol
        candidates = provider_symbol_candidates(provider_symbol, trade_currency)
        last_error: Exception | None = None
        price = currency = priced_at = None
        resolved_symbol = provider_symbol
        for candidate in candidates:
            try:
                price, currency, priced_at = fetch_price(candidate)
                resolved_symbol = candidate
                break
            except Exception as exc:
                last_error = exc
        if price is None or priced_at is None:
            error = str(last_error) if last_error else "no recent price returned"
            results.append({
                "instrument_id": instrument.id,
                "symbol": instrument.symbol,
                "provider_symbol": provider_symbol,
                "status": "error",
                "error": error,
            })
            continue
        db.add(
            MarketPrice(
                instrument_id=instrument.id,
                price=price,
                currency=currency or instrument.currency,
                provider=PROVIDER,
                priced_at=priced_at,
            )
        )
        instrument.currency = currency or instrument.currency
        instrument.provider = PROVIDER
        instrument.provider_symbol = resolved_symbol
        results.append({
            "instrument_id": instrument.id,
            "symbol": instrument.symbol,
            "provider_symbol": resolved_symbol,
            "status": "ok",
            "price": price,
            "currency": currency or instrument.currency,
            "priced_at": priced_at,
        })
    db.commit()
    return results


def fetch_price(provider_symbol: str) -> tuple[float, str | None, datetime]:
    ticker = _yf().Ticker(provider_symbol)
    fast_info = getattr(ticker, "fast_info", None)
    price = _fast_value(fast_info, "last_price") or _fast_value(fast_info, "regularMarketPrice")
    currency = _fast_value(fast_info, "currency")
    if not price:
        try:
            history = ticker.history(period="5d")
        except Exception as exc:
            raise ValueError("no recent price returned") from exc
        if history.empty:
            raise ValueError("no recent price returned")
        price = float(history["Close"].dropna().iloc[-1])
    return float(price), currency, datetime.utcnow()


def fetch_usd_cad_rate() -> float:
    price, _currency, _priced_at = fetch_price("CAD=X")
    return float(price)


def _fast_value(fast_info: Any, key: str):
    if not fast_info:
        return None
    if hasattr(fast_info, "get"):
        try:
            return fast_info.get(key)
        except Exception:
            return None
    try:
        return fast_info[key]
    except Exception:
        return None
