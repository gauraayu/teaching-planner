"""Single place that answers "what is today / now" in the institution's timezone.

Tests monkeypatch `today()` to make task categorisation deterministic.
"""
from datetime import date, datetime, timezone

from app.core.config import get_settings


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def today() -> date:
    return datetime.now(get_settings().tz).date()
