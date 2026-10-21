"""Cohort counts for the Performa page. Pure date arithmetic: no files, no network, no company names.

A cohort is the set of leads whose Inbound Date falls in one period (a day, an ISO week Monday to Sunday, or a calendar month).
For each cohort and each of the five columns (the same period, then 1 to 4 periods later) we count how many of its leads had
reached a stage by the END of that column's period. The viewer turns the counts into percentages:
  Submission to MQL  = mql_by[k]     / size
  Submission to SQL  = sql_by[k]     / size
  MQL to SQL         = sqlm_by[k]    / mql_base    (only leads that have an MQL date; a lead's later SQL date counts once it is <= the cutoff)
A column whose period has not fully elapsed at `as_of` is not rated (valid_columns says how many leading columns are).
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta

COLUMNS = 5
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


def cohorts(leads: list[tuple[date, date | None, date | None]], as_of: date, gran: str) -> list[list]:
    """leads: (inbound date, MQL date or None, SQL date or None). Rows are
    [start, size, mql_base, valid_columns, mql_by[5], sql_by[5], sql_of_mql_by[5]], oldest cohort first."""
    groups: dict[date, list[tuple[date, date | None, date | None]]] = {}
    for lead in leads:
        groups.setdefault(period_start(lead[0], gran), []).append(lead)
    rows = []
    for start in sorted(groups):
        members = groups[start]
        cutoffs = [period_end(shift(start, gran, k), gran) for k in range(COLUMNS)]
        valid = 0
        while valid < COLUMNS and cutoffs[valid] <= as_of:
            valid += 1
        rows.append([
            start.isoformat(), len(members), sum(1 for _, mql, _ in members if mql is not None), valid,
            [sum(1 for _, mql, _ in members if mql is not None and mql <= c) for c in cutoffs],
            [sum(1 for _, _, sql in members if sql is not None and sql <= c) for c in cutoffs],
            [sum(1 for _, mql, sql in members if mql is not None and sql is not None and sql <= c) for c in cutoffs],
        ])
    return rows


def build(leads: list[tuple[date, date | None, date | None]], as_of: date) -> dict[str, list[list]]:
    return {gran: cohorts(leads, as_of, gran) for gran in GRANULARITIES}
