"""Budget and spend: calendar helpers, what a report shows, and checking the Budget form.

Weekly and monthly spend are separate inputs and are never derived from each other: an ISO week can straddle two months,
so a month is not "4 or 5 whole weeks". A week still belongs to the month that holds its Thursday, which only decides under
which month's page its spend is entered (W44 = 26 Oct to 1 Nov is entered under October).
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from viewer import targets

MONTHS_FULL = ("Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember")
TOP_ROWS = 10
MAX_CAMPAIGN_CHARS = 100


# ---- calendar
def month_label(month: str) -> str:
    year, number = month.split("-")
    return f"{MONTHS_FULL[int(number) - 1]} {year}"


def shift_month(month: str, delta: int) -> str:
    year, number = (int(x) for x in month.split("-"))
    year, index = divmod(year * 12 + number - 1 + delta, 12)
    return f"{year}-{index + 1:02d}"


def month_of_date(day: date) -> str:
    return f"{day.year}-{day.month:02d}"


def month_bounds(month: str) -> tuple[date, date]:
    first = date.fromisoformat(month + "-01")
    following = date.fromisoformat(shift_month(month, 1) + "-01")
    return first, following - timedelta(days=1)


def week_key(day: date) -> str:
    iso = day.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def week_start(key: str) -> date:
    year, week = key.split("-W")
    return date.fromisocalendar(int(year), int(week), 1)


def month_of_week(key: str) -> str:
    return month_of_date(week_start(key) + timedelta(days=3))


def prev_week(key: str) -> str:
    return week_key(week_start(key) - timedelta(days=7))


def weeks_of_month(month: str) -> list[tuple[str, date, date]]:
    """ISO weeks whose Thursday falls in the month, as (key, Monday, Sunday)."""
    first, last = month_bounds(month)
    thursday = first + timedelta(days=(3 - first.weekday()) % 7)
    out = []
    while thursday <= last:
        monday = thursday - timedelta(days=3)
        out.append((week_key(thursday), monday, monday + timedelta(days=6)))
        thursday += timedelta(days=7)
    return out


def month_of_period(kind: str, start: date) -> str:
    return month_of_date(start + timedelta(days=3)) if kind == "week" else month_of_date(start)


# ---- reading snapshots
def _amount(value) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def campaigns_of(snapshot: dict | None) -> dict:
    return (snapshot or {}).get("data", {}).get("campaigns", {}) if snapshot else {}


def newest(snaps: list[dict]) -> dict | None:
    return max(snaps, key=lambda s: s["saved_at"]) if snaps else None


def spend_snapshot(snaps: list[dict], until: date | None) -> dict | None:
    """The monthly-spend figures filled up to the latest date that is not after `until` (None: any date). Ties: the newest save."""
    usable = [s for s in snaps if s["spend_as_of"] and (until is None or s["spend_as_of"] <= until)
              and any(c.get("month_spend") is not None for c in campaigns_of(s).values())]
    return max(usable, key=lambda s: (s["spend_as_of"], s["saved_at"])) if usable else None


def _sum(values) -> Decimal | None:
    present = [v for v in values if v is not None]
    return sum(present, Decimal(0)) if present else None


def _month_figures(snaps: list[dict], until: date | None) -> dict:
    cur = newest(snaps)
    total = _amount(cur["total_budget"]) if cur else None
    spend = spend_snapshot(snaps, until)
    spent = _sum(_amount(c.get("month_spend")) for c in campaigns_of(spend).values()) if spend else None
    left = total - spent if total is not None and spent is not None else None
    used = float(spent * 100 / total) if total and spent is not None else None
    return {"total": total, "spent": spent, "left": left, "used": used, "as_of": spend["spend_as_of"] if spend else None}


def months_needed(kind: str, start: date) -> list[str]:
    month = month_of_period(kind, start)
    wanted = [month, shift_month(month, -1)]
    if kind == "week":
        wanted.append(month_of_week(prev_week(week_key(start))))
    return list(dict.fromkeys(wanted))


def report_budget(kind: str, start: date, end: date, period: str, snaps: dict[str, list[dict]]) -> dict:
    """Everything the budget section of a report shows, as plain numbers (None means not filled in)."""
    month = month_of_period(kind, start)
    out = {"state": "belum", "month_label": month_label(month), "prev_label": month_label(shift_month(month, -1)), "kind": kind, "month": month}
    cur = newest(snaps.get(month, []))
    if cur is None or cur["total_budget"] is None:
        return out
    now = _month_figures(snaps.get(month, []), end)
    before = _month_figures(snaps.get(shift_month(month, -1), []), None)
    out.update(state="ok", total=now["total"], spent=now["spent"], left=now["left"], used=now["used"], as_of=now["as_of"],
               prev={"total": before["total"], "spent": before["spent"], "left": before["left"], "used": before["used"]})
    weeks = lambda key, snapshots: _sum(_amount(c.get("weeks", {}).get(key)) for c in campaigns_of(newest(snapshots)).values())
    if kind == "week":
        out["week"] = weeks(period, snaps.get(month, []))
        previous = prev_week(period)
        out["prev_week"] = weeks(previous, snaps.get(month_of_week(previous), []))
    spend_snap = spend_snapshot(snaps.get(month, []), end)
    month_spend = {n: _amount(c.get("month_spend")) for n, c in campaigns_of(spend_snap).items()}
    rows = []
    for name, c in campaigns_of(cur).items():
        budget, spent = _amount(c.get("budget")), month_spend.get(name)
        if budget is None and spent is None and (c.get("weeks") or {}).get(period) is None:
            continue
        rows.append({"name": name, "budget": budget, "week": _amount((c.get("weeks") or {}).get(period)) if kind == "week" else None, "spent": spent,
                     "left": budget - spent if budget is not None and spent is not None else None,
                     "used": float(spent * 100 / budget) if budget and spent is not None else None})
    rows.sort(key=lambda r: (r["spent"] is None, -(r["spent"] or 0), r["name"].casefold()))
    shown, rest = rows[:TOP_ROWS], rows[TOP_ROWS:]
    out["rows"] = shown
    out["rest"] = {"count": len(rest), "budget": _sum(r["budget"] for r in rest), "week": _sum(r["week"] for r in rest), "spent": _sum(r["spent"] for r in rest)} if rest else None
    allocated = _sum(r["budget"] for r in rows)
    out["unallocated"] = now["total"] - (allocated or Decimal(0)) if now["total"] is not None and now["total"] > (allocated or Decimal(0)) else None
    return out


# ---- the Budget form
class FormError(Exception):
    def __init__(self, errors: dict[str, str]):
        super().__init__("form errors")
        self.errors = errors


def clean_name(raw: str) -> str:
    name = " ".join(raw.split())
    if not name:
        raise ValueError("Nama campaign tidak boleh kosong.")
    if len(name) > MAX_CAMPAIGN_CHARS or not name.isprintable():
        raise ValueError(f"Nama campaign maksimal {MAX_CAMPAIGN_CHARS} karakter dan tanpa karakter kontrol.")
    return name


def _money(raw: str, label: str, errors: dict, key: str) -> Decimal | None:
    try:
        return targets.parse_amount(raw, "idr")
    except ValueError as exc:
        errors[key] = f"{label}: {exc}"
        return None


def row_indexes(form: dict) -> list[int]:
    """Row numbers of the campaigns in a posted form. Removing a campaign in the browser leaves gaps, so they are read, never counted."""
    return sorted({int(k[2:]) for k in form if k.startswith("n_") and k[2:].isdigit()})


def parse_form(form: dict[str, str], month: str, today: date) -> dict:
    """Turns the posted Budget form into what is stored, or raises FormError naming the fields. Nothing is stored here."""
    errors: dict[str, str] = {}
    names: list[tuple[int, str]] = []
    seen: set[str] = set()
    for index in row_indexes(form):
        try:
            name = clean_name(form[f"n_{index}"])
        except ValueError as exc:
            errors[f"n_{index}"] = str(exc)
            continue
        if name.casefold() in seen:
            errors[f"n_{index}"] = f"Campaign {name} tercatat dua kali."
        seen.add(name.casefold())
        names.append((index, name))
    total = _money(form.get("total", ""), "Total budget", errors, "total")
    first, last = month_bounds(month)
    as_of_text = form.get("as_of", "").strip()
    as_of = None
    campaigns: dict[str, dict] = {}
    weeks = weeks_of_month(month)
    for i, name in names:
        entry: dict = {"budget": None, "month_spend": None, "weeks": {}}
        budget = _money(form.get(f"b_{i}", ""), f"Budget {name}", errors, f"b_{i}")
        if budget:  # 0 means no budget, like an empty field
            entry["budget"] = int(budget)
        month_spend = _money(form.get(f"m_{i}", ""), f"Spend {month_label(month)} {name}", errors, f"m_{i}")
        if month_spend is not None:
            entry["month_spend"] = int(month_spend)
        for key, monday, _ in weeks:
            field = f"w_{i}_{key}"
            value = _money(form.get(field, ""), f"Spend {key.split('-')[1]} {name}", errors, field)
            if value is None:
                continue
            if monday > today:
                errors[field] = f"Spend {key.split('-')[1]} {name}: minggu ini belum berjalan."
                continue
            entry["weeks"][key] = int(value)
        campaigns[name] = entry
    allocated = sum((Decimal(c["budget"]) for c in campaigns.values() if c["budget"]), Decimal(0))
    if "total" not in errors:
        if allocated > 0 and not total:
            errors["total"] = "Isi total budget lebih dulu, karena ada budget per campaign."
        elif total is not None and allocated > total:
            errors["total"] = f"Jumlah budget per campaign Rp {int(allocated):,} melebihi total budget Rp {int(total):,}. Sesuaikan salah satunya.".replace(",", ".")
    if any(c["month_spend"] is not None for c in campaigns.values()):
        try:
            as_of = date.fromisoformat(as_of_text)
        except ValueError:
            errors["as_of"] = "Isi tanggal sampai kapan spend bulanan ini (format tanggal)."
        else:
            if not first <= as_of <= min(last, today):
                errors["as_of"] = f"Tanggal harus di dalam {month_label(month)} dan tidak boleh di masa depan."
    elif as_of_text:
        try:
            as_of = date.fromisoformat(as_of_text)
        except ValueError:
            errors["as_of"] = "Format tanggal tidak dikenali."
        else:
            as_of = None  # a date without any monthly spend is meaningless
    if errors:
        raise FormError(errors)
    return {"total": int(total) if total else None, "as_of": as_of, "campaigns": campaigns}
