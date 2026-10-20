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
from bs4 import BeautifulSoup

PROFILE_DIR = Path(__file__).with_name("profiles")


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
        return Period("month", start, end, prev, prev_end, start.strftime("%b %Y"), start.strftime("%b"), prev.strftime("%b %Y"), prev.strftime("%b"))
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


def text(tag, value) -> None:
    tag.clear()
    tag.string = str(value)


def node(soup, tag: str, value: str, **attrs):
    el = soup.new_tag(tag, attrs=attrs)
    el.string = str(value)
    return el


def add_cells(soup, parent, values, numeric_from=1):
    row = soup.new_tag("tr")
    for i, value in enumerate(values):
        cell = node(soup, "td", value)
        if i >= numeric_from:
            cell["class"] = ["num"]
        row.append(cell)
    parent.append(row)
    return row


def pair_cell(soup, current, previous, prev_short, currency=False):
    td = soup.new_tag("td", attrs={"class": "num detail-pair"})
    td.append(node(soup, "strong", money(current) if currency else current))
    td.append(node(soup, "small", prev_short + " " + str(money(previous) if currency else previous)))
    return td


def date_label(start: date, end: date) -> str:
    return f"{start.day}–{end.day} {start.strftime('%b')} {start.year}"


def set_period_copy(soup, period: Period, source_text: str | None = None):
    label, short, prev_label, prev_short = period.label, period.short, period.prev_label, period.prev_short
    current_range = date_label(period.start, period.end)
    previous_range = date_label(period.prev_start, period.prev_end)
    soup.title.string = f"{PROFILE['name']} Performance Marketing Report — {label} vs {prev_label}"
    text(soup.select_one(".header .sub"), f"{label} ({current_range}) vs {prev_label} ({previous_range})")
    text(soup.select_one(".header .tag"), PROFILE["tag"])
    text(soup.select_one(".header .eyebrow"), f"{PROFILE['name']} · {'Weekly' if period.kind == 'week' else 'Monthly'} dashboard")
    text(soup.select_one(".sql-list h2"), f"Daftar SQL · {label}")
    text(soup.select_one(".hardware-section > .section-head .note"), f"Angka utama {short} · pembanding {prev_short}")
    text(soup.select_one(".campaign-detail .detail-head .note"), f"Angka utama {label} · pembanding kecil {prev_label}")
    legend = ((label, period.start, period.end), (prev_label, period.prev_start, period.prev_end))
    for span, (name, start, end) in zip(soup.select(".funnel .legend span")[:2], legend):
        dot = span.select_one(".dot")
        span.clear()
        if dot:span.append(dot)
        span.append(f"{name} ({start.day}–{end.day} {start.strftime('%b')})")
    for lab in soup.select(".funnel .week-label"):
        text(lab, short if "current" in lab.parent.select_one(".fill").get("class", []) else prev_short)
    for panel in soup.select(".stage-table"):
        headers = panel.select("thead th")
        for index in (1,4):
            if index < len(headers):text(headers[index],headers[index].get_text().replace("W—",short))
        for index in (2,5):
            if index < len(headers):text(headers[index],headers[index].get_text().replace("W—",prev_short))
    for note in soup.select(".table-note,.formula,.footer"):
        for child in list(note.find_all(string=True)):
            value = str(child).replace("Week —", label).replace("W—", short)
            if value != str(child):child.replace_with(value)
    text(soup.select_one(".footer"), f"Sumber: {source_text or 'empat CSV ' + PROFILE['source_label']}. {label}: {current_range}; {prev_label}: {previous_range}. Stage memakai tanggal event. SQL Value = {PROFILE['sql_value_label']}; Deal Value = Total Contract Deal Won.")


MONTHLY_WORDING = (("Same-week", "Same-month"), ("same-week", "same-month"), ("mingguan", "bulanan"), ("minggu", "bulan"), ("Weekly", "Monthly"))


def replace_wording(soup, pairs) -> None:
    for child in list(soup.find_all(string=True)):
        if child.parent.name in ("script", "style"):
            continue
        value = str(child)
        for old, new in pairs:
            value = value.replace(old, new)
        if value != str(child):
            child.replace_with(value)


