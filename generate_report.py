#!/usr/bin/env python3
"""Deterministic weekly/monthly dashboard generator per BU. No AI, no network calls."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from decimal import ROUND_HALF_UP, Decimal
import calendar
import copy
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
import report_view

PROFILE_DIR = Path(__file__).with_name("profiles")
MONTHS_ID = ("Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des")


def load_profile(name: str) -> dict:
    path = PROFILE_DIR / f"{name.lower()}.json"
    if not path.is_file():
        available = ", ".join(sorted(p.stem for p in PROFILE_DIR.glob("*.json"))) or "tidak ada"
        raise ValueError(f"profil BU {name!r} tidak ditemukan; tersedia: {available}")
    return json.loads(path.read_text(encoding="utf-8"))


def required_columns(profile: dict) -> dict[str, tuple[str, ...]]:
    common = tuple(profile["common_columns"])
    dates = profile["stage_date_columns"]
    return {
        "Submission": common + ("Remark", "Inbound Date", dates["Submission"]),
        "MQL": common + ("Inbound Date", dates["MQL"]),
        "SQL": common + ("Inbound Date", dates["SQL"], profile["sql_value_column"]),
        "Deal Won": common + ("Inbound Date", dates["Deal Won"], profile["won_value_column"]),
    }


PROFILE = load_profile("bu1")
STAGES = dict(PROFILE["stage_date_columns"])
SQL_VALUE = PROFILE["sql_value_column"]
WON_VALUE = PROFILE["won_value_column"]
PRODUCTS = tuple(PROFILE["products"])
REQUIRED = required_columns(PROFILE)


def use_profile(profile: dict) -> None:
    global PROFILE, STAGES, SQL_VALUE, WON_VALUE, PRODUCTS, REQUIRED
    PROFILE = profile
    STAGES = dict(profile["stage_date_columns"])
    SQL_VALUE = profile["sql_value_column"]
    WON_VALUE = profile["won_value_column"]
    PRODUCTS = tuple(profile["products"])
    REQUIRED = required_columns(profile)


@dataclass(frozen=True)
class Period:
    kind: str
    start: date
    end: date
    prev_start: date
    prev_end: date
    label: str
    short: str
    prev_label: str
    prev_short: str

    def contains(self, value: date) -> bool:
        return self.start <= value <= self.end


def parse_period(value: str) -> Period:
    week = re.fullmatch(r"(\d{4})-W(\d{2})", value)
    if week:
        start = date.fromisocalendar(int(week.group(1)), int(week.group(2)), 1)
        prev = start - timedelta(days=7)
        n, pn = start.isocalendar().week, prev.isocalendar().week
        return Period("week", start, start + timedelta(days=6), prev, start - timedelta(days=1), f"Week {n}", f"W{n}", f"Week {pn}", f"W{pn}")
    month = re.fullmatch(r"(\d{4})-(\d{2})", value)
    if month:
        year, mon = int(month.group(1)), int(month.group(2))
        if not 1 <= mon <= 12:
            raise ValueError(f"bulan tidak valid: {value!r}")
        start = date(year, mon, 1)
        end = date(year, mon, calendar.monthrange(year, mon)[1])
        prev_end = start - timedelta(days=1)
        prev = prev_end.replace(day=1)
        return Period("month", start, end, prev, prev_end, f"{MONTHS_ID[start.month - 1]} {start.year}", MONTHS_ID[start.month - 1], f"{MONTHS_ID[prev.month - 1]} {prev.year}", MONTHS_ID[prev.month - 1])
    raise ValueError(f"periode {value!r} tidak valid; gunakan YYYY-Www (mingguan) atau YYYY-MM (bulanan)")


ISO_DATETIME = re.compile(r"(\d{4}-\d{2}-\d{2})(?:[T ]\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?\s?(?:Z|[+-]\d{2}:?\d{2})?)?")
US_DATETIME = re.compile(r"(\d{1,2}/\d{1,2}/\d{4})(?:[ T]\d{1,2}:\d{2}(?::\d{2})?(?:\s?[AaPp][Mm])?)?")


def parse_date(value: str, context: str) -> date | None:
    """Dates are taken as written in the cell. A time part is ignored, never converted between time zones, which
    matches how the Tracker's own pivots group a date-time cell by its date."""
    value = (value or "").strip()
    if not value:
        return None
    for pattern, fmt in ((ISO_DATETIME, "%Y-%m-%d"), (US_DATETIME, "%m/%d/%Y")):
        match = pattern.fullmatch(value)
        if match:
            try:
                return datetime.strptime(match.group(1), fmt).date()
            except ValueError:
                break
    raise ValueError(f"{context}: tanggal tidak valid {value!r}; gunakan M/D/YYYY atau YYYY-MM-DD (jam di belakang tanggal boleh)")


