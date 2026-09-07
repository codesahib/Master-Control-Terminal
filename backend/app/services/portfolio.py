from datetime import date, datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, aliased

from app.models.models import Account, Category, HoldingSnapshot, Instrument, Platform, Transaction, TransactionType
from app.services.market_data import fetch_usd_cad_rate, latest_prices


def portfolio_summary(db: Session, year=None):
    rows = portfolio_pl(db, year=year)
    leaf_rows = [leaf for row in rows for leaf in (row["children"] or [row])]
    account_names = list(db.scalars(select(Account.name).order_by(Account.name)))

    allocation = {}
    for row in rows:
        value = row.get("market_value_reporting") or row.get("book_value_reporting") or row.get("market_value") or row["book_value"]
        if not value:
            continue
        label = row.get("precise_category") or row.get("broad_category") or "Uncategorized"
        allocation[label] = allocation.get(label, 0.0) + float(value)

    account_pl = []
    for account_name in account_names:
        totals = {
            "book": 0.0,
            "market": 0.0,
            "pl": 0.0,
            "bookReporting": 0.0,
            "marketReporting": 0.0,
            "plReporting": 0.0,
        }
        for row in leaf_rows:
            if row["account_name"] != account_name or row["price_status"] != "ok":
                continue
            totals["book"] += float(row["book_value"])
            totals["market"] += float(row.get("market_value") or 0)
            totals["pl"] += float(row.get("unrealized_pl") or 0)
            totals["bookReporting"] += float(row.get("book_value_reporting") or 0)
            totals["marketReporting"] += float(row.get("market_value_reporting") or 0)
            totals["plReporting"] += float(row.get("unrealized_pl_reporting") or 0)
        account_pl.append(
            {
                "account": account_name,
                **totals,
                "plPct": (totals["plReporting"] / totals["bookReporting"] * 100) if totals["bookReporting"] else None,
            }
        )

    return {
        "investable_cash": [row for row in rows if row["record_type"] == "cash" and row["book_value"] > 0],
        "allocation": [{"label": label, "value": value} for label, value in sorted(allocation.items(), key=lambda item: item[1], reverse=True)],
        "account_pl": account_pl,
    }


