"""Achievement figures typed by hand when the Sheet is not complete yet, and how they replace the system figures at display time.

A saved set is {"hardware": {product: number}, "semester": number, "year": number}; every key is optional and a missing key means "use the
system figure". Two forms write it: the month form (one figure per product, BU1 only) and the year form (semester and 1-year progress).
Each form replaces its own part and keeps the other. The stored report is never changed: the viewer applies the set to the report's view and
to the facts sent to the analysis, so the system figures stay visible only inside the form.
"""
from __future__ import annotations

import copy

from viewer import targets

SCOPES = ("month", "year")
MAX_REASON = 300


def parse(scope: str, raw: dict, view: dict) -> dict:
    """Checks the typed text of one form and returns the figures that were filled in. Raises ValueError with a message that is safe to show."""
    if scope not in SCOPES:
        raise ValueError("Bagian yang diubah tidak dikenal.")
    if not isinstance(raw, dict):
        raise ValueError("Isian tidak terbaca.")
    unit = view["progress"]["unit"]
    if scope == "month":
        names = [h["name"] for h in view.get("hardware") or []]
        if not names:
            raise ValueError("Report ini tidak punya angka per produk.")
        allowed, label_of = names, (lambda key: key)
    else:
        allowed, label_of = ["semester", "year"], (lambda key: "Semester" if key == "semester" else "Akumulasi 1 tahun")
    unknown = [k for k in raw if k not in allowed]
    if unknown:
        raise ValueError("Isian tidak dikenal: " + ", ".join(str(k)[:40] for k in unknown) + ".")
    parsed: dict = {}
    for key in allowed:
        value = raw.get(key, "")
        if value is not None and not isinstance(value, str):
            raise ValueError(f"{label_of(key)}: isian harus berupa teks angka.")
        try:
            amount = targets.parse_amount(value or "", unit)
        except ValueError as exc:
            raise ValueError(f"{label_of(key)}: {exc}")
        if amount is not None:
            parsed[key] = int(amount)
    return parsed


def clean_reason(raw) -> str:
    if raw is None:
        return ""
    if not isinstance(raw, str):
        raise ValueError("Alasan perubahan tidak terbaca.")
    text = " ".join(raw.split())
    if len(text) > MAX_REASON or not text.isprintable():
        raise ValueError(f"Alasan perubahan maksimal {MAX_REASON} karakter dan tanpa karakter kontrol.")
    return text


def merge(saved: dict | None, scope: str, parsed: dict) -> dict:
    """The new full set: the posted form replaces its own part, the other part stays as it was last saved."""
    current = copy.deepcopy((saved or {}).get("values") or {})
    if scope == "month":
        current.pop("hardware", None)
        if parsed:
            current["hardware"] = parsed
    else:
        current.pop("semester", None)
        current.pop("year", None)
        current.update(parsed)
    return current


def figures(saved: dict | None) -> dict:
    values = (saved or {}).get("values") or {}
    return values if isinstance(values, dict) else {}


def apply_view(view: dict, saved: dict | None) -> dict:
    """A copy of the report's view with the typed figures in place of the system ones. The original is left alone."""
    values = figures(saved)
    if not values:
        return view
    out = copy.deepcopy(view)
    for item in out.get("hardware") or []:
        if item["name"] in (values.get("hardware") or {}):
            item["month_to_date"] = values["hardware"][item["name"]]
    for scope in ("semester", "year"):
        if scope in values and scope in out.get("progress", {}):
            out["progress"][scope]["actual"] = values[scope]
    return out


def apply_facts(facts: dict, saved: dict | None) -> dict:
    """The same for the facts that feed the target context of the analysis."""
    values = figures(saved)
    if not values:
        return facts
    out = copy.deepcopy(facts)
    progress = out.get("progress") or {}
    focus = "focus_sql" if progress.get("focus_product") else "sql_value"
    for scope in ("semester", "year"):
        if scope in values and scope in (progress.get("total") or {}):
            progress["total"][scope][focus] = values[scope]
    for name, number in (values.get("hardware") or {}).items():
        if name in (progress.get("hardware") or {}):
            progress["hardware"][name]["month_to_date"] = number
    return out