def decimal_amount(compact: str) -> Decimal | None:
    """Accept plain, Indonesian (1.234.567,89) and US (1,234,567.89) amounts; one separator followed by exactly three digits is a thousands separator."""
    if re.fullmatch(r"[0-9]+", compact) or re.fullmatch(r"[0-9]+\.[0-9]{1,2}", compact):
        return Decimal(compact)
    if re.fullmatch(r"[0-9]{1,3}(?:\.[0-9]{3})+(?:,[0-9]{1,2})?", compact):
        return Decimal(compact.replace(".", "").replace(",", "."))
    if re.fullmatch(r"[0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]{1,2})?", compact):
        return Decimal(compact.replace(",", ""))
    if re.fullmatch(r"[0-9]+,[0-9]{1,2}", compact):
        return Decimal(compact.replace(",", "."))
    return None


def parse_money(value: str, context: str) -> int | Decimal:
    value = (value or "").strip().replace("Rp", "").replace("rp", "").strip()
    if value in ("", "-"):
        return 0
    compact = value.replace(" ", "")
    if PROFILE.get("money_decimals"):
        amount = decimal_amount(compact)
        if amount is None:
            raise ValueError(f"{context}: nilai uang tidak valid {value!r}; gunakan angka Rupiah dengan desimal maksimal 2 digit")
        return int(amount) if amount == amount.to_integral_value() else amount
    if not re.fullmatch(r"(?:[0-9]+|[0-9]{1,3}(?:[.,][0-9]{3})+)", compact):
        raise ValueError(f"{context}: nilai uang tidak valid {value!r}; gunakan bilangan bulat Rupiah")
    return int(re.sub(r"[.,]", "", compact))


def normalize_header(name: str) -> str:
    return " ".join((name or "").strip().split())


def read_csv_rows(path: Path, wanted: set[str]) -> tuple[list[str], list[tuple[int, dict[str, str]]]]:
    """Read a CSV, normalize headers and map profile value-column aliases onto canonical names."""
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"{path}: CSV kosong")
        normalized = [normalize_header(x) for x in reader.fieldnames]
        rename = {}
        for canonical, alternatives in PROFILE.get("value_column_aliases", {}).items():
            if canonical not in normalized:
                found = next((alt for alt in alternatives if alt in normalized), None)
                if found:
                    rename[found] = canonical
        fields = [rename.get(x, x) for x in normalized]
        duplicated = sorted(name for name, count in Counter(fields).items() if count > 1 and name in wanted)
        if duplicated:
            raise ValueError(f"{path}: header duplikat setelah normalisasi: {', '.join(duplicated)}")
        rows = []
        for number, row in enumerate(reader, 2):
            clean = {}
            for key, value in row.items():
                if key is not None:
                    name = normalize_header(key)
                    clean[rename.get(name, name)] = (value or "").strip()
            rows.append((number, clean))
    return fields, rows


