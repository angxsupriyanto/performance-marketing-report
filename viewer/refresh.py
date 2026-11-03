"""Starting a report or Performa run from the viewer, and reading its status back.

The viewer records a request (who, what, which company and period) and calls the n8n webhook with the new job id. n8n writes one result per
company when that company's run ends. The status is derived here from the request and its results, so it survives a restart of the viewer and
keeps the buttons locked while a run goes on. Nothing is stored about the leads, only short messages.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import generate_report

TIMEOUT_SECONDS = 300  # a run that has not finished its last company within five minutes is reported as not answered
KINDS = {"report": "Generate report", "performa": "Update data Performa"}
MONTHS = ("Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember")
WEEK_CHOICES = 8
MONTH_CHOICES = 6


def period_options(today: date) -> dict[str, list[tuple[str, str]]]:
    """The periods offered for a report: the current and previous ISO weeks, and the current and previous months. Values are what n8n expects."""
    weeks, monday = [], today - timedelta(days=today.weekday())
    for back in range(WEEK_CHOICES):
        iso = (monday - timedelta(weeks=back)).isocalendar()
        weeks.append((f"{iso.year}-W{iso.week:02d}", f"Week {iso.week} {iso.year}"))
    months, index = [], today.year * 12 + today.month - 1
    for back in range(MONTH_CHOICES):
        year, month = divmod(index - back, 12)
        months.append((f"{year}-{month + 1:02d}", f"{MONTHS[month]} {year}"))
    return {"week": weeks, "month": months}


def check_request(kind: str, bu: str, period: str, companies: list[str]) -> str:
    """Returns the period to store ('' for Performa). Raises ValueError with a message that is safe to show."""
    if kind not in KINDS:
        raise ValueError("Proses tidak dikenal.")
    if bu != "all" and bu not in companies:
        raise ValueError("Perusahaan tidak dikenal.")
    if kind == "performa":
        return ""
    try:
        generate_report.parse_period(period)
    except (ValueError, TypeError):
        raise ValueError("Periode tidak valid.")
    return period


def expected(bu: str, companies: list[str]) -> list[str]:
    return list(companies) if bu == "all" else [bu]


def derive(job: dict, companies: list[str], now: datetime, local_error: str = "") -> dict:
    """The state of one request: running, done, failed (some company reported a failure, or n8n answered with an error), or timeout.
    Returns {state, ok_companies, failures: [(company, message)], finished_at}."""
    wanted = expected(job["bu"], companies)
    got = {r["bu"]: r for r in job["results"]}
    failures = [(b, got[b]["message"]) for b in wanted if b in got and not got[b]["ok"]]
    oks = [b for b in wanted if b in got and got[b]["ok"]]
    finished = max((r["finished_at"] for r in job["results"]), default=None)
    complete = all(b in got for b in wanted)
    if local_error and not complete:
        state, failures = "failed", failures + [("", local_error)]
    elif complete:
        state = "failed" if failures else "done"
    elif (now - job["requested_at"]).total_seconds() > TIMEOUT_SECONDS:
        state = "timeout"
    else:
        state = "running"
    return {"state": state, "ok_companies": oks, "failures": failures, "finished_at": finished}


def outcome_text(job: dict, status: dict, names: dict) -> str:
    """One line for the history table and the card."""
    state = status["state"]
    label = lambda b: names.get(b, b) if b else ""
    if state == "running":
        return "Sedang berjalan"
    if state == "done":
        return "Berhasil"
    if state == "timeout":
        return "Tidak ada laporan dari n8n dalam 5 menit. Periksa eksekusi di n8n; data lama tidak berubah."
    parts = [f"{label(b)}: {m}".strip(": ") for b, m in status["failures"]]
    done = [label(b) for b in status["ok_companies"]]
    text = "Gagal. " + " | ".join(parts) if parts else "Gagal."
    if not text.endswith((".", "!", "?")):
        text += "."
    if done:
        text += " Berhasil untuk " + ", ".join(done) + "."
    return text


def duration_text(job: dict, status: dict) -> str:
    if status["finished_at"] is None or status["state"] in ("running", "timeout"):
        return "-"
    seconds = max(0, int((status["finished_at"] - job["requested_at"]).total_seconds()))
    minutes, rest = divmod(seconds, 60)
    return f"{minutes} menit {rest} detik" if minutes else f"{rest} detik"
