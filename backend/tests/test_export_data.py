import json
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

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
    Platform,
    PlatformAlias,
    Transaction,
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
        snapshot = HoldingSnapshot(
            snapshot_date=date(2026, 6, 1),
            account_id=account.id,
            platform_id=platform.id,
            instrument_id=instrument.id,
            category_id=category.id,
            market_value=1200,
        )
        imp = Import(import_type=ImportType.contributions, source_filename="backup.xlsx", status=ImportStatus.parsed)
        db.add_all([limit, transaction, snapshot, imp])
        db.flush()

        import_row = ImportRow(import_id=imp.id, row_number=1, payload_json=json.dumps({"amount": 500}), error=None)
        db.add(import_row)
        db.commit()

        exported = export_all_data(db)

        assert exported["accounts"][0]["name"] == "TFSA"
        assert exported["platforms"][0]["canonical_name"] == "Wealthsimple"
        assert exported["platform_aliases"][0]["alias"] == "ws"
        assert exported["categories"][0]["precise"] == "All Equity"
        assert exported["instruments"][0]["symbol"] == "XEQT"
        assert exported["contribution_limits"][0]["tax_year"] == "2026"
        assert exported["transactions"][0]["notes"] == "manual backup test"
        assert exported["holding_snapshots"][0]["market_value"] == 1200
        assert exported["imports"][0]["source_filename"] == "backup.xlsx"
        assert exported["import_rows"][0]["payload_json"] == "{\"amount\": 500}"


def test_restore_replaces_existing_data():
    source_engine = create_engine("sqlite:///:memory:", future=True)
    SourceSession = sessionmaker(bind=source_engine, future=True)
    Base.metadata.create_all(source_engine)

    with SourceSession() as source_db:
        account = Account(id=1, name="TFSA")
        platform = Platform(id=1, canonical_name="Wealthsimple")
        instrument = Instrument(id=1, symbol="XEQT", name="iShares Core Equity ETF")
        source_db.add_all([account, platform, instrument])
        source_db.flush()
        source_db.add(
            Transaction(
                id=1,
                transaction_type=TransactionType.contribution,
                transaction_date=date(2026, 6, 1),
                account_id=account.id,
                platform_id=platform.id,
                instrument_id=instrument.id,
                amount=500,
                notes="restored value",
            )
        )
        source_db.commit()
        payload = {"data": export_all_data(source_db)}

    target_engine = create_engine("sqlite:///:memory:", future=True)
    TargetSession = sessionmaker(bind=target_engine, future=True)
    Base.metadata.create_all(target_engine)

    with TargetSession() as target_db:
        target_db.add(Account(name="RRSP"))
        target_db.commit()

        restore_all_data(target_db, payload)

        accounts = target_db.query(Account).all()
        transactions = target_db.query(Transaction).all()

        assert len(accounts) == 1
        assert accounts[0].name == "TFSA"
        assert len(transactions) == 1
        assert transactions[0].notes == "restored value"
