"""Target rules and the display-time merge of targets into a stored report.

Reports are numeric and never contain targets. The generator leaves slots (`.tgt`, `.tgt-month`, `.tgt-cell`,
`.tgt-stack`) with the actuals as data attributes; this module fills them from the current targets.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation


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


def build_tg(view: dict, rows: list[dict] | None) -> dict:
    """What report_view needs to draw targets. rows=None means the database could not be read."""
    if rows is None:
        return {"error": True, "semester": None, "year": None, "hardware": {}}
    progress = view["progress"]
    hardware = {}
    if view.get("hardware"):
        hardware = {h["name"]: effective_hardware(rows, h["name"], view["month"]["key"]) for h in view["hardware"]}
    return {"error": False, "semester": semester_amount(rows, progress["semester"]["key"]), "year": year_amount(rows, progress["year"]["key"]), "hardware": hardware}


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
