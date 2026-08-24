import json
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.encoders import jsonable_encoder

from app.db.session import Base
from app.models.models import (
    Account,
    Category,
    ContributionLimit,
    HoldingSnapshot,
    Import,
    ImportRow,
    ImportStatus,
    ImportType,
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
            contribution_id=transaction.id,
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
        imp = Import(import_type=ImportType.contributions, source_filename="backup.xlsx", status=ImportStatus.parsed)
        price = MarketPrice(instrument_id=instrument.id, price=42, currency="CAD", priced_at=date(2026, 6, 4))
        db.add_all([limit, transaction, investment, reinvestment, snapshot, imp, price])
        db.flush()
        investment.contribution_id = transaction.id

        import_row = ImportRow(import_id=imp.id, row_number=1, payload_json=json.dumps({"amount": 500}), error=None)
        funding = TransactionFunding(transaction_id=investment.id, contribution_id=transaction.id, amount=100)
        db.add_all([import_row, funding])
        db.commit()

        exported = export_all_data(db)

        assert set(exported) == set(Base.metadata.tables)
        assert all(set(exported[table.name][0]) == set(table.c.keys()) for table in Base.metadata.tables.values())
        assert exported["accounts"][0]["name"] == "TFSA"
        assert exported["platforms"][0]["canonical_name"] == "Wealthsimple"
        assert exported["platform_aliases"][0]["alias"] == "ws"
        assert exported["categories"][0]["precise"] == "All Equity"
        assert exported["instruments"][0]["symbol"] == "XEQT"
        assert exported["contribution_limits"][0]["tax_year"] == "2026"
        assert exported["transactions"][0]["notes"] == "manual backup test"
        assert next(row for row in exported["transactions"] if row["id"] == investment.id)["contribution_id"] == transaction.id
        assert {row["transaction_type"] for row in exported["transactions"]} >= {TransactionType.dividend_reinvestment}
        assert exported["transaction_fundings"][0]["amount"] == 100
        assert exported["holdings_snapshots"][0]["market_value"] == 1200
        assert exported["imports"][0]["source_filename"] == "backup.xlsx"
        assert exported["import_rows"][0]["payload_json"] == "{\"amount\": 500}"


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
        imp = Import(id=1, import_type=ImportType.contributions, source_filename="backup.xlsx", status=ImportStatus.parsed)
        source_db.add_all([account, platform, category, instrument, alias, limit, imp])
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
            contribution_id=contribution.id,
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
        import_row = ImportRow(id=1, import_id=imp.id, row_number=1, payload_json='{"amount": 500}', error=None)
        source_db.add_all([snapshot, funding, import_row])
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
