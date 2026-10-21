"""Performa page numbers: the chosen range grouped per day, ISO week or calendar month, the range summary, and the cohort table.

The input is one snapshot written by the n8n workflow "Performa Generate" (see database/007_performance.sql): per-day counts and
values, and cohort counts per day, week and month. Everything here is display-time arithmetic on those aggregates.
A week or month at the edge of the range counts only the days inside the range.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

import performa as cohort_math

MONTHS = ("Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des")
UNITS = {"hari": "day", "minggu": "week", "bulan": "month"}
DEFAULT_SPAN = {"hari": 14, "minggu": 12, "bulan": 6}  # points shown when no range was chosen
MAX_DAY_POINTS = 180
METRICS = {
    "mql": ("Submission ke MQL", "Submission", "MQL"),
    "sql_mql": ("MQL ke SQL", "MQL", "SQL"),
    "sql": ("Submission ke SQL", "Submission", "SQL"),
}
ERR_ORDER = "Tanggal mulai harus sebelum atau sama dengan tanggal akhir."
ERR_DAYS = f"Per hari maksimal {MAX_DAY_POINTS} hari. Perkecil rentang atau pilih per minggu atau bulan."
SHOWN_KEYS = ("sub", "mql", "sql", "sqlv", "won", "wonv")


@dataclass
class Params:
    per: str
    start: date
    end: date
    metrik: str
    error: str = ""


def _date(text: str | None) -> date | None:
    try:
        return date.fromisoformat((text or "").strip())
    except ValueError:
        return None


def default_start(per: str, end: date) -> date:
    n = DEFAULT_SPAN[per]
    if per == "hari":
        return end - timedelta(days=n - 1)
    if per == "minggu":
        return cohort_math.shift(cohort_math.period_start(end, "week"), "week", -(n - 1))
    return cohort_math.shift(end.replace(day=1), "month", -(n - 1))


def parse_params(query: dict, as_of: date) -> Params:
    per = query.get("per") if query.get("per") in UNITS else "minggu"
    metrik = query.get("metrik") if query.get("metrik") in METRICS else "mql"
    end = _date(query.get("to")) or as_of
    start = _date(query.get("from")) or default_start(per, end)
    params = Params(per, start, end, metrik)
    if start > end:
        params.error = ERR_ORDER
    elif per == "hari" and (end - start).days + 1 > MAX_DAY_POINTS:
        params.error = ERR_DAYS
    return params


def _label(start: date, gran: str, full: bool = False) -> str:
    if gran == "day":
        return f"{start.day} {MONTHS[start.month - 1]}" + (f" {start.year}" if full else "")
    if gran == "week":
        end = start + timedelta(days=6)
        week = f"W{start.isocalendar().week:02d}"
        if not full:
            return week
        span = f"{start.day}–{end.day} {MONTHS[end.month - 1]}" if start.month == end.month else f"{start.day} {MONTHS[start.month - 1]}–{end.day} {MONTHS[end.month - 1]}"
        return f"{week} ({span})"
    return f"{MONTHS[start.month - 1]} {start.year}"


def series(snapshot: dict, params: Params) -> list[dict]:
    """One dict per bucket in the range: label, first and last day counted, and the six metrics (values as Decimal)."""
    gran = UNITS[params.per]
    buckets: dict[date, dict] = {}
    cursor = cohort_math.period_start(params.start, gran)
    while cursor <= params.end:
        lo, hi = max(cursor, params.start), min(cohort_math.period_end(cursor, gran), params.end)
        buckets[cursor] = {"label": _label(cursor, gran), "full": _label(cursor, gran, True), "lo": lo, "hi": hi, **{k: Decimal(0) for k in SHOWN_KEYS}}
        cursor = cohort_math.shift(cursor, gran, 1)
    for text, entry in snapshot["data"]["days"].items():
        day = _date(text)
        if day is None or not params.start <= day <= params.end:
            continue
        bucket = buckets[cohort_math.period_start(day, gran)]
        for key in SHOWN_KEYS:
            if key in entry:
                bucket[key] += Decimal(str(entry[key]))
    return list(buckets.values())


def summary(points: list[dict]) -> dict:
    total = {k: sum((p[k] for p in points), Decimal(0)) for k in SHOWN_KEYS}
    rate = lambda a, b: float(total[a] * 100 / total[b]) if total[b] else None
    return {**total, "mql_rate": rate("mql", "sub"), "sql_rate": rate("sql", "mql"), "won_rate": rate("won", "sql")}


def cohort_rows(snapshot: dict, params: Params) -> list[dict]:
    """Cohorts whose period starts inside the range, with cumulative conversion per column ("-" is None: that period has not finished)."""
    gran = UNITS[params.per]
    out = []
    for start_text, size, mql_base, valid, mql_by, sql_by, sqlm_by in snapshot["data"]["cohorts"][gran]:
        start = _date(start_text)
        if start is None or not params.start <= start <= params.end:
            continue
        base, hits = {"mql": (size, mql_by), "sql_mql": (mql_base, sqlm_by), "sql": (size, sql_by)}[params.metrik]
        cells = [round(hits[k] * 100 / base, 1) if base and k < valid else None for k in range(cohort_math.COLUMNS)]
        out.append({"label": _label(start, gran, True), "base": base, "cells": cells})
    return out


def has_activity(points: list[dict]) -> bool:
    return any(p[k] for p in points for k in SHOWN_KEYS)


# ---- chart geometry
def nice_max(value: Decimal) -> Decimal:
    """Smallest 4 * unit (unit 1, 2, 5, 10, 20, 50, ...) that is not below value, so the five grid lines are round numbers."""
    if value <= 4:
        return Decimal(4)
    exponent = 10 ** max(0, math.floor(math.log10(float(value) / 4)))
    for step in (1, 2, 5, 10):
        if 4 * step * exponent >= value:
            return Decimal(4 * step * exponent)
    return Decimal(40 * exponent)


def compact(value: Decimal) -> str:
    n = float(value)
    for limit, suffix in ((1e9, " M"), (1e6, " jt"), (1e3, " rb")):
        if n >= limit:
            return f"{n / limit:.1f}".rstrip("0").rstrip(".").replace(".", ",") + suffix
    return f"{int(n)}"