def list_holdings(db: Session, account=None, year=None):
    as_of_date = date.today() if year is None or year >= date.today().year else date(year, 12, 31)
    source_platform = aliased(Platform)
    q = (
        select(
            Transaction,
            Account,
            Platform,
            source_platform,
            Instrument,
            Category,
        )
        .outerjoin(Account, Transaction.account_id == Account.id)
        .outerjoin(Platform, Transaction.platform_id == Platform.id)
        .outerjoin(source_platform, Transaction.source_platform_id == source_platform.id)
        .outerjoin(Instrument, Transaction.instrument_id == Instrument.id)
        .outerjoin(Category, Transaction.category_id == Category.id)
        .where(Transaction.transaction_date <= as_of_date)
        .order_by(Transaction.transaction_date, Transaction.id)
    )
    if account:
        q = q.where(func.lower(Account.name) == account.lower())

    cash = {}
    positions = {}

    def cash_row(account_row, platform, currency):
        cash_key = (account_row.id, platform.id if platform else None, currency)
        return cash.setdefault(
            cash_key,
            {
                "account_name": account_row.name,
                "platform_name": platform.canonical_name if platform else None,
                "currency": currency,
                "book_value": 0.0,
            },
        )

    def adjust_cash(account_row, platform, currency, amount):
        cash_row(account_row, platform, currency)["book_value"] += amount

    for txn, account_row, platform, source_platform_row, instrument, category in db.execute(q):
        if not account_row:
            continue

        currency = txn.currency or "CAD"
        cash_row(account_row, platform, currency)
        fee_currency = txn.fee_currency or currency
        fees = float(txn.fees or 0)

        if txn.transaction_type == TransactionType.contribution:
            adjust_cash(account_row, platform, currency, float(txn.amount))
            continue
        if txn.transaction_type == TransactionType.dividend_interest:
            adjust_cash(account_row, platform, currency, float(txn.amount))
            adjust_cash(account_row, platform, fee_currency, -fees)
            continue
        if txn.transaction_type == TransactionType.transfer:
            if source_platform_row:
                adjust_cash(account_row, source_platform_row, currency, -float(txn.amount))
                adjust_cash(account_row, source_platform_row, fee_currency, -fees)
                adjust_cash(account_row, platform, currency, float(txn.amount))
            continue
        if txn.transaction_type == TransactionType.currency_exchange:
            adjust_cash(account_row, platform, txn.source_currency or "CAD", -float(txn.source_amount or 0))
            adjust_cash(account_row, platform, fee_currency, -fees)
            adjust_cash(account_row, platform, currency, float(txn.amount))
            continue
        if txn.transaction_type not in {
            TransactionType.investment_buy,
            TransactionType.investment_sell,
            TransactionType.dividend_reinvestment,
            TransactionType.quantity_adjustment,
        }:
            continue

        amount = float(txn.amount)
        if txn.transaction_type == TransactionType.investment_buy:
            cash_currency = txn.source_currency or currency
            cash_amount = float(txn.source_amount if txn.source_amount is not None else txn.amount)
            adjust_cash(account_row, platform, cash_currency, -cash_amount)
        elif txn.transaction_type == TransactionType.dividend_reinvestment and txn.source_amount is not None:
            adjust_cash(account_row, platform, txn.source_currency or currency, -float(txn.source_amount))
        elif txn.transaction_type == TransactionType.investment_sell:
            adjust_cash(account_row, platform, currency, amount)
        adjust_cash(account_row, platform, fee_currency, -fees)

        position_key = (account_row.id, platform.id if platform else None, instrument.id if instrument else None, currency)
        position = positions.setdefault(
            position_key,
            {
                "instrument_id": instrument.id if instrument else None,
                "account_name": account_row.name,
                "platform_name": platform.canonical_name if platform else None,
                "currency": currency,
                "symbol": instrument.symbol if instrument else "Unspecified",
                "provider_symbol": instrument.provider_symbol if instrument else None,
                "name": instrument.name if instrument else None,
                "category_id": None,
                "broad_category": None,
                "precise_category": None,
                "quantity": 0.0,
                "book_value": 0.0,
                "has_quantity": False,
            },
        )
        if category:
            position["category_id"] = category.id
            position["broad_category"] = category.broad
            position["precise_category"] = category.precise

        if txn.transaction_type in {TransactionType.investment_buy, TransactionType.dividend_reinvestment}:
            position["book_value"] += amount + fees
            if txn.quantity is not None:
                position["quantity"] += txn.quantity
                position["has_quantity"] = True
            continue

        if txn.transaction_type == TransactionType.quantity_adjustment:
            if txn.quantity is not None:
                position["quantity"] += txn.quantity
                position["has_quantity"] = True
            continue

        if txn.quantity is not None and position["quantity"]:
            position["book_value"] -= position["book_value"] * (txn.quantity / position["quantity"])
            position["quantity"] -= txn.quantity
            position["has_quantity"] = True
        else:
            position["book_value"] -= amount

    holdings = []
    for (account_id, platform_id, currency), row in cash.items():
        book_value = round(row["book_value"], 2)
        if book_value:
            holdings.append(
                {
                    "id": f"cash:{account_id}:{platform_id or 0}:{currency}",
                    "as_of_date": as_of_date,
                    "account_id": account_id,
                    "platform_id": platform_id,
                    "category_id": None,
                    "account_name": row["account_name"],
                    "platform_name": row["platform_name"],
                    "instrument_id": None,
                    "symbol": "Cash",
                    "broad_category": "Cash",
                    "precise_category": "Cash",
                    "record_type": "cash",
                    "quantity": None,
                    "book_value": book_value,
                    "currency": row["currency"],
                }
            )
    for (account_id, platform_id, instrument_id, currency), row in positions.items():
        if row["quantity"] or row["book_value"]:
            holdings.append(
                {
                    "id": f"holding:{account_id}:{platform_id or 0}:{instrument_id or 0}:{currency}",
                    "as_of_date": as_of_date,
                    "account_id": account_id,
                    "platform_id": platform_id,
                    "category_id": row["category_id"],
                    "account_name": row["account_name"],
                    "platform_name": row["platform_name"],
                    "instrument_id": row["instrument_id"],
                    "symbol": row["symbol"],
                    "provider_symbol": row["provider_symbol"],
                    "name": row["name"],
                    "broad_category": row["broad_category"],
                    "precise_category": row["precise_category"],
                    "record_type": "holding",
                    "quantity": row["quantity"] if row["has_quantity"] else None,
                    "book_value": row["book_value"],
                    "currency": row["currency"],
                }
            )
    return sorted(
        holdings,
        key=lambda row: (row["account_name"], row["record_type"], row["symbol"], row["currency"], row.get("platform_name") or ""),
    )


def grouped_holdings(db: Session, account=None, year=None):
    return _group_holding_rows(list_holdings(db, account=account, year=year))