def summarize_issues(label: str, issues: dict) -> str:
    """One line: per column, how many rows are bad and one example. Values shown are dates or amounts, capped."""
    groups = sorted(issues.items(), key=lambda item: (-item[1][0], item[0]))
    parts = []
    for (column, kind), (count, number, value) in groups[:10]:
        shown = value if len(value) <= 40 else value[:37] + "..."
        hint = "; gunakan M/D/YYYY atau YYYY-MM-DD" if kind == "tanggal tidak valid" else ""
        parts.append(f"kolom {column}: {count} baris {kind} (contoh baris {number}: {shown!r}{hint})")
    more = f" (+{len(groups) - 10} kelompok lain)" if len(groups) > 10 else ""
    return f"{label}: " + " | ".join(parts) + more


def check_stage_rows(rows: list[tuple[int, dict[str, str]]], label: str, stage: str) -> list[dict[str, str]]:
    """Validates every row and reports all problems at once, grouped by column, instead of stopping at the first."""
    kept = []
    issues: dict[tuple[str, str], list] = {}

    def note(column: str, number: int, value: str, kind: str) -> None:
        entry = issues.setdefault((column, kind), [0, number, value])
        entry[0] += 1

    for number, clean in rows:
        if not any(clean.values()) or (clean.get("Company", "").casefold()=="grand total" and not clean.get(STAGES[stage], "")):
            continue
        ok = True
        for column in ("Inbound Date", STAGES[stage]):
            if column in clean:
                try:
                    parse_date(clean[column], "")
                except ValueError:
                    note(column, number, clean[column], "tanggal tidak valid")
                    ok = False
        if ok and not parse_date(clean[STAGES[stage]], ""):
            note(STAGES[stage], number, "", "wajib terisi")
            ok = False
        if stage in ("SQL", "Deal Won"):
            column = SQL_VALUE if stage == "SQL" else WON_VALUE
            try:
                parse_money(clean[column], "")
            except ValueError:
                note(column, number, clean[column], "nilai uang tidak valid")
                ok = False
        if ok:
            kept.append(clean)
    if issues:
        raise ValueError(summarize_issues(label, issues))
    return kept


def read_stage(path: Path, stage: str) -> list[dict[str, str]]:
    fields, rows = read_csv_rows(path, set(REQUIRED[stage]))
    missing = set(REQUIRED[stage]) - set(fields)
    if missing:
        raise ValueError(f"{path}: kolom wajib {stage} tidak ada: {', '.join(sorted(missing))}")
    return check_stage_rows(rows, path.name, stage)


