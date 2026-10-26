"""Performa page numbers, all computed at display time from the anonymous lead rows of one snapshot (format v2, see database/008).

A lead row holds the four stage dates, the SQL and Deal Won value and the six filter values. The page filters the leads (AND between
filters, OR inside one filter), counts every stage on its own date, groups the result per day, ISO week or calendar month, and lays out
the cohort matrices. A week or month at the edge of the range counts only the days inside the range.
"""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import NamedTuple

import performa as periods

MONTHS = ("Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des")
UNITS = {"hari": "day", "minggu": "week", "bulan": "month"}
DEFAULT_SPAN = {"hari": 14, "minggu": 12, "bulan": 6}  # points shown when no range was chosen
MAX_DAY_POINTS = 180
DIMENSIONS = (("channel", "Channel"), ("source", "Source"), ("medium", "Medium"), ("campaign", "Campaign"), ("category", "Category Campaign"), ("hardware", "Campaign Hardware"))
EMPTY_LABEL = "(kosong)"  # how a lead without a value for a filter is named, in the menu and in the address
MATRIX_KEYS = {  # key: (menu text, what the rows are, what the columns are)
    "sub_sql": ("Submission ke SQL", "SQL", "submission"),
    "mql_sql": ("MQL ke SQL", "SQL", "MQL"),
    "sub_mql": ("Submission ke MQL", "MQL", "submission"),
}
MATRIX_COLUMNS = 10
MATRIX_MAX_ROWS = 60
HEAT = ((6, "#5fbf84"), (4, "#a8cf5f"), (3, "#f6cf57"), (2, "#f2a54a"), (1, "#ec8359"))  # leads from, background; dark text keeps at least 5.6:1
ERR_ORDER = "Tanggal mulai harus sebelum atau sama dengan tanggal akhir."
ERR_DAYS = f"Per hari maksimal {MAX_DAY_POINTS} hari. Perkecil rentang atau pilih per minggu atau bulan."
SHOWN_KEYS = ("sub", "mql", "sql", "sqlv", "won", "wonv")


class Lead(NamedTuple):
    inbound: date | None
    mql: date | None
    sql: date | None
    won: date | None
    sqlv: Decimal
    wonv: Decimal
    d: tuple  # position of each filter value in Data.dims, in DIMENSIONS order


@dataclass
class Data:
    as_of: date
    dims: dict[str, list[str]]
    leads: list[Lead]


@dataclass
class Params:
    per: str
    start: date
    end: date
    matriks: str = "sub_sql"
    error: str = ""
    filters: dict[str, list[str]] = field(default_factory=dict)  # filter key -> chosen labels

    @property
    def active(self) -> int:
        return sum(len(v) for v in self.filters.values())


def label(value: str) -> str:
    return value or EMPTY_LABEL


def load(snapshot: dict) -> Data | None:
    """The leads of a snapshot, or None when it was made before lead rows existed (format v1)."""
    raw = snapshot["data"]
    if raw.get("v") != 2:
        return None
    days: dict[int, date | None] = {0: None}

    def day(n: int) -> date | None:
        if n not in days:
            days[n] = date.fromordinal(n)
        return days[n]

    leads = [Lead(day(r[0]), day(r[1]), day(r[2]), day(r[3]), Decimal(str(r[4])), Decimal(str(r[5])), tuple(r[6:12])) for r in raw["leads"]]
    return Data(snapshot["as_of"], {key: list(raw["dims"].get(key, [""])) for key, _ in DIMENSIONS}, leads)


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
        return periods.shift(periods.period_start(end, "week"), "week", -(n - 1))
    return periods.shift(end.replace(day=1), "month", -(n - 1))


def parse_params(query: dict, as_of: date, lists: dict | None = None) -> Params:
    """query: first value of each address parameter. lists: all values, needed for the filters that can be chosen more than once."""
    per = query.get("per") if query.get("per") in UNITS else "minggu"
    end = _date(query.get("to")) or as_of
    start = _date(query.get("from")) or default_start(per, end)
    params = Params(per, start, end, matriks=query.get("matriks") if query.get("matriks") in MATRIX_KEYS else "sub_sql")
    for key, _ in DIMENSIONS:
        chosen = [v for v in dict.fromkeys((lists or {}).get(key, [])) if len(v) <= 200]
        if chosen:
            params.filters[key] = chosen[:200]
    if start > end:
        params.error = ERR_ORDER
    elif per == "hari" and (end - start).days + 1 > MAX_DAY_POINTS:
        params.error = ERR_DAYS
    return params


