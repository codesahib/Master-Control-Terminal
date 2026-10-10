import json
from datetime import date

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base, get_db
from app.main import app
from app.models.models import (
    Account,
    AuditLog,
    Category,
    ContributionLimit,
    Instrument,
    Platform,
    PlatformAlias,
    Transaction,
    TransactionFunding,
    TransactionType,
)
from app.schemas.schemas import AccountTransactionCreate, ContributionCreate
from app.services import finance
from app.services.finance import (
    ConflictError,
    create_account_transaction,
    create_contribution,
    delete_transaction,
    get_all_contribution_room,
    get_contribution_room,
    list_contribution_limits,
    seed_contribution_limits,
    seed_reference_data,
    tracked_years,
    update_contribution,
    upsert_contribution_limit,
)

HEADERS = {"X-Requested-With": "master-terminal"}


def make_session():
    engine = create_engine("sqlite:///:memory:", future=True, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)


def freeze_today(monkeypatch, frozen: date):
    class FrozenDate(date):
        @classmethod
        def today(cls):
            return frozen

    monkeypatch.setattr(finance, "date", FrozenDate)


def add_accounts(db, *names):
    accounts = [Account(name=name) for name in names]
    db.add_all(accounts)
    db.flush()
    return accounts


def contribution(account, day, amount, kind=TransactionType.contribution):
    return Transaction(transaction_type=kind, transaction_date=day, account_id=account.id, amount=amount)


def room_by_year(db, account_name):
    return {row["tax_year"]: row for row in list_contribution_limits(db) if row["account"] == account_name}


def test_tracked_years_follow_data_and_the_current_year():
    Session = make_session()
    with Session() as db:
        assert tracked_years(db, today=date(2027, 1, 1)) == [2027]
        (tfsa,) = add_accounts(db, "TFSA")
        db.add(contribution(tfsa, date(2023, 5, 1), 100))
        db.commit()
        assert tracked_years(db, today=date(2027, 1, 1)) == [2023, 2024, 2025, 2026, 2027]
        db.add(contribution(tfsa, date(2019, 5, 1), 100))
        db.commit()
        assert tracked_years(db, today=date(2026, 6, 1))[0] == 2021


def test_seeding_adds_the_new_year_and_checks_each_row(monkeypatch):
    Session = make_session()
    with Session() as db:
        rrsp, tfsa, fhsa = add_accounts(db, "RRSP", "TFSA", "FHSA")
        db.add(ContributionLimit(account_id=tfsa.id, tax_year="2026", new_room=7500))
        db.commit()

        seed_contribution_limits(db, today=date(2027, 1, 1))
        seed_contribution_limits(db, today=date(2027, 1, 1))

        rows = {(row.account_id, row.tax_year): float(row.new_room) for row in db.scalars(select(ContributionLimit))}
        assert len(rows) == 12
        assert rows[(tfsa.id, "2026")] == 7500
        assert rows[(tfsa.id, "2027")] == 7500
        assert rows[(fhsa.id, "2027")] == 8000
        assert rows[(rrsp.id, "2027")] == 0


def test_reference_seeding_is_not_skipped_by_an_extra_account():
    Session = make_session()
    with Session() as db:
        add_accounts(db, "RRSP", "TFSA", "FHSA", "LIRA")
        db.commit()
        seed_reference_data(db)
        assert db.scalar(select(func.count(Platform.id))) == 5
        assert db.scalar(select(func.count(PlatformAlias.id))) == 10
        assert db.scalar(select(func.count(Category.id))) == sum(len(options) for options in finance.CATEGORY_OPTIONS.values())