def _group_holding_rows(rows: list[dict]):
    grouped = {}
    for row in rows:
        key = (
            row["record_type"],
            row["instrument_id"],
            row["symbol"],
            row["currency"],
        )
        group = grouped.setdefault(
            key,
            {
                **row,
                "id": f"{row['record_type']}:{row['symbol']}:{row['currency']}",
                "platform_name": None,
                "quantity": 0.0 if row["quantity"] is not None else None,
                "book_value": 0.0,
                "average_price": None,
                "children": [],
            },
        )
        child = {**row, "average_price": _average_price(row), "children": []}
        group["children"].append(child)
        group["book_value"] = round(float(group["book_value"]) + float(row["book_value"]), 2)
        if row["quantity"] is not None:
            group["quantity"] = round(float(group["quantity"] or 0) + float(row["quantity"]), 6)
    for group in grouped.values():
        accounts = {child["account_name"] for child in group["children"]}
        group["account_name"] = group["children"][0]["account_name"] if len(accounts) == 1 else "All"
        group["average_price"] = _average_price(group)
        group["children"].sort(key=lambda child: child.get("platform_name") or "")
    return sorted(grouped.values(), key=lambda row: (row["record_type"], row["symbol"], row["currency"]))


def _average_price(row: dict):
    quantity = row.get("quantity")
    if not quantity:
        return None
    return round(float(row["book_value"]) / float(quantity), 4)


def portfolio_pl(db: Session, account=None, year=None, platform=None, status=None):
    rows = _portfolio_pl_rows(db, account=account, year=year)
    if platform:
        rows = [row for row in rows if (row.get("platform_name") or "").lower() == platform.lower()]
    if status:
        rows = [row for row in rows if row.get("price_status", "").lower() == status.lower()]
    return _group_pl_rows(rows)


def _portfolio_pl_rows(db: Session, account=None, year=None):
    prices = latest_prices(db)
    manual_values = _latest_manual_values(db)
    usd_cad_rate = _usd_cad_rate()
    rows = []
    for holding in list_holdings(db, account=account, year=year):
        row = dict(holding)
        instrument_id = row.get("instrument_id")
        price = prices.get(instrument_id) if instrument_id else None
        if row["record_type"] != "cash" and row["quantity"] is None:
            price = None
        row["current_price"] = float(price.price) if price else None
        row["price_currency"] = price.currency if price else None
        row["priced_at"] = price.priced_at if price else None
        row["manual_valuation_date"] = None
        row["provider_symbol"] = row.get("provider_symbol")
        row["name"] = row.get("name")
        if row["record_type"] == "cash":
            row["market_value"] = row["book_value"]
            row["unrealized_pl"] = 0.0
            row["unrealized_pl_pct"] = 0.0
            row["price_status"] = "cash"
        elif row["quantity"] is None:
            manual_value = _manual_value_for_holding(manual_values, row)
            if manual_value:
                market_value = round(float(manual_value["market_value"]), 2)
                unrealized_pl = round(market_value - float(row["book_value"]), 2)
                row["market_value"] = market_value
                row["unrealized_pl"] = unrealized_pl
                row["unrealized_pl_pct"] = round(unrealized_pl / float(row["book_value"]) * 100, 2) if row["book_value"] else None
                row["manual_valuation_date"] = manual_value["snapshot_date"]
                row["price_status"] = "ok"
            else:
                row["market_value"] = None
                row["unrealized_pl"] = None
                row["unrealized_pl_pct"] = None
                row["price_status"] = "missing_quantity"
        elif not price:
            row["market_value"] = None
            row["unrealized_pl"] = None
            row["unrealized_pl_pct"] = None
            row["price_status"] = "missing"
        elif price.currency and price.currency != row["currency"]:
            row["market_value"] = None
            row["unrealized_pl"] = None
            row["unrealized_pl_pct"] = None
            row["price_status"] = "currency_mismatch"
        else:
            market_value = round(float(row["quantity"]) * float(price.price), 2)
            unrealized_pl = round(market_value - float(row["book_value"]), 2)
            row["market_value"] = market_value
            row["unrealized_pl"] = unrealized_pl
            row["unrealized_pl_pct"] = round(unrealized_pl / float(row["book_value"]) * 100, 2) if row["book_value"] else None
            row["price_status"] = "stale" if price.priced_at < datetime.utcnow() - timedelta(hours=24) else "ok"
        _add_reporting_values(row, usd_cad_rate)
        rows.append(row)
    return rows


def _usd_cad_rate():
    try:
        return fetch_usd_cad_rate()
    except Exception:
        return None


def _to_cad(value, currency: str | None, usd_cad_rate: float | None):
    if value is None:
        return None
    if currency == "CAD":
        return round(float(value), 2)
    if currency == "USD" and usd_cad_rate:
        return round(float(value) * usd_cad_rate, 2)
    return None


def _add_reporting_values(row: dict, usd_cad_rate: float | None):
    row["reporting_currency"] = "CAD"
    row["fx_rate_to_reporting"] = 1.0 if row["currency"] == "CAD" else (usd_cad_rate if row["currency"] == "USD" else None)
    row["book_value_reporting"] = _to_cad(row.get("book_value"), row.get("currency"), usd_cad_rate)
    row["market_value_reporting"] = _to_cad(row.get("market_value"), row.get("currency"), usd_cad_rate)
    row["unrealized_pl_reporting"] = _to_cad(row.get("unrealized_pl"), row.get("currency"), usd_cad_rate)