def bu_key(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold()


def read_table(path: Path, allow_duplicate_keys: bool = False) -> tuple[dict[str, list[dict[str, str]]], dict]:
    """One row per lead with all stage dates: filter by BU, then split into the four stage views."""
    bu_column = PROFILE["bu_column"]
    key_column = PROFILE.get("record_key_column")
    wanted = set().union(*(set(cols) for cols in REQUIRED.values())) | {bu_column}
    fields, rows = read_csv_rows(path, wanted)
    missing = wanted - set(fields)
    if missing:
        raise ValueError(f"{path}: kolom wajib tidak ada: {', '.join(sorted(missing))}")
    targets = {bu_key(PROFILE["name"])} | {bu_key(x) for x in PROFILE.get("bu_values", [])}
    in_bu = [(n, r) for n, r in rows if bu_key(r.get(bu_column, "")) in targets]
    if not in_bu:
        seen = Counter(r.get(bu_column, "") or "(kosong)" for _, r in rows)
        listing = ", ".join(f"{k!r}: {v}" for k, v in seen.most_common(10))
        raise ValueError(f"{path}: tidak ada baris dengan {bu_column} = {PROFILE['name']}; nilai yang ada: {listing}. Tambahkan nilai yang benar ke bu_values di profil.")
    duplicates = []
    if key_column and key_column in fields:
        counts = Counter(r[key_column] for _, r in in_bu if r.get(key_column))
        duplicates = sorted(k for k, c in counts.items() if c > 1)
        if duplicates and not allow_duplicate_keys:
            raise ValueError(f"{path}: {len(duplicates)} {key_column} muncul lebih dari sekali dalam {PROFILE['name']} (contoh: {', '.join(duplicates[:3])}); perbaiki sumber atau pakai --allow-duplicate-keys setelah memastikan itu disengaja")
    data = {}
    problems = []
    for stage in STAGES:
        candidates = [(n, r) for n, r in in_bu if r.get(STAGES[stage])]
        try:
            data[stage] = check_stage_rows(candidates, f"{path.name} [{stage}]", stage)
        except ValueError as exc:
            problems.append(str(exc))
    if problems:
        raise ValueError(" || ".join(problems))
    info = {
        "rows_total": len(rows),
        "rows_in_bu": len(in_bu),
        "rows_without_bu": sum(1 for _, r in rows if not r.get(bu_column) and any(r.values())),
        "duplicate_record_keys": len(duplicates),
    }
    return data, info


def product(row: dict[str, str]) -> str:
    raw = row.get("Campaign Hardware", "").strip()
    raw = PROFILE.get("product_aliases", {}).get(raw, raw)
    for fix in PROFILE.get("product_typo_fixes", []):
        if raw == fix["raw"] and fix["campaign_contains"] in row.get("Campaign", "").upper():
            return fix["to"]
    return raw if raw in PRODUCTS else ""


def source(row: dict[str, str]) -> str:
    return row.get("Source", "").strip() or "Unknown"


def campaign(row: dict[str, str]) -> str:
    return row.get("Campaign", "").strip() or "Unknown"


def stage_value(row: dict[str, str], stage: str) -> int | Decimal:
    key = SQL_VALUE if stage == "SQL" else WON_VALUE
    return parse_money(row.get(key, ""), key)


def period_rows(rows: list[dict[str, str]], stage: str, period: Period, previous: bool = False) -> list[dict[str, str]]:
    start, end = (period.prev_start, period.prev_end) if previous else (period.start, period.end)
    return [r for r in rows if start <= parse_date(r[STAGES[stage]], STAGES[stage]) <= end]


def inbound_in_period(row: dict[str, str], period: Period, previous: bool = False) -> bool:
    inbound = parse_date(row.get("Inbound Date", ""), "Inbound Date")
    start, end = (period.prev_start, period.prev_end) if previous else (period.start, period.end)
    return bool(inbound and start <= inbound <= end)


MONTH_NAMES = ("Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember")


def thursday_of(day: date) -> date:
    return day - timedelta(days=day.weekday()) + timedelta(days=3)


def bucket_of(day: date, scope: str) -> tuple:
    if scope == "month":
        return (day.year, day.month)
    if scope == "semester":
        return (day.year, 1 if day.month <= 6 else 2)
    return (day.year,)


def window(period: Period, scope: str) -> dict:
    """Month, semester or year that a period belongs to, accumulated up to the period end.

    A week belongs to the month/semester/year that holds its Thursday, the same rule as ISO week numbering.
    Weekly windows therefore start on the Monday of the first week that belongs to the bucket.
    """
    if period.kind == "week":
        ref = thursday_of(period.start)
        start = period.start
        while bucket_of(thursday_of(start - timedelta(days=7)), scope) == bucket_of(ref, scope):
            start -= timedelta(days=7)
    else:
        ref = period.start
        first_month = {"month": ref.month, "semester": 1 if ref.month <= 6 else 7, "year": 1}[scope]
        start = date(ref.year, first_month, 1)
    if scope == "month":
        key, label = f"{ref.year}-{ref.month:02d}", f"{MONTH_NAMES[ref.month - 1]} {ref.year}"
    elif scope == "semester":
        n = 1 if ref.month <= 6 else 2
        key, label = f"{ref.year}-S{n}", f"Semester {n} {ref.year}"
    else:
        key, label = str(ref.year), str(ref.year)
    return {"key": key, "label": label, "start": start, "end": period.end}


def rows_between(rows: list[dict[str, str]], stage: str, start: date, end: date) -> list[dict[str, str]]:
    return [r for r in rows if start <= parse_date(r[STAGES[stage]], STAGES[stage]) <= end]


def fmt(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def whole(n: int | Decimal) -> int:
    return int(Decimal(n).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def money(n: int | Decimal) -> str:
    return "Rp " + fmt(whole(n))


def json_default(value):
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    raise TypeError(f"tidak dapat men-serialize {type(value).__name__}")


def pct(n: float) -> str:
    return f"{n:.1f}".replace(".", ",") + "%"


def rate(a: int, b: int) -> float | None:
    return 100 * a / b if b else None


def rate_text(a: int, b: int) -> str:
    x = rate(a, b)
    return pct(x) if x is not None else "N/A"


def change(a: int | float, b: int | float, pp: bool = False) -> tuple[str, str]:
    if b == 0 and not pp:
        return ("→ 0,0%", "flat") if a == 0 else ("N/A", "flat")
    diff = (a - b) if pp else (100 * (a / b - 1))
    mark = "▲" if diff > 0 else "▼" if diff < 0 else "→"
    return f"{mark} {f'{abs(diff):.1f}'.replace('.', ',') + ' pp' if pp else pct(abs(diff))}", "up" if diff > 0 else "down" if diff < 0 else "flat"


def sql_total(rows: list[dict[str, str]], start: date, end: date, only=None) -> tuple[int, int | Decimal]:
    chosen = [r for r in rows_between(rows, "SQL", start, end) if only is None or only(r)]
    return len(chosen), sum((stage_value(r, "SQL") for r in chosen), 0)


def progress_facts(data, period: Period, weeks) -> dict:
    """Actuals that targets are compared with. Targets live in the database, so they are never part of the report."""
    windows = {scope: window(period, scope) for scope in ("month", "semester", "year")}
    focus = PROFILE.get("focus_product")
    sql_rows = data["SQL"]
    result = {
        "week_rule": "bulan, semester, dan tahun sebuah minggu ditentukan oleh hari Kamis di minggu itu",
        "unit": PROFILE.get("target_unit", "idr"),
        "windows": {k: {"key": v["key"], "label": v["label"], "start": v["start"].isoformat(), "end": v["end"].isoformat()} for k, v in windows.items()},
    }
    if PROFILE.get("hardware_report", True):
        hardware = {}
        month = windows["month"]
        for name in PRODUCTS:
            mine = lambda r, name=name: product(r) == name
            _, week_value = sql_total(sql_rows, period.start, period.end, mine)
            _, month_value = sql_total(sql_rows, month["start"], month["end"], mine)
            hardware[name] = {"week_sql_value": week_value, "month_before_period": month_value - week_value, "month_to_date": month_value}
        result["hardware"] = hardware
    total = {}
    for scope, win in windows.items():
        count, value = sql_total(sql_rows, win["start"], win["end"])
        total[scope] = {"sql": count, "sql_value": value}
        if focus:
            fcount, fvalue = sql_total(sql_rows, win["start"], win["end"], lambda r: product(r) == focus)
            total[scope].update(focus_sql=fcount, focus_sql_value=fvalue)
    result["total"] = total
    if focus:
        result["focus_product"] = focus
    return result


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def range_text(start: date, end: date) -> str:
    if (start.year, start.month) == (end.year, end.month):
        return f"{start.day} sampai {end.day} {MONTHS_ID[end.month - 1]} {end.year}"
    return f"{start.day} {MONTHS_ID[start.month - 1]} {start.year} sampai {end.day} {MONTHS_ID[end.month - 1]} {end.year}"


def build(data: dict[str, list[dict[str, str]]], period: Period) -> tuple[dict, dict, dict, dict, dict]:
    """Computes everything the report shows. Returns (view, metrics, same, facts, lists); the view is what report_view renders."""
    weeks = {w: {stage: period_rows(rows, stage, period, previous=(w == "prev")) for stage, rows in data.items()} for w in ("now", "prev")}
    metrics = {}
    for w in ("now", "prev"):
        r = weeks[w]
        metrics[w] = {
            "Submission": len(r["Submission"]), "MQL": len(r["MQL"]), "SQL": len(r["SQL"]),
            "SQL Value": sum(stage_value(x, "SQL") for x in r["SQL"]),
            "Deal Won": len(r["Deal Won"]), "Deal Won Value": sum(stage_value(x, "Deal Won") for x in r["Deal Won"]),
        }
    same = {}
    for w in ("now", "prev"):
        mql = [r for r in weeks[w]["MQL"] if inbound_in_period(r, period, w == "prev")]
        sql = [r for r in weeks[w]["SQL"] if inbound_in_period(r, period, w == "prev")]
        same[w] = (len(mql), len(sql), sum(stage_value(r, "SQL") for r in sql))
    progress = progress_facts(data, period, weeks)
    facts = {
        "bu": PROFILE["name"],
        "period": {"kind": period.kind, "label": period.label, "start": period.start.isoformat(), "end": period.end.isoformat(),
                   "comparison_label": period.prev_label, "comparison_start": period.prev_start.isoformat(), "comparison_end": period.prev_end.isoformat()},
        "definitions": {"sql_date_column": STAGES["SQL"], "sql_value": PROFILE["sql_value_label"], "deal_won_source": "Campaign Tracker: Deal Won Date dan Total Contract Deal Won"},
        "funnel": metrics,
        "same_period": {w: {"MQL": same[w][0], "SQL": same[w][1], "SQL Value": same[w][2]} for w in same},
        "progress": progress,
    }
    # Company + amount per SQL and Deal Won row, for the chat summary only. Never part of facts, which go to the model.
    lists = {stage: [{"company": " ".join((r.get("Company") or "Unknown").split()), "value": stage_value(r, stage)}
                     for r in sorted(weeks["now"][stage], key=lambda r: (-stage_value(r, stage), r.get("Company", "")))]
             for stage in ("SQL", "Deal Won")}
    same_word = "Same-week" if period.kind == "week" else "Same-month"
    sql_rows = []
    for r in sorted(weeks["now"]["SQL"], key=lambda r: (-stage_value(r, "SQL"), r.get("Company", ""))):
        inbound = parse_date(r.get("Inbound Date", ""), "Inbound Date")
        event = parse_date(r[STAGES["SQL"]], "SQL date")
        timing = f"{(event - inbound).days} hari, {same_word if inbound_in_period(r, period) else 'Backlog'}" if inbound else "—"
        sql_rows.append({"company": r.get("Company") or "Unknown", "industry": r.get("Industry") or "—", "campaign": campaign(r), "value": whole(stage_value(r, "SQL")), "timing": timing})
    now, prev = metrics["now"], metrics["prev"]
    whole_all = lambda d: {k: whole(v) for k, v in d.items()}
    year, sem = progress["windows"]["year"], progress["windows"]["semester"]
    focus_name = PROFILE.get("focus_product")
    actual_key = "focus_sql" if focus_name else "sql_value"
    view = {
        "v": 1, "bu": PROFILE["name"], "kind": period.kind, "label": period.label, "prev_label": period.prev_label,
        "range": range_text(period.start, period.end), "prev_range": range_text(period.prev_start, period.prev_end), "same_word": same_word,
        "metrics": whole_all(now), "metrics_prev": whole_all(prev),
        "same": {"MQL": same["now"][0], "SQL": same["now"][1], "SQL Value": whole(same["now"][2])},
        "same_prev": {"MQL": same["prev"][0], "SQL": same["prev"][1], "SQL Value": whole(same["prev"][2])},
        "progress": {
            "unit": progress["unit"],
            "semester": {"key": sem["key"], "label": sem["label"], "actual": whole(progress["total"]["semester"][actual_key])},
            "year": {"key": year["key"], "year": year["label"], "actual": whole(progress["total"]["year"][actual_key])},
        },
        "sql_list": {"rows": sql_rows, "count": len(sql_rows), "value": whole(now["SQL Value"])},
    }
    if STAGES["SQL"] != "Proposal Price Quote Date":
        view["sql_note"] = f"Untuk {PROFILE['name']}, SQL ditentukan dari kolom {STAGES['SQL']} dan SQL Value dari kolom {PROFILE['sql_value_column'].replace('SUM of ', '')}."
    if PROFILE.get("hardware_report", True):
        month = progress["windows"]["month"]
        view["month"] = {"key": month["key"], "label": month["label"]}
        hardware, keys = [], ("submission", "mql", "sql", "sql_value", "deal_won", "deal_value", "junk")
        facts["hardware"] = []
        for name in PRODUCTS:
            sets = {stage: [r for r in weeks["now"][stage] if product(r) == name] for stage in STAGES}
            values = progress["hardware"][name]
            hardware.append({"name": name, "slug": slug(name), "submission": len(sets["Submission"]), "mql": len(sets["MQL"]), "sql": len(sets["SQL"]),
                             "deal_won": len(sets["Deal Won"]), "week": whole(values["week_sql_value"]), "before": whole(values["month_before_period"]), "month_to_date": whole(values["month_to_date"])})
            junk = sum(r.get("Remark", "").casefold() == "junk leads" for r in sets["Submission"])
            facts["hardware"].append({"product": name, "now": dict(zip(keys, [len(sets["Submission"]), len(sets["MQL"]), len(sets["SQL"]), sum(stage_value(r, "SQL") for r in sets["SQL"]), len(sets["Deal Won"]), sum(stage_value(r, "Deal Won") for r in sets["Deal Won"]), junk]))})
        view["hardware"] = hardware
    if focus_name:
        rows = sorted((r for r in weeks["now"]["SQL"] if product(r) == focus_name), key=lambda r: (-stage_value(r, "SQL"), r.get("Company", "")))
        total = sum((stage_value(r, "SQL") for r in rows), 0)
        facts["focus_period"] = {"product": focus_name, "sql": len(rows), "sql_value": total}
        view["focus"] = {"product": focus_name, "parent": PROFILE.get("focus_parent", ""), "count": len(rows), "value": whole(total), "rows": [
            {"company": r.get("Company") or "Unknown", "industry": r.get("Industry") or "—", "date": parse_date(r[STAGES["SQL"]], STAGES["SQL"]).isoformat(), "value": whole(stage_value(r, "SQL"))} for r in rows]}
    if PROFILE.get("deal_won_list"):
        rows = sorted(weeks["now"]["Deal Won"], key=lambda r: (-stage_value(r, "Deal Won"), r.get("Company", "")))
        won_rows = []
        for r in rows:
            inbound, event = parse_date(r.get("Inbound Date", ""), "Inbound Date"), parse_date(r[STAGES["Deal Won"]], STAGES["Deal Won"])
            won_rows.append({"company": r.get("Company") or "Unknown", "industry": r.get("Industry") or "—", "campaign": campaign(r), "value": whole(stage_value(r, "Deal Won")), "timing": f"{(event - inbound).days} hari" if inbound else "—"})
        view["won_list"] = {"rows": won_rows, "count": len(rows), "value": whole(now["Deal Won Value"]), "column": WON_VALUE.replace("SUM of ", "")}
    view["analysis_keys"] = report_view.analysis_keys(view)
    return view, metrics, same, facts, lists


def find_inputs(directory: Path) -> dict[str, Path]:
    keys = {"Submission": "submission", "MQL": "mql", "SQL": "sql", "Deal Won": "deal won"}
    files = [p for p in sorted(directory.iterdir()) if p.suffix.lower() == ".csv"]
    found = {}
    for stage, key in keys.items():
        hits = [p for p in files if key in p.name.lower().replace("_", " ")]
        if len(hits) != 1:
            raise ValueError(f"{directory}: harus ada tepat satu CSV untuk {stage} (nama memuat {key!r}), ditemukan {len(hits)}")
        found[stage] = hits[0]
    return found


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bu",default="bu1",help="profil BU di folder profiles/, default bu1")
    parser.add_argument("--table",type=Path,help="satu CSV (ekspor NEW Customers List) berisi semua stage, satu baris per lead; difilter menurut kolom BU")
    parser.add_argument("--allow-duplicate-keys",action="store_true",help="izinkan Record Key ganda pada --table (default: ditolak)")
    parser.add_argument("--input-dir",type=Path,help="folder berisi empat CSV; alternatif dari --submission/--mql/--sql/--won")
    parser.add_argument("--submission",type=Path)
    parser.add_argument("--mql",type=Path)
    parser.add_argument("--sql",type=Path)
    parser.add_argument("--won",type=Path)
    parser.add_argument("--period","--week",dest="period",required=True,help="YYYY-Www untuk mingguan (contoh 2026-W39) atau YYYY-MM untuk bulanan (contoh 2026-09)")
    parser.add_argument("--output",type=Path,help="default: output/<BU>_<periode>.html")
    args=parser.parse_args()
    try:
        profile=load_profile(args.bu)
        use_profile(profile)
        period=parse_period(args.period)
        table_info=None
        if args.table:
            if args.input_dir or any((args.submission,args.mql,args.sql,args.won)):parser.error("--table tidak boleh digabung dengan --input-dir atau opsi per stage")
            paths={}
        elif args.input_dir:
            paths=find_inputs(args.input_dir)
        else:
            paths={"Submission":args.submission,"MQL":args.mql,"SQL":args.sql,"Deal Won":args.won}
            if not all(paths.values()):parser.error("berikan --table, --input-dir, atau keempat --submission --mql --sql --won")
        output=args.output or Path("output")/f"{profile['name']}_{args.period.replace('-W','_W') if period.kind=='week' else args.period}.html"
        if args.table:
            data,table_info=read_table(args.table,args.allow_duplicate_keys)
        else:
            data={stage:read_stage(path,stage) for stage,path in paths.items()}
        if not period_rows(data["Submission"], "Submission", period):
            raise ValueError(f"tidak ada Submission pada {args.period}; periksa periode dan file input")
        view,metrics,same,facts,lists=build(data,period)
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(report_view.render_document(view),encoding="utf-8")
        audit = {
            "bu": profile["name"],
            "period": args.period,
            "period_kind": period.kind,
            "period_start": period.start.isoformat(),
            "period_end": period.end.isoformat(),
            "comparison_start": period.prev_start.isoformat(),
            "comparison_end": period.prev_end.isoformat(),
            "source": "table" if args.table else "stage_csv",
            "stage_date_columns": dict(STAGES),
            "inputs": {"table": {"file": args.table.name, "sha256": hashlib.sha256(args.table.read_bytes()).hexdigest(), **table_info, "stage_rows": {stage: len(rows) for stage,rows in data.items()}}} if args.table else {stage: {"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "rows_excluding_totals": len(data[stage])} for stage,path in paths.items()},
            "metrics": metrics,
            "same_week": {"MQL": same["now"][0], "SQL": same["now"][1], "SQL Value": same["now"][2]},
            "descriptive_analysis": "blank",
            "analysis_keys": view["analysis_keys"],
        }
        if period.kind=="week":audit["week"]=args.period
        if table_info:facts["data_quality"]=table_info
        output.with_suffix(".audit.json").write_text(json.dumps(audit,ensure_ascii=False,indent=2,default=json_default)+"\n",encoding="utf-8")
        output.with_suffix(".facts.json").write_text(json.dumps(facts,ensure_ascii=False,indent=2,default=json_default)+"\n",encoding="utf-8")
        output.with_suffix(".lists.json").write_text(json.dumps(lists,ensure_ascii=False,indent=2,default=json_default)+"\n",encoding="utf-8")
    except (ValueError,OSError) as exc:
        parser.exit(2,f"Gagal: {exc}\n")
    print(f"OK: {output} (audit: {output.with_suffix('.audit.json')})")
    print(f"{period.label}: Submission {metrics['now']['Submission']}, MQL {metrics['now']['MQL']}, SQL {metrics['now']['SQL']}, SQL Value {money(metrics['now']['SQL Value'])}, Deal Won {metrics['now']['Deal Won']}")
    print("Bagian analisis deskriptif tetap kosong.")


if __name__=="__main__":
    main()