def test_room_rolls_into_2027_on_january_first(monkeypatch):
    Session = make_session()
    with Session() as db:
        (rrsp,) = add_accounts(db, "RRSP")
        db.add(ContributionLimit(account_id=rrsp.id, tax_year="2026", new_room=10000))
        db.add_all([
            contribution(rrsp, date(2026, 6, 1), 2000),
            contribution(rrsp, date(2027, 2, 15), 1000),
            contribution(rrsp, date(2027, 4, 1), 3000),
        ])
        db.commit()

        freeze_today(monkeypatch, date(2026, 12, 31))
        assert get_contribution_room(db, 2027) == []

        freeze_today(monkeypatch, date(2027, 1, 1))
        assert get_contribution_room(db, 2026)[0]["used"] == 3000
        assert get_contribution_room(db, 2027) == [
            {"account": "RRSP", "tax_year": "2027", "total_room": 7000.0, "used": 3000.0, "remaining": 4000.0}
        ]
        assert get_all_contribution_room(db)[0]["remaining"] == 4000


def test_fhsa_carry_forward_and_lifetime_caps(monkeypatch):
    Session = make_session()
    with Session() as db:
        (fhsa,) = add_accounts(db, "FHSA")
        db.add_all([ContributionLimit(account_id=fhsa.id, tax_year=str(year), new_room=8000) for year in range(2023, 2029)])
        db.commit()
        freeze_today(monkeypatch, date(2026, 6, 1))
        rows = room_by_year(db, "FHSA")
        assert rows["2023"]["total_room"] == 8000
        assert rows["2024"]["total_room"] == 16000
        assert rows["2026"]["unused_room"] == 8000
        assert rows["2026"]["total_room"] == 16000

        db.add_all([contribution(fhsa, date(year, 3, 1), 8000) for year in range(2023, 2028)])
        db.commit()
        freeze_today(monkeypatch, date(2028, 6, 1))
        rows = room_by_year(db, "FHSA")
        assert rows["2027"]["total_room"] == 8000
        assert rows["2028"]["total_room"] == 0


def test_tfsa_withdrawals_come_back_next_year(monkeypatch):
    Session = make_session()
    with Session() as db:
        (tfsa,) = add_accounts(db, "TFSA")
        db.add_all([
            ContributionLimit(account_id=tfsa.id, tax_year="2025", new_room=7000),
            ContributionLimit(account_id=tfsa.id, tax_year="2026", new_room=7000),
            contribution(tfsa, date(2025, 2, 1), 7000),
            contribution(tfsa, date(2025, 6, 1), 3000, TransactionType.withdrawal),
        ])
        db.commit()
        freeze_today(monkeypatch, date(2026, 6, 1))
        rows = room_by_year(db, "TFSA")
        assert rows["2025"]["remaining"] == 0
        assert rows["2026"]["unused_room"] == 3000
        assert rows["2026"]["total_room"] == 10000


def test_custom_symbol_never_rewrites_a_priced_instrument():
    Session = make_session()
    with Session() as db:
        add_accounts(db, "RRSP")
        db.add(Instrument(symbol="VFV", provider_symbol="VFV.TO", provider="yfinance", currency="CAD", is_active=True))
        db.commit()
        buy = dict(
            transaction_type=TransactionType.investment_buy,
            transaction_date=date(2026, 1, 1),
            account_name="RRSP",
            platform_name="Wealthsimple",
            symbol="VFV",
            is_custom_symbol=True,
            amount=100,
            quantity=1,
        )
        first = create_account_transaction(db, AccountTransactionCreate(**buy))
        second = create_account_transaction(db, AccountTransactionCreate(**buy))

        priced = db.scalar(select(Instrument).where(Instrument.symbol == "VFV"))
        assert (priced.provider, priced.provider_symbol, priced.currency, priced.is_active) == ("yfinance", "VFV.TO", "CAD", True)
        twin = db.get(Instrument, first.instrument_id)
        assert twin.symbol == "VFV (manual)"
        assert (twin.provider, twin.provider_symbol, twin.is_active) == (None, None, False)
        assert second.instrument_id == twin.id


