from datetime import datetime, time, timezone
from typing import Any

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models.models import Instrument, MarketPrice, Transaction

PROVIDER = "yfinance"
FX_SYMBOL = "USDCAD"
FX_PROVIDER_SYMBOL = "CAD=X"
FX_ASSET_TYPE = "fx"
PRICE_TIMEOUT_SECONDS = 10


def normalize_provider_symbol(symbol: str) -> str:
    return symbol.strip().upper()


def display_symbol(provider_symbol: str) -> str:
    value = normalize_provider_symbol(provider_symbol)
    return value[:-3] if value.endswith(".TO") else value


def provider_symbol_candidates(symbol: str, currency: str | None = None) -> list[str]:
    value = normalize_provider_symbol(symbol)
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
        if instrument and instrument.asset_type == "manual":
            raise ValueError(f"{instrument.symbol} is already used by a manual instrument")
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
    """Saved instruments first, then unsaved Yahoo candidates (id None). Never writes."""
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
                ),
                or_(Instrument.asset_type.is_(None), Instrument.asset_type != FX_ASSET_TYPE),
            )
            .order_by(Instrument.symbol)
            .limit(limit)
        )
    )
    results = [serialize_instrument(row) for row in rows]
    if len(results) >= limit:
        return results

    try:
        quotes = _yf().Search(term, max_results=limit, news_count=0, timeout=PRICE_TIMEOUT_SECONDS).quotes
    except Exception:
        quotes = []

    seen = {normalize_provider_symbol(row.provider_symbol or row.symbol) for row in rows}
    for quote in quotes:
        provider_symbol = normalize_provider_symbol(quote.get("symbol") or "")
        if not provider_symbol or provider_symbol in seen:
            continue
        results.append(
            {
                "id": None,
                "symbol": display_symbol(provider_symbol),
                "provider_symbol": provider_symbol,
                "name": _quote_name(quote),
                "exchange": quote.get("exchDisp") or quote.get("exchange"),
                "currency": quote.get("currency"),
                "asset_type": quote.get("quoteType"),
                "provider": PROVIDER,
            }
        )
        seen.add(provider_symbol)
        if len(results) >= limit:
            break
    return results


def save_symbol(db: Session, payload) -> dict[str, Any]:
    """Persist the search candidate the user picked."""
    instrument = upsert_instrument(
        db,
        provider_symbol=payload.provider_symbol,
        symbol=payload.symbol,
        name=payload.name,
        exchange=payload.exchange,
        currency=payload.currency,
        asset_type=payload.asset_type,
    )
    db.commit()
    return serialize_instrument(instrument)


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


def ensure_fx_instrument(db: Session) -> Instrument:
    instrument = db.scalar(select(Instrument).where(Instrument.symbol == FX_SYMBOL))
    if not instrument:
        instrument = Instrument(
            symbol=FX_SYMBOL,
            name="USD to CAD",
            provider_symbol=FX_PROVIDER_SYMBOL,
            provider=PROVIDER,
            currency="CAD",
            asset_type=FX_ASSET_TYPE,
            is_active=True,
        )
        db.add(instrument)
        db.flush()
    return instrument


def latest_fx_rate(db: Session) -> float | None:
    """CAD per USD from the last price refresh. None until prices are refreshed once."""
    price = db.scalar(
        select(MarketPrice.price)
        .join(Instrument, Instrument.id == MarketPrice.instrument_id)
        .where(Instrument.symbol == FX_SYMBOL)
        .order_by(MarketPrice.priced_at.desc())
        .limit(1)
    )
    return float(price) if price else None


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
    instruments.append((ensure_fx_instrument(db), None))
    priced_ids = set(db.scalars(select(MarketPrice.instrument_id).distinct()))

    plans = []
    for instrument, trade_currency in instruments:
        provider_symbol = instrument.provider_symbol or instrument.symbol
        # A stored price means provider_symbol was already resolved, so skip the ".TO" guess.
        if instrument.id in priced_ids:
            candidates = [provider_symbol]
        else:
            candidates = provider_symbol_candidates(provider_symbol, trade_currency)
        plans.append((instrument, provider_symbol, candidates))

    # One batched download for resolved symbols with a known currency. Unresolved symbols (and batch misses)
    # go one by one, because fetch_price also reports the currency of whichever candidate answers.
    def batchable(instrument, candidates):
        return bool(instrument.currency) and len(candidates) == 1

    batch = fetch_prices([candidates[0] for instrument, _, candidates in plans if batchable(instrument, candidates)])
    priced_at = utcnow()
    day_start = datetime.combine(priced_at.date(), time.min, tzinfo=timezone.utc)

    results = []
    for instrument, provider_symbol, candidates in plans:
        price = currency = None
        resolved_symbol = provider_symbol
        last_error: Exception | None = None
        if batchable(instrument, candidates) and candidates[0] in batch:
            price, currency, resolved_symbol = batch[candidates[0]], instrument.currency, candidates[0]
        else:
            for candidate in candidates:
                try:
                    price, currency, _ = fetch_price(candidate)
                    resolved_symbol = candidate
                    break
                except Exception as exc:
                    last_error = exc
        if price is None:
            results.append({
                "instrument_id": instrument.id,
                "symbol": instrument.symbol,
                "provider_symbol": provider_symbol,
                "status": "error",
                "error": str(last_error) if last_error else "no recent price returned",
            })
            continue
        # One price row per instrument per UTC day: a later refresh replaces today's row.
        db.execute(delete(MarketPrice).where(MarketPrice.instrument_id == instrument.id, MarketPrice.priced_at >= day_start))
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


def fetch_prices(provider_symbols: list[str]) -> dict[str, float]:
    """Latest close per symbol from one batched download. Symbols with no recent close are left out."""
    symbols = list(dict.fromkeys(provider_symbols))
    if not symbols:
        return {}
    try:
        data = _yf().download(
            symbols,
            period="5d",
            interval="1d",
            auto_adjust=False,
            progress=False,
            threads=True,
            timeout=PRICE_TIMEOUT_SECONDS,
            multi_level_index=True,
        )
        closes = data["Close"]
    except Exception:
        return {}
    prices = {}
    for symbol in symbols:
        if symbol not in closes:
            continue
        series = closes[symbol].dropna()
        if not series.empty:
            prices[symbol] = float(series.iloc[-1])
    return prices


def fetch_price(provider_symbol: str) -> tuple[float, str | None, datetime]:
    ticker = _yf().Ticker(provider_symbol)
    fast_info = getattr(ticker, "fast_info", None)
    price = _fast_value(fast_info, "last_price") or _fast_value(fast_info, "regularMarketPrice")
    currency = _fast_value(fast_info, "currency")
    if not price:
        try:
            history = ticker.history(period="5d", timeout=PRICE_TIMEOUT_SECONDS)
        except Exception as exc:
            raise ValueError("no recent price returned") from exc
        if history.empty:
            raise ValueError("no recent price returned")
        price = float(history["Close"].dropna().iloc[-1])
    return float(price), currency, utcnow()


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
