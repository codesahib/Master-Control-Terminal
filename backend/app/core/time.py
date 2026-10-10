from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime | None) -> datetime | None:
    # ponytail: naive values (SQLite, pre-timestamptz rows) are treated as UTC.
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)
