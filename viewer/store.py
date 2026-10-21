"""Database access for the viewer. One short connection per request; every query is parameterized."""
from __future__ import annotations

import json
import os
from decimal import Decimal

import psycopg
from psycopg.rows import dict_row


class UserError(Exception):
    """A user or name change the rules refuse. The text is safe to show to an admin."""


USER_COLUMNS = "username, role, all_companies, companies, active, created_at, last_login_at"


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
                """SELECT l.run_id, l.bu, l.period, l.period_kind, l.period_start, l.period_end, l.generated_at, l.numeric_html AS html,
                          l.has_analysis, l.analysis_created_at, l.analysis, l.model, r.facts
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

    # ---- manual edits of analysis panels
    def latest_edits(self, run_id) -> list[dict]:
        """Newest edit row per panel of one run. body None means the AI version was restored."""
        with self._connect() as conn:
            return conn.execute(
                """SELECT DISTINCT ON (panel_key) panel_key, body, edited_by, created_at FROM reports.analysis_edits
                   WHERE run_id = %s ORDER BY panel_key, created_at DESC, edit_id""",
                (run_id,),
            ).fetchall()

    def add_edit(self, run_id, panel_key: str, body: str | None, edited_by: str) -> None:
        with self._connect() as conn:
            conn.execute("INSERT INTO reports.analysis_edits (run_id, panel_key, body, edited_by) VALUES (%s, %s, %s, %s)", (run_id, panel_key, body, edited_by))

    # ---- users
    def ensure_bootstrap_admin(self, password_hash: str) -> bool:
        """Creates the first admin from the old shared-password secret, only while there are no users at all."""
        with self._connect() as conn:
            row = conn.execute(
                """INSERT INTO reports.viewer_users (username, password_hash, role, all_companies)
                   SELECT 'admin', %s, 'admin', true WHERE NOT EXISTS (SELECT 1 FROM reports.viewer_users)
                   ON CONFLICT DO NOTHING RETURNING 1""",
                (password_hash,),
            ).fetchone()
        return row is not None

    def get_user(self, username: str) -> dict | None:
        with self._connect() as conn:
            return conn.execute(f"SELECT {USER_COLUMNS}, password_hash FROM reports.viewer_users WHERE username = %s", (username,)).fetchone()

    def list_users(self) -> list[dict]:
        with self._connect() as conn:
            return conn.execute(f"SELECT {USER_COLUMNS} FROM reports.viewer_users ORDER BY (role = 'admin') DESC, username").fetchall()

    def touch_login(self, username: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE reports.viewer_users SET last_login_at = now() WHERE username = %s", (username,))

    def create_user(self, username: str, password_hash: str, role: str, all_companies: bool, companies: list[str], active: bool) -> None:
        try:
            with self._connect() as conn:
                conn.execute(
                    """INSERT INTO reports.viewer_users (username, password_hash, role, all_companies, companies, active)
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    (username, password_hash, role, all_companies, companies, active),
                )
        except psycopg.errors.UniqueViolation:
            raise UserError("Username ini sudah dipakai. Pilih yang lain.")

    def update_user(self, username: str, password_hash: str | None, role: str, all_companies: bool, companies: list[str], active: bool) -> None:
        """Keeps at least one active admin: the check runs under a table lock, after the change, and rolls it back."""
        with psycopg.connect(self.conninfo, row_factory=dict_row) as conn:
            with conn.transaction():
                conn.execute("LOCK TABLE reports.viewer_users IN SHARE ROW EXCLUSIVE MODE")
                done = conn.execute(
                    """UPDATE reports.viewer_users SET role = %s, all_companies = %s, companies = %s, active = %s, updated_at = now(),
                              password_hash = coalesce(%s, password_hash) WHERE username = %s RETURNING 1""",
                    (role, all_companies, companies, active, password_hash, username),
                ).fetchone()
                if done is None:
                    raise UserError("Pengguna tidak ditemukan.")
                if conn.execute("SELECT count(*) AS n FROM reports.viewer_users WHERE role = 'admin' AND active").fetchone()["n"] < 1:
                    raise UserError("Tidak bisa dinonaktifkan atau diturunkan perannya: ini satu-satunya admin aktif.")

    # ---- company names
    def company_names(self) -> dict[str, str]:
        with self._connect() as conn:
            return {r["bu"]: r["display_name"] for r in conn.execute("SELECT bu, display_name FROM reports.company_names").fetchall()}

    def save_company_names(self, names: dict[str, str]) -> None:
        try:
            with psycopg.connect(self.conninfo, row_factory=dict_row) as conn:
                with conn.transaction():
                    # park the changing rows under unique temporary names so swapping two names does not trip the unique index
                    conn.execute("UPDATE reports.company_names SET display_name = '~' || bu WHERE bu = ANY(%s)", (list(names),))
                    for bu, name in names.items():
                        conn.execute(
                            """INSERT INTO reports.company_names (bu, display_name) VALUES (%s, %s)
                               ON CONFLICT (bu) DO UPDATE SET display_name = EXCLUDED.display_name, updated_at = now()""",
                            (bu, name),
                        )
        except psycopg.errors.UniqueViolation:
            raise UserError("Kedua perusahaan tidak boleh memakai nama yang sama.")

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
