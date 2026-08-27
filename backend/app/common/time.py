from datetime import UTC, datetime


def utcnow() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    """SQLite drops timezone information; normalize persisted timestamps at boundaries."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