def rebuild_product_slots(soup) -> None:
    """Make the analysis slots, filter buttons and scope note follow the profile's product list."""
    aside = soup.select_one(".hardware-product-analysis")
    blocks = aside.select(".product-analysis")
    prototype = copy.copy(blocks[0])
    for block in blocks:
        block.extract()
    for name in PRODUCTS:
        block = copy.copy(prototype)
        text(block.select_one("strong"), name)
        aside.append(block)
    filters = soup.select_one(".detail-filters")
    buttons = filters.select("button")
    prototype = copy.copy(buttons[1])
    for button in buttons[1:]:
        button.extract()
    existing = [b.get("data-hardware") for b in buttons[1:]]
    ordered = [n for n in existing if n in PRODUCTS] + [n for n in PRODUCTS if n not in existing]
    for name in ordered:
        button = copy.copy(prototype)
        button["data-hardware"] = name
        text(button, name)
        filters.append(button)
    names = ", ".join(PRODUCTS[:-1]) + ", dan " + PRODUCTS[-1] if len(PRODUCTS) > 1 else PRODUCTS[0]
    note = soup.select_one(".hardware-section > .table-note")
    text(note, f"Hanya Campaign Hardware {names}. Tag kosong, Unknown, dan Others dikecualikan.")


def populate(soup, data: dict[str, list[dict[str, str]]], period: Period, source_text: str | None = None):
    set_period_copy(soup, period, source_text)
    rebuild_product_slots(soup)
    pair = lambda soup, a, b, currency=False: pair_cell(soup, a, b, period.prev_short, currency)
    weeks = {w: {stage: period_rows(rows, stage, period, previous=(w == "prev")) for stage, rows in data.items()} for w in ("now", "prev")}
    metrics = {}
    for w in ("now", "prev"):
        r = weeks[w]
        metrics[w] = {
            "Submission": len(r["Submission"]), "MQL": len(r["MQL"]), "SQL": len(r["SQL"]),
            "SQL Value": sum(stage_value(x, "SQL") for x in r["SQL"]),
            "Deal Won": len(r["Deal Won"]), "Deal Won Value": sum(stage_value(x, "Deal Won") for x in r["Deal Won"]),
        }
    facts = {
        "bu": PROFILE["name"],
        "period": {"kind": period.kind, "label": period.label, "start": period.start.isoformat(), "end": period.end.isoformat(),
                   "comparison_label": period.prev_label, "comparison_start": period.prev_start.isoformat(), "comparison_end": period.prev_end.isoformat()},
        "definitions": {"sql_date_column": STAGES["SQL"], "sql_value": PROFILE["sql_value_label"], "deal_won_source": "Campaign Tracker: Deal Won Date dan Total Contract Deal Won"},
        "funnel": metrics,
    }
    stage_names = ("Submission", "MQL", "SQL", "SQL Value", "Deal Won", "Deal Won Value")
    for card, name in zip(soup.select(".summary > .card"), stage_names):
        a, b = metrics["now"][name], metrics["prev"][name]
        currency = "Value" in name
        text(card.select_one(".value"), money(a) if currency else fmt(a))
        text(card.select_one(".compare"), f"{period.prev_label}  {money(b) if currency else fmt(b)}")
        delta, kind = change(a,b)
        badge = card.select_one(".delta");text(badge, delta);badge["class"] = ["delta",kind]
        rate_el = card.select_one(".rate")
        if rate_el:
            numerator = name
            denom = {"MQL":"Submission", "SQL":"MQL", "Deal Won":"SQL"}[name]
            ra = rate(a, metrics["now"][denom]);rb = rate(b, metrics["prev"][denom])
            delta_rate = change(ra,rb,True)[0] if ra is not None and rb is not None else "N/A"
            text(rate_el, f"{name} Rate {pct(ra) if ra is not None else 'N/A'} vs {pct(rb) if rb is not None else 'N/A'} · {delta_rate}")
            rate_el["class"] = ["rate", "uptext" if ra is not None and rb is not None and ra>rb else "downtext" if ra is not None and rb is not None and ra<rb else ""]
    # Cohort events from stage-specific exports: inbound and stage event occur in the same week.
    same = {}
    for w in ("now","prev"):
        mql = [r for r in weeks[w]["MQL"] if inbound_in_period(r,period,w=="prev")]
        sql = [r for r in weeks[w]["SQL"] if inbound_in_period(r,period,w=="prev")]
        same[w] = (len(mql),len(sql),sum(stage_value(r,"SQL") for r in sql))
    facts["same_period"] = {w: {"MQL": same[w][0], "SQL": same[w][1], "SQL Value": same[w][2]} for w in same}
    for i,card in enumerate(soup.select(".same .card")):
        a,b=same["now"][i],same["prev"][i]
        total=metrics["now"]["MQL" if i==0 else "SQL" if i==1 else "SQL Value"]
        currency=i==2
        text(card.select_one(".value"),money(a) if currency else fmt(a))
        text(card.select_one(".compare"),f"{period.prev_label}  {money(b) if currency else fmt(b)} · {change(a,b)[0]}")
        card.select_one(".compare")["class"] = ["compare", "uptext" if a>b else "downtext" if a<b else ""]
        text(card.select_one(".share"),f"{rate_text(a,total)} dari total {money(total) if currency else fmt(total)} {'SQL Value' if currency else 'MQL' if i==0 else 'SQL'} {period.label}")
    # All prose panels remain deliberately blank.
    for el in soup.select(".executive-prose,.analysis-body,.hardware-analysis-summary p,.product-analysis p"):
        el.clear()
    # Deterministic highlight selection from numeric rankings.
    sql_by_campaign=defaultdict(lambda:[0,0])
    for r in weeks["now"]["SQL"]:
        x=sql_by_campaign[campaign(r)];x[0]+=1;x[1]+=stage_value(r,"SQL")
    sub_by_campaign=Counter(campaign(r) for r in weeks["now"]["Submission"])
    junk_by_campaign=Counter(campaign(r) for r in weeks["now"]["Submission"] if r.get("Remark","").casefold()=="junk leads")
    best=max(sql_by_campaign, key=lambda x:(sql_by_campaign[x][1],x),default=None)
    weak=max((x for x in sub_by_campaign if sql_by_campaign[x][0]==0),key=lambda x:(sub_by_campaign[x],x),default=None)
    junk=max(junk_by_campaign,key=lambda x:(junk_by_campaign[x],x),default=None)
    highlights=[
        (best,money(sql_by_campaign[best][1]) if best else "—",f"{sql_by_campaign[best][0]} SQL · {sub_by_campaign[best]} submission" if best else ""),
        (weak,f"{sub_by_campaign[weak]} submission" if weak else "—",f"0 SQL" if weak else ""),
        (junk,f"{junk_by_campaign[junk]} junk / {sub_by_campaign[junk]} submission" if junk else "—",f"{sql_by_campaign[junk][0]} SQL" if junk else ""),
    ]
    facts["highlights"] = {key: {"campaign": title, "detail": detail} for key, (title, _, detail) in zip(("top_sql_value", "high_volume_no_sql", "most_junk"), highlights) if title}
    for card,(title,value,small) in zip(soup.select(".highlight"),highlights):
        text(card.select_one("h3"),title or "—");text(card.select_one("strong"),value);text(card.select_one("small"),small)
    for card,stage in zip(soup.select(".contributors .card"),("SQL","Deal Won")):
        value=lambda r:stage_value(r,stage)
        top=max(weeks["now"][stage],key=lambda r:(value(r),r.get("Company","")),default=None)
        fields=card.select(".details b")
        if top:
            _inbound=parse_date(top.get("Inbound Date",""),"Inbound Date");_event=parse_date(top[STAGES[stage]],STAGES[stage])
            facts.setdefault("top_contributors", {})[stage] = {"value": value(top), "industry": top.get("Industry") or None, "source": source(top), "campaign": campaign(top), "days_from_inbound": (_event-_inbound).days if _inbound else None}
            text(card.select_one("h3"),top.get("Company") or "Unknown")
            text(card.select_one(".amount"),money(value(top)))
            inbound=parse_date(top.get("Inbound Date",""),"Inbound Date")
            event=parse_date(top[STAGES[stage]],STAGES[stage])
            for el,v in zip(fields,(top.get("Industry") or "—",source(top),campaign(top),f"{(event-inbound).days} hari" if inbound else "—")):text(el,v)
        else:
            text(card.select_one("h3"),"—");text(card.select_one(".amount"),"—")
            for el in fields:text(el,"—")
    tbody=soup.select_one(".sql-list tbody");tbody.clear()
    for r in sorted(weeks["now"]["SQL"],key=lambda r:(-stage_value(r,"SQL"),r.get("Company",""))):
        inbound=parse_date(r.get("Inbound Date",""),"Inbound Date")
        event=parse_date(r[STAGES["SQL"]],"SQL date")
        timing=f"{(event-inbound).days} hari · {'Same-week' if inbound_in_period(r,period) else 'Backlog'}" if inbound else "—"
        add_cells(soup,tbody,[r.get("Company") or "Unknown",r.get("Industry") or "—",campaign(r),money(stage_value(r,"SQL")),timing],numeric_from=3)
    footer=soup.select_one(".sql-list tfoot tr");footer.clear()
    td=node(soup,"td",f"TOTAL · {len(weeks['now']['SQL'])} SQL",colspan="3");footer.append(td)
    footer.append(node(soup,"td",money(metrics["now"]["SQL Value"]),**{"class":"num"}))
    footer.append(node(soup,"td",""))
    text(soup.select_one(".sql-list .table-note"),f"Diurutkan menurut SQL Value. SQL dihitung dari {STAGES['SQL']} pada {period.label}; Same-week berarti Inbound Date juga pada minggu tersebut.")
    # Funnel: each pair of bars is normalized within its own metric.
    funnel_labels=[("Submission",""),("MQL","Submission → MQL"),("SQL","MQL → SQL"),("Deal Won","SQL → Deal Won"),("SQL Value",""),("Deal Won Value","")]
    for row,(name,conversion) in zip(soup.select(".funnel .metric-row"),funnel_labels):
        a,b=metrics["now"][name],metrics["prev"][name]
        mark,kind=change(a,b);badge=row.select_one(".delta");text(badge,mark);badge["class"]=["delta",kind]
        maximum=max(a,b,1)
        for line,value in zip(row.select(".pair-line"),(a,b)):
            text(line.select_one("b"),money(value) if "Value" in name else fmt(value))
            line.select_one(".fill")["style"]=f"width:{value/maximum*100:.1f}%"
        conv=row.select_one(".conversion")
        if conv:
            denom={"MQL":"Submission","SQL":"MQL","Deal Won":"SQL"}[name]
            text(conv,f"{conversion}: {rate_text(a,metrics['now'][denom])} vs {rate_text(b,metrics['prev'][denom])}")
    for row,stage in zip(soup.select(".timing-row"),("MQL","SQL","Deal Won")):
        fresh=sum(inbound_in_period(r,period) for r in weeks["now"][stage]);total=len(weeks["now"][stage]);old=total-fresh
        row.select_one(".timing-current")["style"]=f"width:{fresh/total*100 if total else 0:.1f}%"
        row.select_one(".timing-prior")["style"]=f"width:{old/total*100 if total else 0:.1f}%"
        text(row.select_one("span"),f"{fresh} same-week · {old} backlog")
        facts.setdefault("timing", {})[stage] = {"same_period": fresh, "backlog": old}
    # Four event-week source breakdown tables.
    for panel,stage in zip(soup.select(".stage-table"),STAGES):
        body=panel.select_one("tbody");foot=panel.select_one("tfoot");body.clear();foot.clear()
        sources=sorted(set(source(r) for w in weeks for r in weeks[w][stage]),key=lambda x:(-sum(source(r)==x for r in weeks["now"][stage]),x))
        for name in sources+["TOTAL"]:
            sets=[weeks[w][stage] if name=="TOTAL" else [r for r in weeks[w][stage] if source(r)==name] for w in ("now","prev")]
            a,b=map(len,sets)
            values=[name,fmt(a),fmt(b),change(a,b)[0]]
            if stage in ("SQL","Deal Won"):
                values += [money(sum(stage_value(r,stage) for r in group)) for group in sets]
            add_cells(soup,foot if name=="TOTAL" else body,values)
            entry={"source":name,"now":a,"prev":b}
            if stage in ("SQL","Deal Won"):
                entry.update(now_value=sum(stage_value(r,stage) for r in sets[0]),prev_value=sum(stage_value(r,stage) for r in sets[1]))
            facts.setdefault("by_source", {}).setdefault(stage, []).append(entry)
    # Cross-stage table: MQL cohort uses Submission rows; later stages use event dates.
    cross=soup.select_one(".cross-stage");body=cross.select_one("tbody");foot=cross.select_one("tfoot");body.clear();foot.clear()
    sources=sorted(set(source(r) for stage in STAGES for r in weeks["now"][stage]))
    for name in sources+["TOTAL"]:
        selection=lambda stage:weeks["now"][stage] if name=="TOTAL" else [r for r in weeks["now"][stage] if source(r)==name]
        sub=selection("Submission");sql=selection("SQL");won=selection("Deal Won")
        mql=sum(bool(parse_date(r.get("MQL Date",""),"MQL Date") and period.contains(parse_date(r.get("MQL Date",""),"MQL Date"))) for r in sub)
        add_cells(soup,foot if name=="TOTAL" else body,[name,len(sub),mql,rate_text(mql,len(sub)),len(sql),money(sum(stage_value(r,"SQL") for r in sql)),len(won),money(sum(stage_value(r,"Deal Won") for r in won))])
        facts.setdefault("cross_stage", []).append({"source":name,"submission":len(sub),"mql_same_period":mql,"sql":len(sql),"sql_value":sum(stage_value(r,"SQL") for r in sql),"deal_won":len(won),"deal_value":sum(stage_value(r,"Deal Won") for r in won)})
    text(cross.select_one(".table-note"),f"MQL dan MQL Rate memakai submission {period.label} yang mencapai MQL dalam minggu yang sama. SQL dan Deal Won memakai tanggal event {period.label}, termasuk backlog; kolom-kolom bukan satu cohort.")
    # Product aggregate, restricted to five tagged hardware categories.
    hardware=soup.select_one(".hardware-section");table=hardware.select_one(":scope > .table-wrap table")
    body=table.select_one("tbody");foot=table.select_one("tfoot");body.clear();foot.clear()
    aggregate={w:[0]*7 for w in ("now","prev")}
    def product_metrics(name,w):
        sets={stage:[r for r in weeks[w][stage] if product(r)==name] for stage in STAGES}
        return [len(sets["Submission"]),len(sets["MQL"]),len(sets["SQL"]),sum(stage_value(r,"SQL") for r in sets["SQL"]),len(sets["Deal Won"]),sum(stage_value(r,"Deal Won") for r in sets["Deal Won"]),sum(r.get("Remark","").casefold()=="junk leads" for r in sets["Submission"])]
    def product_row(label, now, prev, target):
        tr=soup.new_tag("tr");tr.append(node(soup,"td",label))
        for i,(a,b) in enumerate(zip(now,prev)):
            td=soup.new_tag("td",attrs={"class":"num"});td.append(node(soup,"strong",money(a) if i in (3,5) else fmt(a)))
            td.append(node(soup,"small",f"{period.prev_short} "+(money(b) if i in (3,5) else fmt(b))))
            tr.append(td)
        target.append(tr)
    for name in PRODUCTS:
        a=product_metrics(name,"now");b=product_metrics(name,"prev")
        aggregate["now"]=[x+y for x,y in zip(aggregate["now"],a)]
        aggregate["prev"]=[x+y for x,y in zip(aggregate["prev"],b)]
        product_row(name,a,b,body)
        keys=("submission","mql","sql","sql_value","deal_won","deal_value","junk")
        facts.setdefault("hardware", []).append({"product":name,"now":dict(zip(keys,a)),"prev":dict(zip(keys,b))})
    product_row(f"TOTAL {len(PRODUCTS)} PRODUK",aggregate["now"],aggregate["prev"],foot)
    # Active current-week campaigns in the selected hardware categories.
    detail=hardware.select_one(".campaign-detail");body=detail.select_one("tbody");foot=detail.select_one("tfoot");body.clear();foot.clear()
    active=Counter((product(r),campaign(r)) for r in weeks["now"]["Submission"] if product(r) in PRODUCTS)
    ordered=sorted(active,key=lambda x:(-active[x],x[0],x[1]))
    totals={w:{"sub":0,"mql":0,"junk":0,"sql":0,"value":0} for w in ("now","prev")}
    def campaign_metrics(h,c,w):
        sub=[r for r in weeks[w]["Submission"] if product(r)==h and campaign(r)==c]
        sql=[r for r in weeks[w]["SQL"] if product(r)==h and campaign(r)==c]
        return {"sub":len(sub),"mql":sum(bool(parse_date(r.get("MQL Date",""),"MQL Date")) for r in sub),"junk":sum(r.get("Remark","").casefold()=="junk leads" for r in sub),"sql":len(sql),"value":sum(stage_value(r,"SQL") for r in sql)}
    for h,c in ordered:
        values={w:campaign_metrics(h,c,w) for w in ("now","prev")}
        for w in values:
            for key in totals[w]:totals[w][key]+=values[w][key]
        if len(facts.setdefault("campaigns", [])) < 20:
            facts["campaigns"].append({"hardware":h,"campaign":c,"now":values["now"],"prev":values["prev"]})
        tr=soup.new_tag("tr",attrs={"data-hardware":h});tr.append(node(soup,"td",h));tr.append(node(soup,"td",c))
        tr.append(pair(soup,values["now"]["sub"],values["prev"]["sub"]))
        tr.append(pair(soup,rate_text(values["now"]["mql"],values["now"]["sub"]),rate_text(values["prev"]["mql"],values["prev"]["sub"])))
        for key in ("junk","sql"):tr.append(pair(soup,values["now"][key],values["prev"][key]))
        tr.append(pair(soup,values["now"]["value"],values["prev"]["value"],True));body.append(tr)
    tr=soup.new_tag("tr");tr.append(node(soup,"td","TOTAL CAMPAIGN AKTIF",colspan="2"))
    tr.append(pair(soup,totals["now"]["sub"],totals["prev"]["sub"]))
    tr.append(pair(soup,rate_text(totals["now"]["mql"],totals["now"]["sub"]),rate_text(totals["prev"]["mql"],totals["prev"]["sub"])))
    for key in ("junk","sql"):tr.append(pair(soup,totals["now"][key],totals["prev"][key]))
    tr.append(pair(soup,totals["now"]["value"],totals["prev"]["value"],True));foot.append(tr)
    text(detail.select_one(".table-note"),f"MQL Rate campaign = submission pada minggu tersebut yang sudah memiliki MQL Date pada snapshot CSV ÷ submission campaign. SQL Value mengikuti {STAGES['SQL']} masing-masing minggu; cohort dan SQL event dapat berbeda.")
    if STAGES["SQL"] != "Proposal Price Quote Date":
        replace_wording(soup, (("Proposal Price Quote Date", STAGES["SQL"]), ("tanggal proposal", f"tanggal {STAGES['SQL']}")))
    if period.kind == "month":
        replace_wording(soup, MONTHLY_WORDING)
    return metrics, same, facts


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
        template=Path(__file__).with_name("dashboard_template.html")
        soup=BeautifulSoup(template.read_text(encoding="utf-8"),"html.parser")
        if not period_rows(data["Submission"], "Submission", period):
            raise ValueError(f"tidak ada Submission pada {args.period}; periksa periode dan file input")
        metrics,same,facts=populate(soup,data,period,f"tabel {args.table.name} (BU {profile['name'][2:] if profile['name'].startswith('BU') else profile['name']})" if args.table else None)
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(str(soup),encoding="utf-8")
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
        }
        if period.kind=="week":audit["week"]=args.period
        if table_info:facts["data_quality"]=table_info
        output.with_suffix(".audit.json").write_text(json.dumps(audit,ensure_ascii=False,indent=2,default=json_default)+"\n",encoding="utf-8")
        output.with_suffix(".facts.json").write_text(json.dumps(facts,ensure_ascii=False,indent=2,default=json_default)+"\n",encoding="utf-8")
    except (ValueError,OSError) as exc:
        parser.exit(2,f"Gagal: {exc}\n")
    print(f"OK: {output} (audit: {output.with_suffix('.audit.json')})")
    print(f"{period.label}: Submission {metrics['now']['Submission']}, MQL {metrics['now']['MQL']}, SQL {metrics['now']['SQL']}, SQL Value {money(metrics['now']['SQL Value'])}, Deal Won {metrics['now']['Deal Won']}")
    print("Bagian analisis deskriptif tetap kosong.")


if __name__=="__main__":
    main()