def test_account_names_are_validated_and_never_created():
    assert ContributionCreate(transaction_date="2026-01-01", account_name=" tfsa ", amount=1).account_name == "TFSA"
    with pytest.raises(ValidationError):
        ContributionCreate(transaction_date="2026-01-01", account_name="RRSP2", amount=1)
    with pytest.raises(ValidationError):
        ContributionCreate(transaction_date="2026-01-01", amount=1)

    Session = make_session()
    with Session() as db:
        add_accounts(db, "TFSA")
        db.commit()
        with pytest.raises(LookupError):
            upsert_contribution_limit(db, "FOO", "2026", 100)
        db.rollback()
        assert db.scalar(select(func.count(Account.id))) == 1


def test_withdrawals_reject_symbol_quantity_and_funding():
    base = dict(transaction_type=TransactionType.withdrawal, transaction_date="2026-01-01", account_name="TFSA", platform_name="Wealthsimple")
    assert AccountTransactionCreate(**base, amount=50).amount == 50
    for extra in ({"amount": 0}, {"amount": 50, "symbol": "VFV"}, {"amount": 50, "quantity": 1}, {"amount": 50, "funding_cash_sources": [{"platform_name": "Wealthsimple", "amount": 50}]}):
        with pytest.raises(ValidationError):
            AccountTransactionCreate(**{**base, **extra})


def test_sell_cannot_exceed_held_units_and_failed_saves_leave_no_orphans():
    Session = make_session()
    with Session() as db:
        add_accounts(db, "TFSA")
        db.commit()
        trade = dict(account_name="TFSA", platform_name="Wealthsimple", symbol="XEQT", currency="CAD")
        create_account_transaction(db, AccountTransactionCreate(transaction_type=TransactionType.investment_buy, transaction_date=date(2026, 2, 1), amount=300, quantity=10, **trade))

        with pytest.raises(ValueError, match="only 10 held"):
            create_account_transaction(db, AccountTransactionCreate(transaction_type=TransactionType.investment_sell, transaction_date=date(2026, 3, 1), amount=360, quantity=12, **trade))
        db.rollback()
        with pytest.raises(ValueError, match="only 0 held"):
            create_account_transaction(db, AccountTransactionCreate(transaction_type=TransactionType.investment_sell, transaction_date=date(2026, 1, 1), amount=30, quantity=1, **trade))
        db.rollback()
        sold = create_account_transaction(db, AccountTransactionCreate(transaction_type=TransactionType.investment_sell, transaction_date=date(2026, 3, 1), amount=300, quantity=10, **trade))
        assert sold.id

        with pytest.raises(ValueError):
            create_account_transaction(
                db,
                AccountTransactionCreate(
                    transaction_type=TransactionType.investment_sell,
                    transaction_date=date(2026, 3, 1),
                    account_name="TFSA",
                    platform_name="Brand New Broker",
                    symbol="NEWSYM",
                    amount=10,
                    quantity=1,
                ),
            )
        db.rollback()
        assert db.scalar(select(Platform).where(Platform.canonical_name == "Brand New Broker")) is None
        assert db.scalar(select(Instrument).where(Instrument.symbol == "NEWSYM")) is None


