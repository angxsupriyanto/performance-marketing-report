"""Database access for the viewer. One short connection per request; every query is parameterized."""
from __future__ import annotations

import json
import os
from decimal import Decimal

import psycopg
from psycopg.rows import dict_row


class Store:
    def __init__(self, conninfo: str):
        self.conninfo = conninfo

    @classmethod
    def from_env(cls, read_secret) -> "Store":
        password_file = os.environ.get("VIEWER_DB_PASSWORD_FILE")
        password = read_secret(password_file) if password_file else os.environ.get("VIEWER_DB_PASSWORD", "")
        parts = {
            "host": os.environ.get("VIEWER_DB_HOST", "n8n-postgres"),
            "port": os.environ.get("VIEWER_DB_PORT", "5432"),
            "dbname": os.environ.get("VIEWER_DB_NAME", "marketing_reports"),
            "user": os.environ.get("VIEWER_DB_USER", "report_viewer"),
            "password": password,
            "connect_timeout": "5",
            "application_name": "report-viewer",
        }
        return cls(psycopg.conninfo.make_conninfo(**parts))

    def _connect(self):
        return psycopg.connect(self.conninfo, row_factory=dict_row, autocommit=True)

    def list_reports(self) -> list[dict]:
        with self._connect() as conn:
            return conn.execute(
                """SELECT bu, period, period_kind, period_start, period_end, generated_at, has_analysis, analysis_created_at
                   FROM reports.latest_reports ORDER BY period_start DESC, bu"""
            ).fetchall()

    def get_report(self, bu: str, period: str) -> dict | None:
        with self._connect() as conn:
            return conn.execute(
                """SELECT l.run_id, l.bu, l.period, l.period_kind, l.period_start, l.period_end, l.generated_at, l.html,
                          l.has_analysis, l.analysis_created_at, r.facts
                   FROM reports.latest_reports l JOIN reports.report_runs r USING (run_id)
                   WHERE l.bu = %s AND l.period = %s""",
                (bu, period),
            ).fetchone()

    def latest_analysis_time(self, bu: str, period: str):
        with self._connect() as conn:
            row = conn.execute("SELECT analysis_created_at FROM reports.latest_reports WHERE bu = %s AND period = %s", (bu, period)).fetchone()
        return row["analysis_created_at"] if row else None

    def latest_targets(self, bu: str) -> list[dict]:
        with self._connect() as conn:
            return conn.execute(
                "SELECT scope, product, period_key, unit, amount, recorded_at FROM reports.targets_latest WHERE bu = %s", (bu,)
            ).fetchall()

    def target_history(self, bu: str, limit: int = 60) -> list[dict]:
        with self._connect() as conn:
            return conn.execute(
                """SELECT scope, product, period_key, unit, amount, recorded_at FROM reports.target_entries
                   WHERE bu = %s ORDER BY recorded_at DESC, entry_id LIMIT %s""",
                (bu, limit),
            ).fetchall()

    def add_targets(self, bu: str, entries: list[tuple[str, str | None, str, str, Decimal]]) -> None:
        """All entries of one save go in one transaction, so a failure never leaves a half-saved form."""
        with psycopg.connect(self.conninfo, row_factory=dict_row) as conn:
            with conn.transaction():
                for scope, product, period_key, unit, amount in entries:
                    conn.execute(
                        "INSERT INTO reports.target_entries (bu, scope, product, period_key, unit, amount) VALUES (%s, %s, %s, %s, %s, %s)",
                        (bu, scope, product, period_key, unit, amount),
                    )

    def ping(self) -> bool:
        try:
            with self._connect() as conn:
                conn.execute("SELECT 1")
            return True
        except psycopg.Error:
            return False


def facts_of(report: dict) -> dict:
    facts = report["facts"]
    return json.loads(facts) if isinstance(facts, str) else facts
