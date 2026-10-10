import json
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.encoders import jsonable_encoder

from app.db.session import Base
from app.models.models import (
    Account,
    AuditLog,
    Category,
    ContributionLimit,
    HoldingSnapshot,
    PortfolioSnapshot,
    Instrument,
    MarketPrice,
    Platform,
    PlatformAlias,
    Transaction,
    TransactionFunding,
    TransactionType,
)
from app.services.finance import export_all_data, restore_all_data


def test_export_includes_persisted_records():
    engine = create_engine("sqlite:///:memory:", future=True)
    Session = sessionmaker(bind=engine, future=True)
    Base.metadata.create_all(engine)

    with Session() as db:
        account = Account(name="TFSA")
        platform = Platform(canonical_name="Wealthsimple")
        db.add_all([account, platform])
        db.flush()

        alias = PlatformAlias(alias="ws", platform_id=platform.id)
        category = Category(broad="All Equity", precise="All Equity")
        instrument = Instrument(symbol="XEQT", name="iShares Core Equity ETF")
        db.add_all([alias, category, instrument])
        db.flush()

        instrument.category_id = category.id

        limit = ContributionLimit(account_id=account.id, tax_year="2026", new_room=7000)
        transaction = Transaction(
            transaction_type=TransactionType.contribution,
            transaction_date=date(2026, 6, 1),
            account_id=account.id,
            platform_id=platform.id,
            instrument_id=instrument.id,
            amount=500,
            notes="manual backup test",
        )
        investment = Transaction(
            transaction_type=TransactionType.investment_buy,
            transaction_date=date(2026, 6, 2),
            account_id=account.id,
            platform_id=platform.id,
            instrument_id=instrument.id,
            amount=100,
            quantity=1,
        )
        reinvestment = Transaction(
            transaction_type=TransactionType.dividend_reinvestment,
            transaction_date=date(2026, 6, 3),
            account_id=account.id,
            platform_id=platform.id,
            instrument_id=instrument.id,
            amount=5,
            quantity=0.1,
        )
        snapshot = HoldingSnapshot(
            snapshot_date=date(2026, 6, 1),
            account_id=account.id,
            platform_id=platform.id,
            instrument_id=instrument.id,
            category_id=category.id,
            market_value=1200,
        )
        price = MarketPrice(instrument_id=instrument.id, price=42, currency="CAD", priced_at=date(2026, 6, 4))
        db.add_all([limit, transaction, investment, reinvestment, snapshot, price])
        db.flush()

        funding = TransactionFunding(transaction_id=investment.id, contribution_id=transaction.id, amount=100)
        audit = AuditLog(operation="create", table_name="transactions", row_id="1")
        portfolio_snapshot = PortfolioSnapshot(snapshot_date=date(2026, 1, 2), account_id=account.id, book_value=100, market_value=110)
        db.add_all([funding, audit, portfolio_snapshot])
        db.commit()

        exported = export_all_data(db)

        exported_tables = {name for name in Base.metadata.tables if name != "audit_logs"}
        assert set(exported) == exported_tables
        assert "audit_logs" not in exported
        assert all(set(exported[table.name][0]) == set(table.c.keys()) for table in Base.metadata.tables.values() if table.name != "audit_logs")
        assert exported["accounts"][0]["name"] == "TFSA"
        assert exported["platforms"][0]["canonical_name"] == "Wealthsimple"
        assert exported["platform_aliases"][0]["alias"] == "ws"
        assert exported["categories"][0]["precise"] == "All Equity"
        assert exported["instruments"][0]["symbol"] == "XEQT"
        assert exported["contribution_limits"][0]["tax_year"] == "2026"
        assert exported["transactions"][0]["notes"] == "manual backup test"
        assert {row["transaction_type"] for row in exported["transactions"]} >= {TransactionType.dividend_reinvestment}
        assert exported["transaction_fundings"][0]["amount"] == 100
        assert exported["holdings_snapshots"][0]["market_value"] == 1200


def test_restore_replaces_existing_data():
    source_engine = create_engine("sqlite:///:memory:", future=True)
    SourceSession = sessionmaker(bind=source_engine, future=True)
    Base.metadata.create_all(source_engine)

    with SourceSession() as source_db:
        account = Account(id=1, name="TFSA")
        platform = Platform(id=1, canonical_name="Wealthsimple")
        category = Category(id=1, broad="All Equity", precise="All Equity")
        instrument = Instrument(id=1, symbol="XEQT", name="iShares Core Equity ETF", category_id=category.id)
        alias = PlatformAlias(id=1, alias="ws", platform_id=platform.id)
        limit = ContributionLimit(id=1, account_id=account.id, tax_year="2026", new_room=7000)
        source_db.add_all([account, platform, category, instrument, alias, limit])
        source_db.flush()
        contribution = Transaction(
                id=1,
                transaction_type=TransactionType.contribution,
                transaction_date=date(2026, 6, 1),
                account_id=account.id,
                platform_id=platform.id,
                instrument_id=instrument.id,
                amount=500,
                notes="restored value",
        )
        investment = Transaction(
            id=2,
            transaction_type=TransactionType.investment_buy,
            transaction_date=date(2026, 6, 2),
            account_id=account.id,
            platform_id=platform.id,
            instrument_id=instrument.id,
            amount=100,
            quantity=1,
        )
        reinvestment = Transaction(
            id=3,
            transaction_type=TransactionType.dividend_reinvestment,
            transaction_date=date(2026, 6, 3),
            account_id=account.id,
            platform_id=platform.id,
            instrument_id=instrument.id,
            amount=5,
            quantity=0.1,
        )
        source_db.add_all([contribution, investment, reinvestment])
        source_db.flush()
        snapshot = HoldingSnapshot(
            id=1,
            snapshot_date=date(2026, 6, 3),
            account_id=account.id,
            platform_id=platform.id,
            instrument_id=instrument.id,
            category_id=category.id,
            market_value=1200,
        )
        funding = TransactionFunding(id=1, transaction_id=investment.id, contribution_id=contribution.id, amount=100)
        source_db.add_all([snapshot, funding])
        source_db.commit()
        source_data = export_all_data(source_db)
        payload = json.loads(json.dumps(jsonable_encoder({"data": source_data})))
        payload["data"]["holding_snapshots"] = payload["data"].pop("holdings_snapshots")

    target_engine = create_engine("sqlite:///:memory:", future=True)
    TargetSession = sessionmaker(bind=target_engine, future=True)
    Base.metadata.create_all(target_engine)

    with TargetSession() as target_db:
        target_db.add(Account(name="RRSP"))
        target_db.commit()

        restore_all_data(target_db, payload)

        assert export_all_data(target_db) == source_data
        audit = target_db.query(AuditLog).one()
        assert audit.operation == "restore"
        assert audit.table_name == "all"