def test_funding_sources_cannot_shrink_below_what_they_fund_and_delete_rules():
    Session = make_session()
    with Session() as db:
        add_accounts(db, "TFSA", "RRSP")
        db.commit()
        source = create_contribution(db, ContributionCreate(transaction_date=date(2026, 1, 1), account_name="TFSA", platform_name="Wealthsimple", amount=500))
        buy = create_account_transaction(
            db,
            AccountTransactionCreate(
                transaction_type=TransactionType.investment_buy,
                transaction_date=date(2026, 1, 2),
                account_name="TFSA",
                platform_name="Wealthsimple",
                symbol="XEQT",
                amount=2.675,
                quantity=1,
                funding_contributions=[{"contribution_id": source.id, "amount": 2.68}],
            ),
        )
        edit = dict(transaction_date=date(2026, 1, 1), platform_name="Wealthsimple")
        with pytest.raises(ConflictError):
            update_contribution(db, source.id, ContributionCreate(account_name="TFSA", amount=2, **edit))
        db.rollback()
        with pytest.raises(ConflictError):
            update_contribution(db, source.id, ContributionCreate(account_name="RRSP", amount=500, **edit))
        db.rollback()
        assert update_contribution(db, source.id, ContributionCreate(account_name="TFSA", amount=3, **edit)).amount == 3

        with pytest.raises(ConflictError):
            delete_transaction(db, source.id, contribution=True)
        db.rollback()
        with pytest.raises(LookupError):
            delete_transaction(db, buy.id, contribution=True)
        db.rollback()

        delete_transaction(db, buy.id, contribution=False)
        assert db.get(Transaction, buy.id) is None
        assert db.scalar(select(func.count(TransactionFunding.id))) == 0
        audit = db.scalar(select(AuditLog).where(AuditLog.operation == "delete"))
        assert json.loads(audit.before_json)["id"] == buy.id
        delete_transaction(db, source.id, contribution=True)
        assert db.get(Transaction, source.id) is None


def test_routes_status_codes_page_size_and_backup_version():
    Session = make_session()

    def override_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    with Session() as db:
        add_accounts(db, "TFSA")
        db.add_all([Platform(canonical_name="Wealthsimple")])
        db.commit()

    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app)
        assert client.post("/transactions", json={}, headers=HEADERS).status_code == 405

        created = [
            client.post("/contributions", json={"transaction_date": f"2026-01-0{day}", "account_name": "tfsa", "platform_name": "Wealthsimple", "amount": 100}, headers=HEADERS)
            for day in range(1, 4)
        ]
        assert all(response.status_code == 200 for response in created)
        page = client.get("/transactions", params={"page_size": 2}, headers=HEADERS).json()
        assert (page["page_size"], page["total"], len(page["items"])) == (2, 3, 2)
        assert client.get("/transactions", params={"page_size": 101}, headers=HEADERS).status_code == 422

        bad_account = {"transaction_type": "withdrawal", "transaction_date": "2026-02-01", "account_name": "XYZ", "platform_name": "Wealthsimple", "amount": 10}
        assert client.post("/account-transactions", json=bad_account, headers=HEADERS).status_code == 422
        withdrawal = client.post("/account-transactions", json={**bad_account, "account_name": "TFSA"}, headers=HEADERS)
        assert withdrawal.status_code == 200
        assert client.delete(f"/account-transactions/{withdrawal.json()['id']}", headers=HEADERS).status_code == 204

        contribution_id = created[0].json()["id"]
        assert client.delete(f"/account-transactions/{contribution_id}", headers=HEADERS).status_code == 404
        assert client.delete(f"/contributions/{contribution_id}", headers=HEADERS).status_code == 204
        assert client.delete(f"/contributions/{contribution_id}", headers=HEADERS).status_code == 404

        assert client.put("/contribution-limits/FOO/2026", json={"new_room": 1}, headers=HEADERS).status_code == 404
        assert client.put("/contribution-limits/TFSA/20x6", json={"new_room": 1}, headers=HEADERS).status_code == 422
        assert client.put("/contribution-limits/TFSA/2026", json={"new_room": 7000}, headers=HEADERS).json()["total_room"] == 7000

        backup = json.dumps({"meta": {"format": finance.BACKUP_FORMAT, "version": 99}, "data": {}})
        response = client.post("/import-backup", files={"file": ("backup.json", backup, "application/json")}, headers=HEADERS)
        assert response.status_code == 400
        assert "version 99" in response.json()["detail"]

        assert client.get("/years", headers=HEADERS).json()[-1] == date.today().year
    finally:
        app.dependency_overrides.clear()
