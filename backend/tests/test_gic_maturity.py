from datetime import date

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.models import Account, Instrument, Platform, Transaction, TransactionFunding, TransactionType
from app.schemas.schemas import AccountTransactionCreate, ContributionCreate, GicMaturityCreate
from app.services.finance import create_account_transaction, create_contribution, list_available_contributions, mature_gic
from app.services.portfolio import _portfolio_pl_rows


def _rows(db):
    return {(r["record_type"], r["symbol"]): r for r in _portfolio_pl_rows(db)}


def _tx(db, transaction_type, day, amount, **extra):
    return create_account_transaction(
        db,
        AccountTransactionCreate(
            transaction_type=transaction_type, transaction_date=day, account_name="FHSA", platform_name="EQ Bank", amount=amount, **extra
        ),
    )


def test_gic_renews_moves_to_cash_and_rebuys_any_amount():
    engine = create_engine("sqlite:///:memory:", future=True)
    Session = sessionmaker(bind=engine, future=True)
    Base.metadata.create_all(engine)

    with Session() as db:
        gic = Instrument(symbol="GIC", asset_type="gic", is_active=False)
        fund = Instrument(symbol="FUND", asset_type="manual", is_active=False)
        db.add_all([Account(name="FHSA"), Platform(canonical_name="EQ Bank"), gic, fund])
        db.commit()
        contribution = create_contribution(
            db, ContributionCreate(transaction_date=date(2025, 12, 23), account_name="FHSA", platform_name="EQ Bank", amount=3000)
        )
        _tx(db, TransactionType.investment_buy, date(2025, 12, 23), 3000, instrument_id=gic.id,
            funding_contributions=[{"contribution_id": contribution.id, "amount": 3000}])
        maturity = GicMaturityCreate(
            transaction_date=date(2026, 3, 23), account_name="FHSA", platform_name="EQ Bank", instrument_id=gic.id, interest=19.23
        )

        # Renew: interest is income, then joins the principal; GIC is valued at book.
        interest, buy = mature_gic(db, maturity)
        assert interest.transaction_type == TransactionType.dividend_interest and float(interest.amount) == 19.23
        assert buy.transaction_type == TransactionType.investment_buy and float(buy.amount) == 19.23
        funding = db.scalars(select(TransactionFunding).where(TransactionFunding.transaction_id == buy.id)).one()
        assert (funding.contribution_id, float(funding.amount)) == (interest.id, 19.23)
        assert list_available_contributions(db, "FHSA") == []
        row = _rows(db)[("holding", "GIC")]
        assert (row["book_value"], row["market_value"], row["unrealized_pl"], row["price_status"]) == (3019.23, 3019.23, 0.0, "ok")

        # Move to cash: the GIC closes; principal plus interest becomes platform cash.
        _, sell = mature_gic(db, maturity.model_copy(update={"transaction_date": date(2026, 6, 23), "interest": 19.79, "reinvest": False}))
        assert sell.transaction_type == TransactionType.investment_sell and float(sell.amount) == 3019.23
        rows = _rows(db)
        assert ("holding", "GIC") not in rows
        assert rows[("cash", "Cash")]["book_value"] == 3039.02

        # Savings interest while it sits in cash, then a new GIC for any amount.
        _tx(db, TransactionType.dividend_interest, date(2026, 7, 1), 1.00)
        _tx(db, TransactionType.investment_buy, date(2026, 8, 21), 3000, instrument_id=gic.id)
        rows = _rows(db)
        assert rows[("holding", "GIC")]["market_value"] == 3000
        assert rows[("cash", "Cash")]["book_value"] == 40.02

        count = db.scalar(select(func.count()).select_from(Transaction))
        with pytest.raises(ValueError, match="not a GIC"):
            mature_gic(db, maturity.model_copy(update={"instrument_id": fund.id}))
        db.rollback()
        with pytest.raises(ValueError, match="no GIC holding"):
            mature_gic(db, maturity.model_copy(update={"platform_name": "Questrade"}))
        db.rollback()
        assert db.scalar(select(func.count()).select_from(Transaction)) == count
