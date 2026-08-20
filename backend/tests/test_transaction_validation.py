import pytest

from app.models.models import TransactionType
from app.schemas.schemas import AccountTransactionCreate, ContributionCreate, TransactionCreate


def test_investment_requires_symbol():
    with pytest.raises(ValueError):
        TransactionCreate(
            transaction_type=TransactionType.investment_buy,
            transaction_date="2026-01-01",
            amount=100,
        )


def test_transfer_requires_notes():
    with pytest.raises(ValueError):
        TransactionCreate(
            transaction_type=TransactionType.transfer,
            transaction_date="2026-01-01",
            amount=100,
        )


def test_contribution_valid():
    txn = TransactionCreate(
        transaction_type=TransactionType.contribution,
        transaction_date="2026-01-01",
        amount=250,
        account_name="TFSA",
    )
    assert txn.amount == 250


def test_domain_contribution_valid():
    contribution = ContributionCreate(
        transaction_date="2026-01-01",
        amount=250,
        account_name="TFSA",
    )
    assert contribution.amount == 250


def test_account_transaction_rejects_contribution_type():
    with pytest.raises(ValueError):
        AccountTransactionCreate(
            transaction_type=TransactionType.contribution,
            transaction_date="2026-01-01",
            account_name="TFSA",
            platform_name="Wealthsimple",
            amount=100,
        )


def test_account_transaction_only_requires_core_fields():
    txn = AccountTransactionCreate(
        transaction_type=TransactionType.investment_buy,
        transaction_date="2026-01-01",
        account_name="TFSA",
        platform_name="Wealthsimple",
        amount=100,
    )
    assert txn.symbol is None
    assert txn.precise_category is None


def test_account_transaction_requires_account_and_platform():
    with pytest.raises(ValueError):
        AccountTransactionCreate(
            transaction_type=TransactionType.investment_buy,
            transaction_date="2026-01-01",
            account_name="",
            platform_name="Wealthsimple",
            amount=100,
        )
    with pytest.raises(ValueError):
        AccountTransactionCreate(
            transaction_type=TransactionType.investment_buy,
            transaction_date="2026-01-01",
            account_name="TFSA",
            platform_name="",
            amount=100,
        )
