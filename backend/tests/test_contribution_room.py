from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.models import Account, ContributionLimit, Transaction, TransactionType
from app.services.finance import get_contribution_room, list_contribution_limits


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

        limits = [row for row in list_contribution_limits(db) if row["account"] == "TFSA"]
        limit_2026 = next(row for row in limits if row["tax_year"] == "2026")
        assert limit_2026["unused_room"] == 5500
        assert limit_2026["total_room"] == 12500