# ---- filters
def _chosen(data: Data, params: Params) -> dict[int, set[int]]:
    """Filter position -> positions of the chosen values. A chosen label this snapshot does not have simply matches nothing extra."""
    out: dict[int, set[int]] = {}
    for i, (key, _) in enumerate(DIMENSIONS):
        wanted = set(params.filters.get(key, []))
        if wanted:
            out[i] = {n for n, value in enumerate(data.dims[key]) if label(value) in wanted}
    return out


def filter_leads(data: Data, params: Params, skip: int | None = None) -> list[Lead]:
    chosen = _chosen(data, params)
    rules = [(i, idx) for i, idx in chosen.items() if i != skip]
    if not rules:
        return data.leads
    return [lead for lead in data.leads if all(lead.d[i] in idx for i, idx in rules)]


def options(data: Data, params: Params) -> dict[str, list[dict]]:
    """For each filter, its values with the number of leads that match every OTHER filter, so a value never offers an empty result.
    A chosen value stays in the list even when its count is zero, so it can still be un-chosen."""
    out = {}
    for i, (key, _) in enumerate(DIMENSIONS):
        counts = Counter(lead.d[i] for lead in filter_leads(data, params, skip=i))
        picked = set(params.filters.get(key, []))
        rows = [{"value": label(v), "count": counts.get(n, 0), "selected": label(v) in picked} for n, v in enumerate(data.dims[key]) if counts.get(n, 0) or label(v) in picked]
        rows.sort(key=lambda r: (r["value"] == EMPTY_LABEL, -r["count"], r["value"].casefold()))
        out[key] = rows
    return out


PARENT_KEYS = ("channel", "source", "medium", "campaign")


def relations(data: Data) -> dict:
    """Which Channel, Source, Medium and Campaign values occur together on at least one lead, whatever the date range. The browser narrows Source,
    Medium and Campaign lists with it while a parent is being ticked. `labels` are the values of each filter; `combos` hold positions in them."""
    positions = [[key for key, _ in DIMENSIONS].index(k) for k in PARENT_KEYS]
    labels = {k: [label(v) for v in data.dims[k]] for k in PARENT_KEYS}
    combos = sorted({tuple(lead.d[i] for i in positions) for lead in data.leads})
    return {"labels": labels, "combos": [list(c) for c in combos]}


def nurturing_groups(rel: dict | None) -> tuple[dict | None, list[str], set[str]]:
    """Budget cannot take one row per Nurturing campaign: there are too many. Every Medium under a Source that holds "Nurturing" becomes one
    group ("Email Nurturing"), added to the campaign labels with the same Channel, Source and Medium so the parent filters still find it.
    Returns the relation with the groups added, the group names, and the campaigns that only ever occur under such a Source (to hide)."""
    if not rel:
        return rel, [], set()
    labels = {k: list(v) for k, v in rel["labels"].items()}
    combos = [list(c) for c in rel["combos"]]
    nurturing = {i for i, name in enumerate(labels["source"]) if "nurturing" in name.casefold()}
    if not nurturing:
        return rel, [], set()
    inside: dict[int, bool] = {}
    groups: dict[str, list[list[int]]] = {}
    for channel, source, medium, campaign in combos:
        inside[campaign] = inside.get(campaign, True) and source in nurturing
        if source in nurturing:
            medium_name = labels["medium"][medium]
            name = labels["source"][source] if medium_name in ("", EMPTY_LABEL) else f"{medium_name} {labels['source'][source]}"
            groups.setdefault(name, []).append([channel, source, medium])
    hidden = {labels["campaign"][c].casefold() for c, only in inside.items() if only}
    for name, parents in sorted(groups.items()):
        if name not in labels["campaign"]:
            labels["campaign"].append(name)
        position = labels["campaign"].index(name)
        combos += [[*parent, position] for parent in parents]
    return {"labels": labels, "combos": combos}, sorted(groups, key=str.casefold), hidden


