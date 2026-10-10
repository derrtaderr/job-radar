"""Business-day arithmetic for the warm-path windows.

Weekends only. Holidays are not modelled, so a window that spans one ends a
day early. That is the cheap direction to be wrong in: the person applies a
day sooner, and a referral ask is never held open longer than promised.
"""
from __future__ import annotations

import datetime


def add_business_days(start: datetime.date, n: int) -> datetime.date:
    """The date `n` business days after `start`. A Saturday or Sunday start
    counts from the following Monday, so Sat + 1 is Monday."""
    day = start
    added = 0
    while added < n:
        day += datetime.timedelta(days=1)
        if day.weekday() < 5:
            added += 1
    return day
