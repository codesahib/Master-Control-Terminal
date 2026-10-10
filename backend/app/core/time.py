from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

# Calendar days (one price per day, daily snapshots) follow the TSX market day, not UTC.
MARKET_TZ = ZoneInfo("America/Toronto")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime | None) -> datetime | None:
    # ponytail: naive values (SQLite, pre-timestamptz rows) are treated as UTC.
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


def market_date(value: datetime | None = None) -> date:
    """Toronto calendar date of an instant (default: now)."""
    return as_utc(value or utcnow()).astimezone(MARKET_TZ).date()


def market_day_start(day: date) -> datetime:
    """Toronto midnight of `day`, as aware UTC (safe to compare on SQLite and Postgres)."""
    return datetime.combine(day, time.min, tzinfo=MARKET_TZ).astimezone(timezone.utc)
