"""Runs database/*.sql against a disposable PostgreSQL server.

Set REPORTS_TEST_ADMIN to libpq connection options for a superuser on a THROWAWAY server, e.g.
    REPORTS_TEST_ADMIN="host=127.0.0.1 port=54329 user=postgres"
The test skips when the variable is absent, and refuses to run if marketing_reports or any report_* role exists.
"""
import json
import os
from decimal import Decimal
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
        cls.psql("marketing_reports", "-v", "viewer_password=viewer-pw", "-f", str(ROOT / "database/002_targets_and_viewer.sql"))
        cls.psql("marketing_reports", "-f", str(ROOT / "database/003_run_idempotency_includes_generator.sql"))
        cls.psql("marketing_reports", "-f", str(ROOT / "database/003_run_idempotency_includes_generator.sql"))  # safe to repeat
        cls.psql("marketing_reports", "-f", str(ROOT / "database/004_users_and_company_names.sql"))
        cls.psql("marketing_reports", "-f", str(ROOT / "database/004_users_and_company_names.sql"))  # safe to repeat
        cls.psql("marketing_reports", "-f", str(ROOT / "database/005_analysis_edits.sql"))
        cls.psql("marketing_reports", "-f", str(ROOT / "database/005_analysis_edits.sql"))  # safe to repeat
        cls.psql("marketing_reports", "-f", str(ROOT / "database/006_budget.sql"))
        cls.psql("marketing_reports", "-f", str(ROOT / "database/006_budget.sql"))  # safe to repeat
        opts = ADMIN
        cls.writer = lambda self=None: psycopg.connect(f"{opts} dbname=marketing_reports user=report_writer password=writer-pw", autocommit=True)
        cls.reader = lambda self=None: psycopg.connect(f"{opts} dbname=marketing_reports user=report_reader password=reader-pw", autocommit=True)
        cls.viewer = lambda self=None: psycopg.connect(f"{opts} dbname=marketing_reports user=report_viewer password=viewer-pw", autocommit=True)

    @classmethod
    def tearDownClass(cls):
        with cls.admin() as conn:
            conn.execute("DROP DATABASE IF EXISTS marketing_reports")
            for role in ("report_writer", "report_reader", "report_viewer", "report_owner"):
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

    def test_new_generator_code_adds_a_run_for_the_same_input_and_the_viewer_shows_it(self):
        old = self.run_params(period="2026-W45", sha=SHA_A, html="<p>old generator</p>")
        new = dict(old, p7="test+newcode", p15="<p>new generator</p>")
        with self.writer() as conn:
            first = conn.execute(sql("insert_run.sql"), old).fetchall()
            same = conn.execute(sql("insert_run.sql"), old).fetchall()
            upgraded = conn.execute(sql("insert_run.sql"), new).fetchall()
            again = conn.execute(sql("insert_run.sql"), new).fetchall()
            shown = conn.execute(sql("select_latest_report.sql"), {"p1": "bu2", "p2": "2026-W45"}).fetchall()
        self.assertEqual((first[0][1], same[0][1], same[0][0]), (True, False, first[0][0]))
        self.assertEqual((upgraded[0][1], upgraded[0][0] != first[0][0], again[0][1], again[0][0]), (True, True, False, upgraded[0][0]))
        self.assertEqual(shown, [("<p>new generator</p>", False)])

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

    def test_viewer_can_add_targets_but_never_change_or_remove_them(self):
        insert = "INSERT INTO reports.target_entries (bu, scope, product, period_key, unit, amount) VALUES (%s, %s, %s, %s, %s, %s)"
        with self.viewer() as conn:
            conn.execute(insert, ("bu1", "hardware_month", "Dashcam", "2026-10", "idr", 150000000))
            conn.execute(insert, ("bu1", "hardware_month", "Dashcam", "2026-10", "idr", 175000000.5))
            conn.execute(insert, ("bu1", "hardware_month", "Dashcam", "2026-12", "idr", 200000000))
            conn.execute(insert, ("bu2", "semester", None, "2026-S2", "count", 24))
            latest = dict(((row[0], row[1], row[2]), row[3]) for row in conn.execute("SELECT bu, product, period_key, amount FROM reports.targets_latest").fetchall())
            history = conn.execute("SELECT count(*) FROM reports.target_entries WHERE bu = 'bu1' AND product = 'Dashcam' AND period_key = '2026-10'").fetchone()[0]
            for statement in ("UPDATE reports.target_entries SET amount = 1", "DELETE FROM reports.target_entries", "TRUNCATE reports.target_entries", "CREATE TABLE reports.y (a int)", "INSERT INTO reports.report_analyses (run_id, model, prompt_version, analysis, final_html) VALUES (gen_random_uuid(), 'm', 'v', '{}', 'x')"):
                with self.assertRaises(psycopg.errors.InsufficientPrivilege, msg=statement):
                    conn.execute(statement)
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                conn.execute(sql("insert_run.sql"), self.run_params(period="2026-W41", sha=SHA_B))
            self.assertGreaterEqual(conn.execute("SELECT count(*) FROM reports.latest_reports").fetchone()[0], 0)
        self.assertEqual(float(latest[("bu1", "Dashcam", "2026-10")]), 175000000.5)
        self.assertEqual(float(latest[("bu1", "Dashcam", "2026-12")]), 200000000)
        self.assertEqual(float(latest[("bu2", None, "2026-S2")]), 24)
        self.assertEqual(history, 2)
        with self.writer() as conn, self.reader() as other:
            for connection in (conn, other):
                self.assertGreaterEqual(connection.execute("SELECT count(*) FROM reports.targets_latest").fetchone()[0], 3)
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    connection.execute(insert, ("bu1", "hardware_month", "Fuel", "2026-10", "idr", 1))

    def test_target_rows_must_have_a_consistent_shape(self):
        insert = "INSERT INTO reports.target_entries (bu, scope, product, period_key, unit, amount) VALUES (%s, %s, %s, %s, %s, %s)"
        bad = [
            ("BU1", "hardware_month", "Dashcam", "2026-10", "idr", 1),       # bu must be lowercase
            ("bu1", "hardware_month", None, "2026-10", "idr", 1),            # hardware needs a product
            ("bu1", "hardware_month", "Dashcam", "2026-13", "idr", 1),       # no month 13
            ("bu1", "hardware_month", "Dashcam", "2026-S1", "idr", 1),
            ("bu1", "hardware_month", "Dashcam", "2026-10", "count", 1),     # hardware targets are rupiah
            ("bu1", "semester", "Dashcam", "2026-S1", "idr", 1),             # semester has no product
            ("bu1", "semester", None, "2026-S3", "idr", 1),
            ("bu1", "semester", None, "2026-10", "idr", 1),
            ("bu1", "semester", None, "2026-S1", "idr", -5),                 # no negative targets
            ("bu1", "year", None, "2026", "idr", 1),                         # year is the sum of semesters
        ]
        with self.viewer() as conn:
            for row in bad:
                with self.assertRaises(psycopg.errors.CheckViolation, msg=row):
                    conn.execute(insert, row)

    def test_viewer_store_reads_reports_and_saves_targets_in_one_transaction(self):
        sys.path.insert(0, str(ROOT))
        from viewer.store import Store
        store = Store(f"{ADMIN} dbname=marketing_reports user=report_viewer password=viewer-pw")
        with self.writer() as conn:
            run_id = conn.execute(sql("insert_run.sql"), self.run_params(period="2026-W43", sha=SHA_A, html="<p>viewer run</p>")).fetchone()[0]
        listed = [r for r in store.list_reports() if r["period"] == "2026-W43"]
        self.assertEqual((len(listed), listed[0]["has_analysis"]), (1, False))
        report = store.get_report("bu2", "2026-W43")
        self.assertEqual((str(report["run_id"]), report["html"], report["facts"]), (str(run_id), "<p>viewer run</p>", {}))
        self.assertIsNone(store.get_report("bu2", "2030-W01"))
        self.assertIsNone(store.latest_analysis_time("bu2", "2026-W43"))
        with self.writer() as conn:
            conn.execute(sql("insert_analysis.sql"), {"p1": str(run_id), "p2": "t", "p3": "m", "p4": "v", "p5": "{}", "p6": "<p>final</p>"})
        self.assertIsNotNone(store.latest_analysis_time("bu2", "2026-W43"))
        shown = store.get_report("bu2", "2026-W43")
        self.assertEqual((shown["html"], shown["analysis"]), ("<p>viewer run</p>", {}))  # the viewer draws analysis itself; numeric_html carries the view
        before = len(store.target_history("bu1"))
        with self.assertRaises(psycopg.errors.CheckViolation):
            store.add_targets("bu1", [("hardware_month", "Fuel", "2026-10", "idr", 5), ("hardware_month", "Fuel", "2026-13", "idr", 6)])
        self.assertEqual(len(store.target_history("bu1")), before)  # the first row was rolled back with the second
        store.add_targets("bu1", [("hardware_month", "Fuel", "2026-10", "idr", 5)])
        self.assertEqual([(r["product"], r["amount"]) for r in store.latest_targets("bu1") if r["product"] == "Fuel"], [("Fuel", Decimal("5.00"))])
        self.assertTrue(store.ping())

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


    # ---- viewer users and company names (004), through the real Store class
    def admin_db(self):
        return self.admin("marketing_reports")

    def viewer_store(self):
        from viewer.store import Store
        with self.admin_db() as conn:  # these tests share one database, so each starts from empty user and name tables
            conn.execute("TRUNCATE reports.viewer_users, reports.company_names")
        return Store(f"{ADMIN} dbname=marketing_reports user=report_viewer password=viewer-pw")

    def test_users_table_enforces_shape_and_the_viewer_role_cannot_delete(self):
        import psycopg.errors as pe
        store = self.viewer_store()
        hash_ = "scrypt$1$1$1$c2FsdA$ZGlnZXN0"
        self.assertTrue(store.ensure_bootstrap_admin(hash_))
        self.assertFalse(store.ensure_bootstrap_admin(hash_))  # only while the table is empty
        admin = store.get_user("admin")
        self.assertEqual((admin["role"], admin["all_companies"], admin["companies"], admin["active"]), ("admin", True, [], True))
        store.create_user("andi", hash_, "user", False, ["bu1"], True)
        with self.assertRaises(Exception) as ctx:
            store.create_user("andi", hash_, "user", True, [], True)
        self.assertIn("sudah dipakai", str(ctx.exception))
        for bad in (("x1", "plain", "user", True, [], True), ("badshape", hash_, "user", False, [], True), ("adminlimited", hash_, "admin", False, ["bu1"], True), ("UPPER", hash_, "user", True, [], True)):
            with self.assertRaises((pe.CheckViolation, pe.Error)):
                store.create_user(*bad)
        with self.viewer() as conn:
            for sql in ("DELETE FROM reports.viewer_users", "TRUNCATE reports.viewer_users", "DELETE FROM reports.company_names"):
                with self.assertRaises(pe.InsufficientPrivilege):
                    conn.execute(sql)
        for role in (self.writer, self.reader):
            with role() as conn, self.assertRaises(pe.InsufficientPrivilege):
                conn.execute("SELECT * FROM reports.viewer_users")

    def test_last_active_admin_rule_and_password_update_in_the_real_store(self):
        store = self.viewer_store()
        hash_ = "scrypt$1$1$1$c2FsdA$ZGlnZXN0"
        store.ensure_bootstrap_admin(hash_)
        from viewer.store import UserError
        with self.assertRaises(UserError):
            store.update_user("admin", None, "admin", True, [], False)
        self.assertTrue(store.get_user("admin")["active"])  # rolled back
        store.create_user("bos", hash_, "admin", True, [], True)
        store.update_user("admin", "scrypt$2$2$2$c2FsdA$bmV3", "admin", True, [], False)
        self.assertEqual(store.get_user("admin")["password_hash"], "scrypt$2$2$2$c2FsdA$bmV3")
        with self.assertRaises(UserError):
            store.update_user("bos", None, "user", True, [], True)  # would leave no admin
        self.assertEqual(store.get_user("bos")["role"], "admin")
        with self.assertRaises(UserError):
            store.update_user("ghost", None, "user", True, [], True)
        store.touch_login("bos")
        self.assertIsNotNone(store.get_user("bos")["last_login_at"])

    def test_company_names_upsert_swap_and_unique_ignoring_case(self):
        from viewer.store import UserError
        store = self.viewer_store()
        store.save_company_names({"bu1": "McEasy", "bu2": "LOL"})
        self.assertEqual(store.company_names(), {"bu1": "McEasy", "bu2": "LOL"})
        store.save_company_names({"bu1": "LOL", "bu2": "McEasy"})  # a swap must not trip the unique index
        self.assertEqual(store.company_names(), {"bu1": "LOL", "bu2": "McEasy"})
        with self.assertRaises(UserError):
            store.save_company_names({"bu1": "same", "bu2": "SAME"})
        self.assertEqual(store.company_names(), {"bu1": "LOL", "bu2": "McEasy"})  # nothing half saved

    def test_analysis_edits_are_append_only_for_the_viewer_and_tied_to_a_run(self):
        import psycopg.errors as pe
        from viewer.store import Store
        with self.writer() as conn:
            run_id = conn.execute(sql("insert_run.sql"), self.run_params(period="2026-W47", sha=SHA_A)).fetchall()[0][0]
        store = self.viewer_store()
        store.add_edit(run_id, "executive_summary", "versi satu", "admin")
        store.add_edit(run_id, "executive_summary", "versi dua", "admin")
        store.add_edit(run_id, "hardware_dashcam", None, "admin")  # restore marker
        newest = {e["panel_key"]: e for e in store.latest_edits(run_id)}
        self.assertEqual((newest["executive_summary"]["body"], newest["hardware_dashcam"]["body"]), ("versi dua", None))
        with self.admin_db() as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM reports.analysis_edits").fetchone()[0], 3)  # every version kept
        with self.viewer() as conn:
            for statement in ("UPDATE reports.analysis_edits SET body = 'x'", "DELETE FROM reports.analysis_edits", "TRUNCATE reports.analysis_edits"):
                with self.assertRaises(pe.InsufficientPrivilege):
                    conn.execute(statement)
        for bad in ((run_id, "Bad Key", "x", "admin"), (run_id, "executive_summary", "", "admin"), (run_id, "executive_summary", "x" * 4001, "admin"), (run_id, "executive_summary", "x", ""),
                    ("00000000-0000-0000-0000-000000000000", "executive_summary", "x", "admin")):
            with self.assertRaises((pe.CheckViolation, pe.ForeignKeyViolation)):
                store.add_edit(*bad)
        with self.writer() as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM reports.analysis_edits").fetchone()[0], 3)  # writer reads them
            with self.assertRaises(pe.InsufficientPrivilege):
                conn.execute("INSERT INTO reports.analysis_edits (run_id, panel_key, body, edited_by) VALUES (%s, 'a', 'b', 'c')", (run_id,))

    def test_budget_snapshots_are_append_only_checked_and_guarded_against_stale_saves(self):
        import psycopg.errors as pe
        from datetime import date
        store = self.viewer_store()
        data = {"campaigns": {"Alpha": {"budget": 6000000, "month_spend": 3000000, "weeks": {"2026-W42": 1000000}}}}
        self.assertTrue(store.add_budget_snapshot("bu1", "2026-10", "", 10000000, date(2026, 10, 18), data, "admin"))
        first = store.budget_snapshots("bu1", ["2026-10"])["2026-10"]
        self.assertEqual((len(first), first[0]["total_budget"], first[0]["spend_as_of"], first[0]["data"]["campaigns"]["Alpha"]["weeks"]["2026-W42"]), (1, 10000000, date(2026, 10, 18), 1000000))
        self.assertFalse(store.add_budget_snapshot("bu1", "2026-10", "", 1, None, data, "admin"))  # a form opened before the first save is stale
        self.assertTrue(store.add_budget_snapshot("bu1", "2026-10", str(first[0]["snapshot_id"]), 12000000, date(2026, 10, 20), data, "admin"))
        history = store.budget_history("bu1")
        self.assertEqual([h["total_budget"] for h in history], [12000000, 10000000])  # newest first, both kept
        self.assertEqual(store.budget_snapshots("bu2", ["2026-10"])["2026-10"], [])
        self.assertEqual(store.latest_view_html("bu1"), None)
        with self.viewer() as conn:
            for statement in ("UPDATE reports.budget_snapshots SET total_budget = 1", "DELETE FROM reports.budget_snapshots", "TRUNCATE reports.budget_snapshots"):
                with self.assertRaises(pe.InsufficientPrivilege):
                    conn.execute(statement)
        for bad in (("bu1", "2026-13", None, None, data), ("BU 1", "2026-10", None, None, data), ("bu1", "2026-10", -5, None, data), ("bu1", "2026-10", None, None, {"nope": {}})):
            with self.assertRaises(pe.CheckViolation):
                store.add_budget_snapshot(bad[0], bad[1], str(history[0]["snapshot_id"]) if bad[:2] == ("bu1", "2026-10") else "", bad[2], bad[3], bad[4], "admin")
        with self.writer() as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM reports.budget_snapshots").fetchone()[0], 2)
            with self.assertRaises(pe.InsufficientPrivilege):
                conn.execute("INSERT INTO reports.budget_snapshots (bu, month, data, saved_by) VALUES ('bu1', '2026-10', '{\"campaigns\": {}}', 'x')")


if __name__ == "__main__":
    unittest.main()
