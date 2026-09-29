from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import Base
from app.services.finance import export_all_data, restore_all_data
from app.services.sync_state import (
    create_sync_state_table,
    get_or_create_sync_state,
    record_sync_failure,
    record_sync_success,
    utc_now,
)


def _external_session(external_database_url: str):
    engine = create_engine(external_database_url, future=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return engine, SessionLocal


def _state_payload(db: Session) -> dict:
    state = get_or_create_sync_state(db)
    return {
        "database_id": state.database_id,
        "last_write_at": state.last_write_at,
        "last_push_at": state.last_push_at,
        "last_pull_at": state.last_pull_at,
        "last_sync_at": state.last_sync_at,
        "last_sync_direction": state.last_sync_direction,
        "last_sync_status": state.last_sync_status,
        "last_sync_error": state.last_sync_error,
    }


def _is_changed_since(state: dict | None, synced_at: datetime | None) -> bool:
    if not state or not state.get("last_write_at"):
        return False
    if not synced_at:
        return True
    return state["last_write_at"] > synced_at


def recommend_sync_action(local_state: dict, external_state: dict | None) -> str:
    if not external_state:
        return "unavailable"
    last_sync_at = max(
        [value for value in [local_state.get("last_sync_at"), external_state.get("last_sync_at")] if value],
        default=None,
    )
    if not last_sync_at:
        local_write_at = local_state.get("last_write_at")
        external_write_at = external_state.get("last_write_at")
        if local_write_at and external_write_at:
            if local_write_at == external_write_at:
                return "in_sync"
            return "push" if local_write_at > external_write_at else "pull"
        if local_write_at:
            return "push"
        if external_write_at:
            return "pull"
        return "in_sync"
    local_changed = _is_changed_since(local_state, last_sync_at)
    external_changed = _is_changed_since(external_state, last_sync_at)
    if local_changed and external_changed:
        return "conflict"
    if local_changed:
        return "push"
    if external_changed:
        return "pull"
    return "in_sync"


def sync_status(source_db: Session, external_database_url: str | None) -> dict:
    local_state = _state_payload(source_db)
    source_db.commit()
    if not external_database_url:
        return {
            "external_available": False,
            "recommended_action": "unavailable",
            "local": local_state,
            "external": None,
            "error": "External database is not configured",
        }

    engine, SessionLocal = _external_session(external_database_url)
    try:
        create_sync_state_table(engine)
        with SessionLocal() as external_db:
            external_state = _state_payload(external_db)
            external_db.commit()
    except Exception as exc:
        return {
            "external_available": False,
            "recommended_action": "unavailable",
            "local": local_state,
            "external": None,
            "error": str(exc),
        }
    finally:
        engine.dispose()

    return {
        "external_available": True,
        "recommended_action": recommend_sync_action(local_state, external_state),
        "local": local_state,
        "external": external_state,
        "error": None,
    }


def sync_data_to_external_database(source_db: Session, external_database_url: str) -> dict:
    data = export_all_data(source_db)
    rows_synced = sum(len(rows) for rows in data.values())
    synced_at = utc_now()
    engine, SessionLocal = _external_session(external_database_url)

    try:
        Base.metadata.create_all(engine)
        with SessionLocal() as target_db:
            restore_all_data(target_db, {"data": data})
            target_state = record_sync_success(target_db, "push", synced_at)
            target_state.last_write_at = synced_at
            target_db.commit()
        record_sync_success(source_db, "push", synced_at)
        source_db.commit()
    except Exception as exc:
        record_sync_failure(source_db, "push", str(exc))
        source_db.commit()
        raise
    finally:
        engine.dispose()

    return {
        "status": "ok",
        "direction": "push",
        "tables_synced": len(data),
        "rows_synced": rows_synced,
        "synced_at": synced_at,
    }


def sync_data_from_external_database(target_db: Session, external_database_url: str) -> dict:
    synced_at = utc_now()
    engine, SessionLocal = _external_session(external_database_url)

    try:
        Base.metadata.create_all(engine)
        with SessionLocal() as source_db:
            data = export_all_data(source_db)
            rows_synced = sum(len(rows) for rows in data.values())
            record_sync_success(source_db, "pull", synced_at)
            source_db.commit()
        restore_all_data(target_db, {"data": data})
        target_state = record_sync_success(target_db, "pull", synced_at)
        target_state.last_write_at = synced_at
        target_db.commit()
    except Exception as exc:
        record_sync_failure(target_db, "pull", str(exc))
        target_db.commit()
        raise
    finally:
        engine.dispose()

    return {
        "status": "ok",
        "direction": "pull",
        "tables_synced": len(data),
        "rows_synced": rows_synced,
        "synced_at": synced_at,
    }
