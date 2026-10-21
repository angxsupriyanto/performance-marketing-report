"""Period arithmetic for the Performa page (day, ISO week Monday to Sunday, calendar month). Pure dates: no files, no network, no names."""
from __future__ import annotations

import calendar
from datetime import date, timedelta

GRANULARITIES = ("day", "week", "month")


def period_start(day: date, gran: str) -> date:
    if gran == "day":
        return day
    if gran == "week":
        return day - timedelta(days=day.weekday())
    return day.replace(day=1)


def period_end(start: date, gran: str) -> date:
    if gran == "day":
        return start
    if gran == "week":
        return start + timedelta(days=6)
    return start.replace(day=calendar.monthrange(start.year, start.month)[1])


def shift(start: date, gran: str, k: int) -> date:
    if gran == "day":
        return start + timedelta(days=k)
    if gran == "week":
        return start + timedelta(days=7 * k)
    index = start.year * 12 + start.month - 1 + k
    return date(index // 12, index % 12 + 1, 1)
