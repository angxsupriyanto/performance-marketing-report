"""Runs database/*.sql against a disposable PostgreSQL server.

Set REPORTS_TEST_ADMIN to libpq connection options for a superuser on a THROWAWAY server, e.g.
    REPORTS_TEST_ADMIN="host=127.0.0.1 port=54329 user=postgres"
The test skips when the variable is absent, and refuses to run if marketing_reports or any report_* role exists.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADMIN = os.environ.get("REPORTS_TEST_ADMIN", "")

try:
    import psycopg
except ImportError:  # pragma: no cover
    psycopg = None

SHA_A, SHA_B = "a" * 64, "b" * 64


def named(query: str) -> str:
    return re.sub(r"\$(\d+)", r"%(p\1)s", query)


def sql(name: str) -> str:
    return named((ROOT / "n8n" / "sql" / name).read_text(encoding="utf-8"))


@unittest.skipUnless(ADMIN and psycopg and shutil.which("psql"), "needs REPORTS_TEST_ADMIN, psycopg and psql")
class DatabaseTests(unittest.TestCase):
    @classmethod
    def admin(cls, dbname="postgres", autocommit=True):
        return psycopg.connect(f"{ADMIN} dbname={dbname}", autocommit=autocommit)

    @classmethod
    def psql(cls, dbname, *args):
        env = dict(os.environ)
        opts = dict(part.split("=", 1) for part in ADMIN.split())
        env.update(PGHOST=opts.get("host", ""), PGPORT=opts.get("port", "5432"), PGUSER=opts.get("user", "postgres"))
        result = subprocess.run(["psql", "-v", "ON_ERROR_STOP=1", "-q", "-d", dbname, *args], capture_output=True, text=True, env=env)
        assert result.returncode == 0, result.stderr
        return result

    @classmethod
    def setUpClass(cls):
        with cls.admin() as conn:
            exists = conn.execute("SELECT (SELECT count(*) FROM pg_database WHERE datname='marketing_reports') + (SELECT count(*) FROM pg_roles WHERE rolname LIKE 'report\\_%')").fetchone()[0]
        if exists:
            raise unittest.SkipTest("marketing_reports or report_* roles already exist; refusing to touch them")
        cls.psql("postgres", "-v", "writer_password=writer-pw", "-v", "reader_password=reader-pw", "-f", str(ROOT / "database/000_create_database_and_roles.sql"))
        cls.psql("marketing_reports", "-f", str(ROOT / "database/001_reports_schema.sql"))
        opts = ADMIN
        cls.writer = lambda self=None: psycopg.connect(f"{opts} dbname=marketing_reports user=report_writer password=writer-pw", autocommit=True)
        cls.reader = lambda self=None: psycopg.connect(f"{opts} dbname=marketing_reports user=report_reader password=reader-pw", autocommit=True)

    @classmethod
    def tearDownClass(cls):
        with cls.admin() as conn:
            conn.execute("DROP DATABASE IF EXISTS marketing_reports")
            for role in ("report_writer", "report_reader", "report_owner"):
                conn.execute(f"DROP ROLE IF EXISTS {role}")

    def run_params(self, period="2026-W39", sha=SHA_A, html="<html>numeric</html>", kind="week", bu="bu2"):
        start, end = ("2026-09-21", "2026-09-27") if kind == "week" else ("2026-09-01", "2026-09-30")
        values = [bu, period, kind, start, end, sha, "test", 10, 8, 2, json.dumps({"now": {}}), json.dumps({}), json.dumps({}), json.dumps(["executive_summary"]), html]
        return {f"p{i}": v for i, v in enumerate(values, 1)}

    def test_insert_is_idempotent_for_identical_input(self):
        with self.writer() as conn:
            first = conn.execute(sql("insert_run.sql"), self.run_params(period="2026-W40", sha=SHA_A)).fetchall()
            again = conn.execute(sql("insert_run.sql"), self.run_params(period="2026-W40", sha=SHA_A)).fetchall()
            changed = conn.execute(sql("insert_run.sql"), self.run_params(period="2026-W40", sha=SHA_B)).fetchall()
            count = conn.execute("SELECT count(*) FROM reports.report_runs WHERE period='2026-W40'").fetchone()[0]
        self.assertEqual((len(first), first[0][1]), (1, True))
        self.assertEqual((len(again), again[0][1], again[0][0]), (1, False, first[0][0]))
        self.assertEqual((changed[0][1], count), (True, 2))

    def test_constraints_reject_inconsistent_rows(self):
        with self.writer() as conn:
            for override in ({"bu": "BU2"}, {"period": "2026-W39", "kind": "month"}, {"period": "minggu-39"}, {"sha": "xyz"}):
                with self.assertRaises(psycopg.errors.CheckViolation, msg=override):
                    conn.execute(sql("insert_run.sql"), self.run_params(**override))

    def test_permissions_are_least_privilege_and_append_only(self):
        with self.writer() as conn:
            conn.execute(sql("insert_run.sql"), self.run_params(period="2026-W41"))
            for statement in ("UPDATE reports.report_runs SET bu='bu1'", "DELETE FROM reports.report_runs", "TRUNCATE reports.report_runs", "CREATE TABLE reports.x (a int)", "CREATE TABLE public.x (a int)", "DROP TABLE reports.report_runs"):
                with self.assertRaises(psycopg.errors.InsufficientPrivilege, msg=statement):
                    conn.execute(statement)
        with self.reader() as conn:
            self.assertGreaterEqual(conn.execute("SELECT count(*) FROM reports.latest_reports").fetchone()[0], 1)
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                conn.execute(sql("insert_run.sql"), self.run_params(period="2026-W41", sha=SHA_B))
        with self.admin() as conn:
            conn.execute("CREATE ROLE stranger LOGIN")
            try:
                with self.assertRaises(psycopg.OperationalError):
                    psycopg.connect(f"{ADMIN} dbname=marketing_reports user=stranger")
            finally:
                conn.execute("DROP ROLE stranger")
            roles = conn.execute("SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls FROM pg_roles WHERE rolname IN ('report_writer','report_reader')").fetchall()
        self.assertTrue(all(not any(flags) for _, *flags in roles))

    def test_latest_report_prefers_newest_run_and_newest_analysis(self):
        with self.writer() as conn:
            conn.execute(sql("insert_run.sql"), self.run_params(period="2026-09", kind="month", sha=SHA_A, html="<p>run1</p>"))
            run2 = conn.execute(sql("insert_run.sql"), self.run_params(period="2026-09", kind="month", sha=SHA_B, html="<p>run2</p>")).fetchone()[0]
            plain = conn.execute(sql("select_latest_report.sql"), {"p1": "bu2", "p2": "2026-09"}).fetchall()
            self.assertEqual(plain, [("<p>run2</p>", False)])
            latest = conn.execute(sql("select_latest_run.sql"), {"p1": "bu2", "p2": "2026-09"}).fetchall()
            self.assertEqual((latest[0][0], latest[0][4]), (run2, ["executive_summary"]))
            for text in ("first", "second"):
                saved = conn.execute(sql("insert_analysis.sql"), {"p1": str(run2), "p2": "tester", "p3": "model-x", "p4": "analysis_v1", "p5": json.dumps({"executive_summary": text}), "p6": f"<p>final {text}</p>"}).fetchall()
                self.assertEqual(saved[0][1], run2)
            shown = conn.execute(sql("select_latest_report.sql"), {"p1": "bu2", "p2": "2026-09"}).fetchall()
        self.assertEqual(shown, [("<p>final second</p>", True)])
        with self.assertRaises(psycopg.errors.ForeignKeyViolation):
            with self.writer() as conn:
                conn.execute(sql("insert_analysis.sql"), {"p1": "00000000-0000-0000-0000-000000000000", "p2": "t", "p3": "m", "p4": "v", "p5": "{}", "p6": "x"})

    def test_end_to_end_from_sheet_rows_to_stored_report(self):
        sys.path.insert(0, str(ROOT / "tests"))
        sys.path.insert(0, str(ROOT))
        import test_n8n
        from service import server
        from test_table_mode import LEADS
        flow = test_n8n.load("Report_Generate_v1.json")
        csv_items = test_n8n.run_code(test_n8n.node(flow, "Build CSV")["parameters"]["jsCode"], test_n8n.sheet_rows(LEADS),
                                      {"Normalize Plan": {"items": [{"plans": [{"bu": "bu2", "period": "2026-W39"}]}], "executed": True}})["result"]
        report = server.generate(csv_items[0]["json"]["csv"].encode(), "bu2", "2026-W39", False)
        prepared = test_n8n.run_code(test_n8n.node(flow, "Prepare Insert")["parameters"]["jsCode"], [report])["result"]
        params = {f"p{i}": v for i, v in enumerate(prepared[0]["json"]["params"], 1)}
        with self.writer() as conn:
            saved = conn.execute(sql("insert_run.sql"), params).fetchall()
            again = conn.execute(sql("insert_run.sql"), params).fetchall()
            stored = conn.execute("SELECT rows_in_bu, rows_without_bu, metrics->'now'->>'SQL Value', length(numeric_html) > 1000 FROM reports.report_runs WHERE run_id = %s", (saved[0][0],)).fetchone()
        self.assertEqual((saved[0][1], again[0][1], again[0][0]), (True, False, saved[0][0]))
        self.assertEqual(stored, (3, 0, "8000000", True))
        message = test_n8n.run_code(test_n8n.node(flow, "Compose Message")["parameters"]["jsCode"], [{"run_id": str(saved[0][0]), "inserted": True}],
                                    {"Prepare Insert": {"items": [p["json"] for p in prepared]}})["result"][0]["json"]["text"]
        self.assertIn("SQL Value Rp 8.000.000", message)


if __name__ == "__main__":
    unittest.main()
