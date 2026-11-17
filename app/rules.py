from datetime import datetime, timezone


def now_utc():
    return datetime.now(timezone.utc)


def fmt(dt):
    """datetime -> строка UTC, например 2030-01-07T05:00:00Z"""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
