from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.models.models import AuditLog, Import, MarketPrice, SyncState, Transaction

SYNC_STATE_ID = 1


def create_sync_state_table(engine: Engine) -> None:
    SyncState.__table__.create(engine, checkfirst=True)


def utc_now() -> datetime:
    return datetime.utcnow()


def get_or_create_sync_state(db: Session) -> SyncState:
    state = db.get(SyncState, SYNC_STATE_ID)
    if state:
        return state
    state = SyncState(id=SYNC_STATE_ID, last_write_at=infer_last_write_at(db))
    db.add(state)
    db.flush()
    return state


def infer_last_write_at(db: Session) -> datetime | None:
    timestamps = [
        db.scalar(select(func.max(AuditLog.created_at))),
        db.scalar(select(func.max(Transaction.created_at))),
        db.scalar(select(func.max(Import.created_at))),
        db.scalar(select(func.max(MarketPrice.created_at))),
    ]
    return max((timestamp for timestamp in timestamps if timestamp), default=None)


def mark_database_write(db: Session, written_at: datetime | None = None) -> SyncState:
    state = get_or_create_sync_state(db)
    state.last_write_at = written_at or utc_now()
    return state


def record_sync_success(db: Session, direction: str, synced_at: datetime | None = None) -> SyncState:
    state = get_or_create_sync_state(db)
    timestamp = synced_at or utc_now()
    if direction == "push":
        state.last_push_at = timestamp
    elif direction == "pull":
        state.last_pull_at = timestamp
    state.last_sync_at = timestamp
    state.last_sync_direction = direction
    state.last_sync_status = "ok"
    state.last_sync_error = None
    return state


def record_sync_failure(db: Session, direction: str, error: str) -> SyncState:
    state = get_or_create_sync_state(db)
    state.last_sync_at = utc_now()
    state.last_sync_direction = direction
    state.last_sync_status = "failed"
    state.last_sync_error = error
    return state