# ---- the chosen range, grouped
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


def series(leads: list[Lead], params: Params) -> list[dict]:
    """One dict per bucket in the range: label, first and last day counted, and the six metrics (values as Decimal)."""
    gran = UNITS[params.per]
    buckets: dict[date, dict] = {}
    cursor = periods.period_start(params.start, gran)
    while cursor <= params.end:
        lo, hi = max(cursor, params.start), min(periods.period_end(cursor, gran), params.end)
        buckets[cursor] = {"label": _label(cursor, gran), "full": _label(cursor, gran, True), "lo": lo, "hi": hi, **{k: Decimal(0) for k in SHOWN_KEYS}}
        cursor = periods.shift(cursor, gran, 1)
    for lead in leads:
        for count_key, day, value_key, value in (("sub", lead.inbound, None, 0), ("mql", lead.mql, None, 0), ("sql", lead.sql, "sqlv", lead.sqlv), ("won", lead.won, "wonv", lead.wonv)):
            if day and params.start <= day <= params.end:
                bucket = buckets[periods.period_start(day, gran)]
                bucket[count_key] += 1
                if value_key:
                    bucket[value_key] += value
    return list(buckets.values())


def summary(points: list[dict]) -> dict:
    total = {k: sum((p[k] for p in points), Decimal(0)) for k in SHOWN_KEYS}
    rate = lambda a, b: float(total[a] * 100 / total[b]) if total[b] else None
    return {**total, "mql_rate": rate("mql", "sub"), "sql_rate": rate("sql", "mql"), "won_rate": rate("won", "sql")}


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


# ---- cohort matrices
def heat(n: int) -> str:
    return next((color for floor, color in HEAT if n >= floor), "transparent")


def _pairs(leads: list[Lead], key: str):
    """(row date, column date) per lead that has both: sub_sql = (SQL, inbound), mql_sql = (SQL, MQL), sub_mql = (MQL, inbound)."""
    for lead in leads:
        row, col = {"sub_sql": (lead.sql, lead.inbound), "mql_sql": (lead.sql, lead.mql), "sub_mql": (lead.mql, lead.inbound)}[key]
        if row and col:
            yield row, col


def matrix(leads: list[Lead], params: Params) -> dict | None:
    """Rows: the periods in the range in which a stage happened (newest first). Columns: the 10 latest periods the leads came from.
    A cell is a number of leads. Older columns are folded into "Lebih lama"; the last column is the row total over every column.
    Returns None for per-day (too many columns)."""
    if params.per == "hari":
        return None
    gran = UNITS[params.per]
    by_row: dict[date, Counter] = {}
    for row_day, col_day in _pairs(leads, params.matriks):
        by_row.setdefault(periods.period_start(row_day, gran), Counter())[periods.period_start(col_day, gran)] += 1
    last = periods.period_start(params.end, gran)
    columns = [periods.shift(last, gran, -k) for k in range(MATRIX_COLUMNS)]
    starts, cursor = [], periods.period_start(params.start, gran)
    if cursor < params.start:
        cursor = periods.shift(cursor, gran, 1)
    while cursor <= params.end:
        starts.append(cursor)
        cursor = periods.shift(cursor, gran, 1)
    starts.reverse()
    rows = []
    for start in starts[:MATRIX_MAX_ROWS]:
        counts = by_row.get(start, Counter())
        cells = [{"n": counts.get(c, 0), "bg": heat(counts.get(c, 0))} for c in columns]
        total = sum(counts.values())
        rows.append({"label": _matrix_label(start, gran), "cells": cells, "older": total - sum(c["n"] for c in cells), "total": total})
    return {"columns": [_matrix_label(c, gran) for c in columns], "rows": rows, "truncated": len(starts) > MATRIX_MAX_ROWS}


def _matrix_label(start: date, gran: str) -> str:
    if gran == "week":
        iso = start.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"
    return f"{MONTHS[start.month - 1]} {start.year}"
