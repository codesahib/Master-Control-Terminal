from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.models import Account, Platform, SyncState
from app.services.sync import recommend_sync_action, sync_data_from_external_database, sync_data_to_external_database, sync_status
from app.services.sync_state import mark_database_write
from datetime import datetime


def test_sync_data_to_external_database_replaces_external_data(tmp_path):
    source_engine = create_engine("sqlite:///:memory:", future=True)
    SourceSession = sessionmaker(bind=source_engine, future=True)
    Base.metadata.create_all(source_engine)

    target_path = tmp_path / "external.db"
    target_url = f"sqlite:///{target_path}"
    target_engine = create_engine(target_url, future=True)
    TargetSession = sessionmaker(bind=target_engine, future=True)
    Base.metadata.create_all(target_engine)

    with TargetSession() as target_db:
        target_db.add(Account(name="OLD"))
        target_db.commit()

    with SourceSession() as source_db:
        source_db.add_all([Account(name="TFSA"), Platform(canonical_name="Wealthsimple")])
        mark_database_write(source_db)
        source_db.commit()

        result = sync_data_to_external_database(source_db, target_url)

    with TargetSession() as target_db:
        accounts = [account.name for account in target_db.query(Account).order_by(Account.name)]
        platforms = [platform.canonical_name for platform in target_db.query(Platform)]

    target_engine.dispose()

    assert result["status"] == "ok"
    assert result["direction"] == "push"
    assert result["rows_synced"] == 2
    assert accounts == ["TFSA"]
    assert platforms == ["Wealthsimple"]


def test_sync_data_from_external_database_replaces_local_data(tmp_path):
    local_engine = create_engine("sqlite:///:memory:", future=True)
    LocalSession = sessionmaker(bind=local_engine, future=True)
    Base.metadata.create_all(local_engine)

    external_path = tmp_path / "external.db"
    external_url = f"sqlite:///{external_path}"
    external_engine = create_engine(external_url, future=True)
    ExternalSession = sessionmaker(bind=external_engine, future=True)
    Base.metadata.create_all(external_engine)

    with LocalSession() as local_db:
        local_db.add(Account(name="OLD"))
        mark_database_write(local_db)
        local_db.commit()

    with ExternalSession() as external_db:
        external_db.add_all([Account(name="FHSA"), Platform(canonical_name="Questrade")])
        mark_database_write(external_db)
        external_db.commit()

    with LocalSession() as local_db:
        result = sync_data_from_external_database(local_db, external_url)

    with LocalSession() as local_db:
        accounts = [account.name for account in local_db.query(Account).order_by(Account.name)]
        platforms = [platform.canonical_name for platform in local_db.query(Platform)]
        state = local_db.get(SyncState, 1)

    external_engine.dispose()

    assert result["status"] == "ok"
    assert result["direction"] == "pull"
    assert result["rows_synced"] == 2
    assert accounts == ["FHSA"]
    assert platforms == ["Questrade"]
    assert state.last_pull_at == result["synced_at"]


def test_sync_status_recommends_push_when_local_changed(tmp_path):
    local_engine = create_engine("sqlite:///:memory:", future=True)
    LocalSession = sessionmaker(bind=local_engine, future=True)
    Base.metadata.create_all(local_engine)

    external_path = tmp_path / "external.db"
    external_url = f"sqlite:///{external_path}"
    external_engine = create_engine(external_url, future=True)
    Base.metadata.create_all(external_engine)
    external_engine.dispose()

    with LocalSession() as local_db:
        local_db.add(Account(name="TFSA"))
        mark_database_write(local_db)
        local_db.commit()
        status = sync_status(local_db, external_url)

    assert status["external_available"] is True
    assert status["recommended_action"] == "push"
    assert status["local"]["last_write_at"] is not None
    assert status["external"]["last_write_at"] is None


def test_first_run_status_recommends_newer_database():
    older = {"last_write_at": datetime(2026, 1, 1), "last_sync_at": None}
    newer = {"last_write_at": datetime(2026, 1, 2), "last_sync_at": None}

    assert recommend_sync_action(newer, older) == "push"
    assert recommend_sync_action(older, newer) == "pull"
