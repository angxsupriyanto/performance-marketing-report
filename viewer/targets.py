"""Target rules and the display-time merge of targets into a stored report.

Reports are numeric and never contain targets. The generator leaves slots (`.tgt`, `.tgt-month`, `.tgt-cell`,
`.tgt-stack`) with the actuals as data attributes; this module fills them from the current targets.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from bs4 import BeautifulSoup

import generate_report as gen

MONTH_KEY = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
MAX_DIGITS = 15


def parse_amount(text: str, unit: str) -> Decimal | None:
    """Blank means "leave as is". Rupiah accepts 'Rp 1.500.000' and '1500000' (a comma is rejected, not guessed); counts accept whole numbers only."""
    cleaned = (text or "").strip()
    if not cleaned:
        return None
    if unit == "idr":
        cleaned = re.sub(r"^rp\.?\s*", "", cleaned, flags=re.I).replace(".", "").replace(" ", "")
    if not cleaned.isascii() or not cleaned.isdigit() or len(cleaned) > MAX_DIGITS:
        raise ValueError("harus berupa angka bulat tanpa pecahan" + (" (boleh memakai titik ribuan)" if unit == "idr" else ""))
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        raise ValueError("bukan angka")


def effective_hardware(rows: list[dict], product: str, month_key: str) -> Decimal | None:
    """The row with the latest effective month not after month_key. A zero row clears the target."""
    candidates = [r for r in rows if r["scope"] == "hardware_month" and r["product"] == product and r["period_key"] <= month_key]
    if not candidates:
        return None
    chosen = max(candidates, key=lambda r: r["period_key"])
    return chosen["amount"] if chosen["amount"] > 0 else None


def semester_amount(rows: list[dict], key: str) -> Decimal | None:
    for r in rows:
        if r["scope"] == "semester" and r["period_key"] == key and r["amount"] > 0:
            return r["amount"]
    return None


def year_amount(rows: list[dict], year: str) -> Decimal | None:
    first, second = semester_amount(rows, f"{year}-S1"), semester_amount(rows, f"{year}-S2")
    return first + second if first is not None and second is not None else None


def percent(actual, target) -> float | None:
    return float(Decimal(actual) * 100 / Decimal(target)) if target else None


def _fmt_value(value, unit: str) -> str:
    return gen.money(value) if unit == "idr" else f"{gen.fmt(gen.whole(value))} SQL"


def _pct_text(value: float | None) -> str:
    return gen.pct(value) if value is not None else "—"


def _width(value: float | None) -> str:
    return f"width:{max(0.0, min(100.0, value or 0.0)):.1f}%"


def fill_targets(html: str, rows: list[dict]) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for card in soup.select(".target-progress .tgt"):
        unit, actual = card["data-unit"], Decimal(card["data-actual"])
        key = card["data-key"]
        target = year_amount(rows, key) if card["data-scope"] == "year" else semester_amount(rows, key)
        if target is None:
            continue
        value = percent(actual, target)
        card.select_one(".tgt-line").string = f"{_fmt_value(actual, unit)} dari target {_fmt_value(target, unit)}"
        card.select_one(".fill")["style"] = _width(value)
        card.select_one(".tgt-pct").string = f"{_pct_text(value)} dari target {'tahun' if card['data-scope'] == 'year' else 'semester'}"
    panel = soup.select_one(".tgt-month")
    if panel is not None:
        month_key = panel["data-month-key"]
        products = [c["data-product"] for c in soup.select("tbody td.tgt-cell[data-slot=target][data-product]")]
        targets = {p: effective_hardware(rows, p, month_key) for p in products}
        total_target = sum((t for t in targets.values() if t is not None), Decimal(0))
        mtd = Decimal(panel["data-mtd"])
        if total_target > 0:
            panel.select_one(".tgt-line").string = "Satu target per hardware. Total target adalah jumlah target semua produk yang sudah diatur."
            panel.select_one("[data-slot=target] dd").string = gen.money(total_target)
            panel.select_one("[data-slot=remain] dd").string = gen.money(max(total_target - mtd, Decimal(0)))
            value = percent(mtd, total_target)
            panel.select_one(".fill")["style"] = _width(value)
            panel.select_one(".tgt-pct").string = f"{_pct_text(value)} dari target {gen.money(total_target)}"
        for cell in soup.select("tbody td.tgt-cell[data-product]"):
            target = targets.get(cell["data-product"])
            if target is None:
                continue
            if cell["data-slot"] == "target":
                cell.string = gen.money(target)
            else:
                cell.string = _pct_text(percent(Decimal(cell["data-mtd"]), target))
        for cell in soup.select("tfoot td.tgt-cell"):
            if total_target > 0:
                cell.string = gen.money(total_target) if cell["data-slot"] == "target" else _pct_text(percent(mtd, total_target))
        for stack in soup.select(".tgt-stack[data-product]"):
            target = targets.get(stack["data-product"])
            if target is None:
                continue
            before, week = Decimal(stack["data-before"]), Decimal(stack["data-week"])
            before_w = max(0.0, min(100.0, percent(before, target)))
            week_w = max(0.0, min(100.0 - before_w, percent(week, target)))
            done = before + week
            for old in stack.select(".stack, .legend2"):
                old.decompose()
            text = stack.select_one(".tgt-text")
            bar = soup.new_tag("div", attrs={"class": "stack", "aria-hidden": "true"})
            bar.append(soup.new_tag("div", attrs={"class": "before", "style": f"width:{before_w:.1f}%"}))
            bar.append(soup.new_tag("div", attrs={"class": "week", "style": f"width:{week_w:.1f}%"}))
            legend = soup.new_tag("div", attrs={"class": "legend2"})
            for label in (f"Sebelum minggu ini {gen.money(before)}", f"Minggu ini {gen.money(week)}", f"Sisa target {gen.money(max(target - done, Decimal(0)))}"):
                span = soup.new_tag("span")
                span.string = label
                legend.append(span)
            text.insert_before(bar)
            text.insert_before(legend)
            text.string = f"{_pct_text(percent(done, target))} dari target {gen.money(target)}"
    return str(soup)


def context_for_analysis(facts: dict, rows: list[dict]) -> dict:
    """Numbers only. This is what the analysis may say about targets; the model never sees the rows themselves."""
    progress = facts.get("progress") or {}
    unit = progress.get("unit", "idr")
    windows = progress.get("windows") or {}
    focus = "focus_sql" if progress.get("focus_product") else "sql_value"
    out: dict = {"unit": unit}
    for scope, key in (("semester", windows.get("semester", {}).get("key")), ("year", windows.get("year", {}).get("key"))):
        if not key:
            continue
        actual = progress["total"][scope][focus]
        target = year_amount(rows, key) if scope == "year" else semester_amount(rows, key)
        out[scope] = {"label": windows[scope]["label"], "actual": actual, "target": target, "progress_percent": None if target is None else round(percent(actual, target), 1)}
    month = windows.get("month")
    if month and "hardware" in progress:
        items = []
        for name, values in progress["hardware"].items():
            target = effective_hardware(rows, name, month["key"])
            mtd = values["month_to_date"]
            items.append({"product": name, "month_to_date": mtd, "week": values["week_sql_value"], "target": target, "progress_percent": None if target is None else round(percent(mtd, target), 1)})
        total_target = sum((i["target"] for i in items if i["target"] is not None), Decimal(0))
        mtd_total = sum(i["month_to_date"] for i in items)
        out["month"] = {"label": month["label"], "hardware": items, "total_target": total_target or None, "month_to_date": mtd_total,
                        "progress_percent": None if not total_target else round(percent(mtd_total, total_target), 1)}
    return out