def _latest_manual_values(db: Session):
    rows = {}
    q = select(HoldingSnapshot).order_by(HoldingSnapshot.snapshot_date, HoldingSnapshot.id)
    for snapshot in db.scalars(q):
        key = (
            snapshot.account_id,
            snapshot.platform_id,
            snapshot.instrument_id,
            snapshot.category_id,
            snapshot.record_type,
        )
        rows[key] = {
            "market_value": snapshot.market_value,
            "snapshot_date": snapshot.snapshot_date,
        }
    return rows


def _manual_value_for_holding(manual_values: dict, row: dict):
    keys = [
        (row.get("account_id"), row.get("platform_id"), row.get("instrument_id"), row.get("category_id"), row["record_type"]),
        (row.get("account_id"), None, row.get("instrument_id"), row.get("category_id"), row["record_type"]),
    ]
    for key in keys:
        if key in manual_values:
            return manual_values[key]
    return None


def _group_pl_rows(rows: list[dict]):
    grouped = _group_holding_rows(rows)
    for group in grouped:
        children = group["children"]
        market_values = [float(row["market_value"]) for row in children if row.get("market_value") is not None]
        unrealized_values = [float(row["unrealized_pl"]) for row in children if row.get("unrealized_pl") is not None]
        statuses = {row["price_status"] for row in children}
        group["current_price"] = children[0].get("current_price") if len({row.get("current_price") for row in children}) == 1 else None
        group["price_currency"] = children[0].get("price_currency") if len({row.get("price_currency") for row in children}) == 1 else None
        group["priced_at"] = max((row["priced_at"] for row in children if row.get("priced_at")), default=None)
        group["manual_valuation_date"] = max(
            (row["manual_valuation_date"] for row in children if row.get("manual_valuation_date")),
            default=None,
        )
        group["market_value"] = round(sum(market_values), 2) if market_values else None
        group["unrealized_pl"] = round(sum(unrealized_values), 2) if unrealized_values else None
        group["reporting_currency"] = "CAD"
        group["fx_rate_to_reporting"] = children[0].get("fx_rate_to_reporting") if len({row.get("fx_rate_to_reporting") for row in children}) == 1 else None
        group["book_value_reporting"] = round(
            sum(float(row["book_value_reporting"]) for row in children if row.get("book_value_reporting") is not None),
            2,
        )
        reporting_market_values = [float(row["market_value_reporting"]) for row in children if row.get("market_value_reporting") is not None]
        reporting_pl_values = [float(row["unrealized_pl_reporting"]) for row in children if row.get("unrealized_pl_reporting") is not None]
        group["market_value_reporting"] = round(sum(reporting_market_values), 2) if reporting_market_values else None
        group["unrealized_pl_reporting"] = round(sum(reporting_pl_values), 2) if reporting_pl_values else None
        group["unrealized_pl_pct"] = (
            round(float(group["unrealized_pl"]) / float(group["book_value"]) * 100, 2)
            if group.get("unrealized_pl") is not None and group["book_value"]
            else None
        )
        group["price_status"] = children[0]["price_status"] if len(statuses) == 1 else "mixed"
    return grouped


def distribution(db: Session, group_by: str, year: int | None = None, category_level: str = "precise", currency: str = "CAD"):
    totals = {}
    for holding in list_holdings(db, year=year):
        if holding["currency"] != currency:
            continue
        if group_by == "sector":
            label = holding["broad_category"] if category_level == "broad" else holding["precise_category"]
        elif group_by == "account":
            label = holding["account_name"]
        else:
            label = holding["platform_name"]
        label = label or "Uncategorized"
        totals[label] = totals.get(label, 0.0) + holding["book_value"]
    return [{"label": label, "value": value} for label, value in sorted(totals.items())]


def timeseries(db: Session, year: int | None = None, currency: str = "CAD"):
    q = (
        select(
            func.to_char(Transaction.transaction_date, "YYYY-MM").label("month"),
            func.coalesce(func.sum(case((Transaction.transaction_type == TransactionType.contribution, Transaction.amount), else_=0)), 0).label("contributions"),
            func.coalesce(
                func.sum(
                    case(
                        (Transaction.transaction_type.in_([TransactionType.investment_buy, TransactionType.investment_sell]), Transaction.amount),
                        else_=0,
                    )
                ),
                0,
            ).label("investments"),
        )
        .group_by("month")
        .order_by("month")
    )
    if year:
        q = q.where(func.extract("year", Transaction.transaction_date) == year)
    q = q.where(Transaction.currency == currency)
    rows = db.execute(q).all()
    return [{"month": r.month, "contributions": float(r.contributions or 0), "investments": float(r.investments or 0)} for r in rows]
