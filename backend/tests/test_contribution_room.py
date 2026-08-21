from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.models import Account, ContributionLimit, Transaction, TransactionType
from app.services.finance import get_all_contribution_room, get_contribution_room, get_contribution_used, list_contribution_limits, list_contributions


def test_contribution_room_calculation():
    engine = create_engine("sqlite:///:memory:", future=True)
    Session = sessionmaker(bind=engine, future=True)
    Base.metadata.create_all(engine)

    with Session() as db:
        acc = Account(name="TFSA")
        db.add(acc)
        db.flush()
        db.add(ContributionLimit(account_id=acc.id, tax_year="2025", new_room=7000))
        db.add(ContributionLimit(account_id=acc.id, tax_year="2026", new_room=7000))
        db.add(
            Transaction(
                transaction_type=TransactionType.contribution,
                transaction_date=date(2025, 3, 1),
                account_id=acc.id,
                amount=1500,
            )
        )
        db.commit()

        room = get_contribution_room(db, 2026)
        assert len(room) == 1
        assert room[0]["total_room"] == 12500
        assert room[0]["used"] == 0
        assert room[0]["remaining"] == 12500

        all_room = get_all_contribution_room(db)[0]
        assert all_room["total_room"] == 14000
        assert all_room["used"] == 1500
        assert all_room["remaining"] == 12500

        limits = [row for row in list_contribution_limits(db) if row["account"] == "TFSA"]
        assert [row["tax_year"] for row in limits] == ["2021", "2022", "2023", "2024", "2025", "2026"]
        limit_2026 = next(row for row in limits if row["tax_year"] == "2026")
        assert limit_2026["unused_room"] == 5500
        assert limit_2026["total_room"] == 12500


def test_rrsp_contributions_use_the_cra_contribution_period():
    engine = create_engine("sqlite:///:memory:", future=True)
    Session = sessionmaker(bind=engine, future=True)
    Base.metadata.create_all(engine)

    with Session() as db:
        account = Account(name="RRSP")
        db.add(account)
        db.flush()
        db.add_all(
            [
                Transaction(
                    transaction_type=TransactionType.contribution,
                    transaction_date=date(2026, 2, 28),
                    account_id=account.id,
                    amount=1000,
                ),
                Transaction(
                    transaction_type=TransactionType.contribution,
                    transaction_date=date(2026, 3, 1),
                    account_id=account.id,
                    amount=2000,
                ),
                Transaction(
                    transaction_type=TransactionType.contribution,
                    transaction_date=date(2026, 3, 2),
                    account_id=account.id,
                    amount=3000,
                ),
                Transaction(
                    transaction_type=TransactionType.contribution,
                    transaction_date=date(2026, 3, 3),
                    account_id=account.id,
                    amount=4000,
                ),
            ]
        )
        db.commit()

        assert get_contribution_used(db, account.id, 2025) == 6000
        assert get_contribution_used(db, account.id, 2026) == 4000
        assert [row[0].transaction_date for row in list_contributions(db, account="RRSP", year=2025)] == [date(2026, 3, 2), date(2026, 3, 1), date(2026, 2, 28)]
        assert [row[0].transaction_date for row in list_contributions(db, account="RRSP", year=2026)] == [date(2026, 3, 3)]


def test_rrsp_contribution_period_handles_leap_years():
    engine = create_engine("sqlite:///:memory:", future=True)
    Session = sessionmaker(bind=engine, future=True)
    Base.metadata.create_all(engine)

    with Session() as db:
        account = Account(name="RRSP")
        db.add(account)
        db.flush()
        db.add_all(
            [
                Transaction(
                    transaction_type=TransactionType.contribution,
                    transaction_date=date(2024, 2, 29),
                    account_id=account.id,
                    amount=1000,
                ),
                Transaction(
                    transaction_type=TransactionType.contribution,
                    transaction_date=date(2024, 3, 1),
                    account_id=account.id,
                    amount=2000,
                ),
            ]
        )
        db.commit()

        assert get_contribution_used(db, account.id, 2023) == 1000
        assert get_contribution_used(db, account.id, 2024) == 2000
