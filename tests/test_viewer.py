import http.client
import json
import re
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlencode

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from test_table_mode import LEADS, run, write_table  # noqa: E402
from viewer import app, auth, targets  # noqa: E402
from viewer.store import UserError  # noqa: E402

PASSWORD = "correct horse battery"
SECRET = b"s" * 40
UTC = timezone.utc


def generated(bu="bu1", period="2026-W39"):
    with tempfile.TemporaryDirectory() as tmp:
        table, out = Path(tmp) / "t.csv", Path(tmp) / "r.html"
        write_table(table, LEADS)
        assert run("--table", table, "--bu", bu, "--period", period, "--output", out).returncode == 0
        return out.read_text(), json.loads(out.with_suffix(".facts.json").read_text())


class FakeStore:
    """In-memory stand-in with the same methods as viewer.store.Store."""

    def __init__(self):
        self.html = {bu: generated(bu) for bu in ("bu1", "bu2")}
        self.entries = []
        self.analysis_at = {"bu1": None, "bu2": None}
        self.analysis = {}
        self.legacy = False
        self.fail_writes = False
        self.down = False
        self.users = {}
        self.names = {}
        self.edits = []
        self.model = {"bu1": "claude-sonnet-5-5", "bu2": "claude-sonnet-5-5"}

    def _check(self):
        if self.down:
            raise RuntimeError("database down")

    def list_reports(self):
        self._check()
        base = datetime(2026, 10, 20, 16, 11, tzinfo=UTC)
        return [{"bu": bu, "period": "2026-W39", "period_kind": "week", "period_start": datetime(2026, 9, 21).date(), "period_end": datetime(2026, 9, 27).date(),
                 "generated_at": base, "has_analysis": self.analysis_at[bu] is not None, "analysis_created_at": self.analysis_at[bu]} for bu in ("bu1", "bu2")]

    def get_report(self, bu, period):
        self._check()
        if period != "2026-W39" or bu not in self.html:
            return None
        html, facts = self.html[bu]
        if self.legacy:
            html = "<html><body>laporan lama</body></html>"
        return {"run_id": "r1", "bu": bu, "period": period, "period_kind": "week", "period_start": datetime(2026, 9, 21).date(), "period_end": datetime(2026, 9, 27).date(),
                "generated_at": datetime(2026, 10, 20, 16, 11, tzinfo=UTC), "html": html, "has_analysis": self.analysis_at[bu] is not None,
                "analysis_created_at": self.analysis_at[bu], "analysis": self.analysis.get(bu), "model": self.model[bu], "facts": facts}

    def latest_analysis_time(self, bu, period):
        return self.analysis_at[bu]

    def latest_targets(self, bu):
        self._check()
        latest = {}
        for e in self.entries:
            if e["bu"] == bu:
                latest[(e["scope"], e["product"], e["period_key"])] = e
        return list(latest.values())

    def target_history(self, bu, limit=60):
        return [e for e in reversed(self.entries) if e["bu"] == bu][:limit]

    def add_targets(self, bu, entries):
        if self.fail_writes:
            raise RuntimeError("write failed")
        for scope, product, key, unit, amount in entries:
            self.entries.append({"bu": bu, "scope": scope, "product": product, "period_key": key, "unit": unit, "amount": amount, "recorded_at": datetime.now(UTC)})

    def ping(self):
        return not self.down

    def latest_edits(self, run_id):
        self._check()
        newest = {}
        for e in self.edits:
            if e["run_id"] == run_id:
                newest[e["panel_key"]] = e
        return list(newest.values())

    def add_edit(self, run_id, panel_key, body, edited_by):
        if self.fail_writes:
            raise RuntimeError("write failed")
        self.edits.append({"run_id": run_id, "panel_key": panel_key, "body": body, "edited_by": edited_by, "created_at": datetime.now(UTC)})

    # ---- users and company names, same rules as the real Store
    def ensure_bootstrap_admin(self, password_hash):
        self._check()
        if self.users:
            return False
        self.users["admin"] = {"username": "admin", "password_hash": password_hash, "role": "admin", "all_companies": True, "companies": [], "active": True,
                               "created_at": datetime.now(UTC), "last_login_at": None}
        return True

    def get_user(self, username):
        self._check()
        row = self.users.get(username)
        return dict(row) if row else None

    def list_users(self):
        self._check()
        return sorted((dict(u) for u in self.users.values()), key=lambda u: (u["role"] != "admin", u["username"]))

    def touch_login(self, username):
        self.users[username]["last_login_at"] = datetime(2026, 10, 21, 9, 5, tzinfo=UTC)

    def create_user(self, username, password_hash, role, all_companies, companies, active):
        self._check()
        if username in self.users:
            raise UserError("Username ini sudah dipakai. Pilih yang lain.")
        self.users[username] = {"username": username, "password_hash": password_hash, "role": role, "all_companies": all_companies, "companies": companies,
                                "active": active, "created_at": datetime.now(UTC), "last_login_at": None}

    def update_user(self, username, password_hash, role, all_companies, companies, active):
        self._check()
        if username not in self.users:
            raise UserError("Pengguna tidak ditemukan.")
        before = dict(self.users[username])
        self.users[username].update(role=role, all_companies=all_companies, companies=companies, active=active)
        if password_hash:
            self.users[username]["password_hash"] = password_hash
        if not any(u["role"] == "admin" and u["active"] for u in self.users.values()):
            self.users[username] = before
            raise UserError("Tidak bisa dinonaktifkan atau diturunkan perannya: ini satu-satunya admin aktif.")

    def company_names(self):
        self._check()
        return dict(self.names)

    def save_company_names(self, names):
        self._check()
        if len({n.lower() for n in names.values()}) < len(names):
            raise UserError("Kedua perusahaan tidak boleh memakai nama yang sama.")
        self.names.update(names)


class FakeN8n(BaseHTTPRequestHandler):
    calls = []
    status = 200
    on_call = None

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        FakeN8n.calls.append({"headers": dict(self.headers), "body": json.loads(body)})
        if FakeN8n.on_call:
            FakeN8n.on_call(json.loads(body))
        payload = json.dumps({"message": "Jawaban model bukan JSON"} if FakeN8n.status >= 400 else {"ok": True}).encode()
        self.send_response(FakeN8n.status)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class ViewerCase(unittest.TestCase):
    """Server, fake store and helpers shared by the viewer test files; holds no tests itself."""

    @classmethod
    def setUpClass(cls):
        cls.n8n = HTTPServer(("127.0.0.1", 0), FakeN8n)
        threading.Thread(target=cls.n8n.serve_forever, daemon=True).start()
        cls.hash = auth.hash_password(PASSWORD)

    @classmethod
    def tearDownClass(cls):
        cls.n8n.shutdown()

    def setUp(self):
        self.store = FakeStore()
        FakeN8n.calls, FakeN8n.status, FakeN8n.on_call = [], 200, None
        cfg = app.Config(password_hash=self.hash, session_secret=SECRET, store=self.store, n8n_url=f"http://127.0.0.1:{self.n8n.server_port}/webhook/report-analysis",
                         n8n_header="Authorization", n8n_prefix="Bearer ", n8n_token="n8n-token-123", secure_cookie=True, trust_proxy=True)
        self.server = app.make_server(cfg, "127.0.0.1", 0)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.shutdown)
        self.port = self.server.server_address[1]
        self.cookie = ""
        self.limiter = self.server.RequestHandlerClass.limiter

    def call(self, method, path, body=None, headers=None, cookie=True, ip="10.0.0.1"):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        hdrs = {"CF-Connecting-IP": ip, "Host": "officehour.pesankopi.com", **(headers or {})}
        if cookie and self.cookie:
            hdrs["Cookie"] = f"vw_session={self.cookie}"
        if isinstance(body, dict):
            body = urlencode(body)
            hdrs.setdefault("Content-Type", "application/x-www-form-urlencoded")
        conn.request(method, path, body=body, headers=hdrs)
        response = conn.getresponse()
        data = response.read().decode("utf-8")
        conn.close()
        return response, data

    def login(self, password=PASSWORD, ip="10.0.0.1", username="admin"):
        self.cookie = ""
        response, data = self.call("POST", "/login", {"username": username, "password": password}, cookie=False, ip=ip)
        cookie = response.getheader("Set-Cookie")
        if cookie:
            self.cookie = re.match(r"vw_session=([^;]*)", cookie).group(1)
        return response, data

    def csrf(self):
        return auth.read_session(SECRET, self.cookie)[0]


class ViewerTests(ViewerCase):
    # ---- login and sessions
    def test_everything_but_health_and_login_needs_a_session(self):
        for path in ("/", "/report/bu1/2026-W39", "/targets", "/api/analysis/status?bu=bu1&period=2026-W39"):
            response, _ = self.call("GET", path, cookie=False)
            self.assertEqual((response.status, response.getheader("Location")), (303, "/login"), path)
        response, _ = self.call("POST", "/api/analysis", {"bu": "bu1", "period": "2026-W39"}, cookie=False)
        self.assertEqual(response.status, 303)
        response, body = self.call("GET", "/healthz", cookie=False)
        self.assertEqual((response.status, json.loads(body)), (200, {"status": "ok", "database": True}))

    def test_wrong_password_is_refused_and_five_failures_lock_even_the_right_password(self):
        response, body = self.login("wrong password!!")
        self.assertEqual(response.status, 401)
        self.assertIn("Username atau password salah", body)
        self.assertIsNone(response.getheader("Set-Cookie"))
        for _ in range(4):
            response, body = self.login("wrong password!!")
        self.assertEqual(response.status, 401)
        self.assertIn("Terlalu banyak percobaan. Coba lagi dalam 5 menit.", body)
        response, body = self.login(PASSWORD)
        self.assertEqual(response.status, 429)
        self.assertIsNone(response.getheader("Set-Cookie"))
        self.assertIn("disabled", body)
        self.assertTrue(int(response.getheader("Retry-After")) > 0)
        other, _ = self.login(PASSWORD, ip="10.0.0.2")  # another address is not locked
        self.assertEqual(other.status, 303)

    def test_login_sets_a_hardened_session_cookie_and_logout_clears_it(self):
        response, _ = self.login()
        self.assertEqual((response.status, response.getheader("Location")), (303, "/"))
        flags = response.getheader("Set-Cookie")
        for part in ("HttpOnly", "Secure", "SameSite=Strict", "Path=/", "Max-Age=43200"):
            self.assertIn(part, flags)
        page, body = self.call("GET", "/")
        self.assertEqual(page.status, 200)
        for header, value in (("X-Frame-Options", "DENY"), ("X-Content-Type-Options", "nosniff"), ("Referrer-Policy", "same-origin"), ("Cache-Control", "no-store")):
            self.assertEqual(page.getheader(header), value)
        out, _ = self.call("POST", "/logout", {"csrf": self.csrf()})
        self.assertEqual(out.status, 303)
        self.assertIn("Max-Age=0", out.getheader("Set-Cookie"))

    def test_tampered_or_expired_sessions_are_rejected(self):
        self.login()
        response, _ = self.call("GET", "/")
        self.assertEqual(response.status, 200)
        self.cookie = self.cookie[:-3] + "AAA"
        self.assertEqual(self.call("GET", "/")[0].status, 303)
        old, _ = auth.new_session(SECRET, "admin", auth.credential_tag(self.hash), now=time.time() - auth.SESSION_SECONDS - 5)
        self.cookie = old
        self.assertEqual(self.call("GET", "/")[0].status, 303)
        other, _ = auth.new_session(b"x" * 40, "admin", auth.credential_tag(self.hash))
        self.cookie = other
        self.assertEqual(self.call("GET", "/")[0].status, 303)

    def test_posts_need_the_csrf_token_and_a_matching_origin(self):
        self.login()
        body = {"bu": "bu1", "period": "2026-W39"}
        self.assertEqual(self.call("POST", "/api/analysis", body)[0].status, 403)
        self.assertEqual(self.call("POST", "/api/analysis", body, {"X-CSRF-Token": "nope"})[0].status, 403)
        self.assertEqual(self.call("POST", "/api/analysis", body, {"X-CSRF-Token": self.csrf(), "Origin": "https://evil.example"})[0].status, 403)
        self.assertEqual(FakeN8n.calls, [])
        self.assertEqual(self.call("POST", "/login", {"username": "admin", "password": PASSWORD}, {"Origin": "https://evil.example"}, cookie=False)[0].status, 403)

    # ---- list and report
    def test_list_shows_both_reports_and_analysis_state(self):
        self.login()
        self.store.analysis_at["bu1"] = datetime(2026, 10, 20, 16, 30, tzinfo=UTC)
        _, body = self.call("GET", "/")
        soup = BeautifulSoup(body, "html.parser")
        rows = soup.select("tbody tr")
        self.assertEqual([r.select("td")[1].get_text() for r in rows], ["Perusahaan 1", "Perusahaan 2"])
        self.assertIn("Sudah ada", rows[0].get_text())
        self.assertIn("23.30 WIB", rows[0].get_text())
        self.assertIn("Belum ada", rows[1].get_text())
        self.assertIn("20 Okt 2026, 23.11 WIB", rows[0].get_text())
        self.assertEqual([a["href"] for a in soup.select("tbody a")], ["/report/bu1/2026-W39", "/report/bu2/2026-W39"])
        self.assertEqual(soup.select_one("h1").get_text(), "Daftar report")
        self.store.down = True
        response, body = self.call("GET", "/")
        self.assertEqual(response.status, 503)
        self.assertIn("Daftar report tidak bisa dimuat", body)

    def test_report_page_has_chrome_report_and_strict_csp(self):
        self.login()
        response, body = self.call("GET", "/report/bu1/2026-W39")
        self.assertEqual(response.status, 200)
        soup = BeautifulSoup(body, "html.parser")
        self.assertEqual(soup.select_one("h1.vw-h1").get_text(), "Report Perusahaan 1")
        self.assertIsNotNone(soup.select_one("#vw-analysis[data-state=none] button"))
        self.assertIn("Belum ada analisis", body)
        self.assertEqual([h.get_text() for h in soup.select("h2")], ["Report"])
        self.assertIn("Campaign Hardware", [h.get_text() for h in soup.select("h3")])
        self.assertEqual(len(soup.select(".hw-funnel-block")) + len(soup.select(".hardware-section")), 0)  # nothing of the old dashboard
        nonce = re.search(r"'nonce-([^']+)'", response.getheader("Content-Security-Policy")).group(1)
        self.assertTrue(all(t.get("nonce") == nonce for t in soup.find_all(["script", "style"])))
        csp = response.getheader("Content-Security-Policy")
        self.assertIn("default-src 'none'", csp)
        self.assertIn("frame-ancestors 'none'", csp)
        self.assertEqual(soup.select_one("meta[name=csrf]")["content"], self.csrf())

    def test_report_shows_the_latest_analysis_in_the_mockup_panels(self):
        self.login()
        self.store.analysis_at["bu1"] = datetime(2026, 10, 20, 16, 30, tzinfo=UTC)
        self.store.analysis["bu1"] = {"executive_summary": "SQL naik <b>tajam</b>", "hardware_summary": "Ringkasan hardware", "hardware_gps_tracker": "GPS memimpin"}
        _, body = self.call("GET", "/report/bu1/2026-W39")
        soup = BeautifulSoup(body, "html.parser")
        self.assertEqual(soup.select_one('[data-analysis="executive_summary"]').get_text(), "SQL naik <b>tajam</b>")
        self.assertNotIn("<b>tajam</b>", body)
        self.assertEqual(soup.select_one('[data-analysis="hardware_gps_tracker"]').get_text(), "GPS memimpin")
        self.assertEqual(soup.select_one('[data-analysis="hardware_fuel"]').get_text(), "Kosong sampai analisis dibuat.")
        self.assertIn("Analisis tersedia", body)

    def test_a_report_from_the_old_generator_asks_for_a_new_run_instead_of_showing_old_content(self):
        self.login()
        self.store.legacy = True
        response, body = self.call("GET", "/report/bu1/2026-W39")
        self.assertEqual(response.status, 200)
        self.assertIn("generator versi lama", body)
        self.assertNotIn("laporan lama", body)
        self.assertIn("Report Perusahaan 1", body)

    def test_target_load_failure_keeps_the_report_and_shows_the_mockup_message(self):
        self.login()
        original = self.store.latest_targets
        self.store.latest_targets = lambda bu: (_ for _ in ()).throw(RuntimeError("down"))
        response, body = self.call("GET", "/report/bu1/2026-W39")
        self.assertEqual(response.status, 200)
        self.assertEqual(body.count("Target tidak bisa dimuat. Database marketing_reports tidak menjawab. Muat ulang halaman ini."), 2)
        self.assertIn("Daftar SQL Week 39", body)

    def test_report_page_404_for_unknown_or_malformed(self):
        self.login()
        self.assertEqual(self.call("GET", "/report/bu1/2026-W40")[0].status, 404)
        self.assertEqual(self.call("GET", "/report/bu1/..%2Fx")[0].status, 404)
        self.assertEqual(self.call("GET", "/report/BU1;%20DROP%20TABLE/2026-W39")[0].status, 404)
        self.assertEqual(self.call("GET", "/nope")[0].status, 404)

    def test_targets_appear_in_the_report_once_saved(self):
        self.login()
        _, before = self.call("GET", "/report/bu1/2026-W39")
        self.assertIn("Target 2026 belum diatur", before)
        self.call("POST", "/targets/month", {"csrf": self.csrf(), "bu": "bu1", "month": "2026-09", "hw_0": "", "hw_1": "Rp 4.000.000", "hw_2": "", "hw_3": "", "hw_4": ""})
        self.call("POST", "/targets/year", {"csrf": self.csrf(), "bu": "bu1", "year": "2026", "sem1": "8.000.000", "sem2": "12.000.000"})
        _, after = self.call("GET", "/report/bu1/2026-W39")
        soup = BeautifulSoup(after, "html.parser")
        text = soup.get_text(" ")
        self.assertIn("Tercapai Rp 1.000.000 dari target Rp 12.000.000", text)
        self.assertIn("Tercapai Rp 1.000.000 dari target Rp 20.000.000", text)
        self.assertIn("5,0% dari target tahun", text)
        rows = soup.select("table")[1].select("tbody tr")
        self.assertEqual([c.get_text() for c in rows[1].select("td")][5:], ["Rp 4.000.000", "25,0%"])
        self.assertEqual([c.get_text() for c in rows[0].select("td")][5:], ["Belum diatur", "-"])
        self.assertIn("Total target September 2026", text)
        self.assertIn("25,0% dari target Rp 4.000.000", text)

    # ---- analysis button
    def test_analysis_button_calls_n8n_with_auth_and_target_numbers_then_reports_done(self):
        self.login()
        self.call("POST", "/targets/year", {"csrf": self.csrf(), "bu": "bu1", "year": "2026", "sem1": "8000000", "sem2": "12000000"})

        def n8n_saves(_):
            self.store.analysis_at["bu1"] = datetime.now(UTC)
        FakeN8n.on_call = n8n_saves
        response, body = self.call("POST", "/api/analysis", {"bu": "bu1", "period": "2026-W39"}, {"X-CSRF-Token": self.csrf()})
        self.assertEqual((response.status, json.loads(body)), (202, {"state": "running"}))
        for _ in range(50):
            state = json.loads(self.call("GET", "/api/analysis/status?bu=bu1&period=2026-W39")[1])
            if state["state"] != "running":
                break
            time.sleep(0.05)
        self.assertEqual(state, {"state": "done", "error": ""})
        call = FakeN8n.calls[0]
        self.assertEqual(call["headers"]["Authorization"], "Bearer n8n-token-123")
        self.assertEqual({k: call["body"][k] for k in ("bu", "period", "requested_by")}, {"bu": "bu1", "period": "2026-W39", "requested_by": "viewer"})
        context = call["body"]["targets"]
        self.assertEqual(context["unit"], "idr")
        self.assertEqual(context["semester"]["target"], 12000000)
        self.assertEqual(context["year"]["target"], 20000000)
        self.assertEqual(context["month"]["hardware"][1]["product"], "GPS Tracker")
        self.assertNotIn("Co1", json.dumps(call["body"]))
        self.assertIn("Analisis tersedia", self.call("GET", "/report/bu1/2026-W39")[1])

    def test_analysis_failure_from_n8n_is_reported_and_can_be_retried(self):
        self.login()
        FakeN8n.status = 500
        self.call("POST", "/api/analysis", {"bu": "bu2", "period": "2026-W39"}, {"X-CSRF-Token": self.csrf()})
        for _ in range(50):
            state = json.loads(self.call("GET", "/api/analysis/status?bu=bu2&period=2026-W39")[1])
            if state["state"] != "running":
                break
            time.sleep(0.05)
        self.assertEqual(state["state"], "failed")
        self.assertIn("n8n menjawab 500", state["error"])
        self.assertIn("Jawaban model bukan JSON", state["error"])
        page = self.call("GET", "/report/bu2/2026-W39")[1]
        self.assertIn("Analisis gagal", page)
        FakeN8n.status = 200
        again = self.call("POST", "/api/analysis", {"bu": "bu2", "period": "2026-W39"}, {"X-CSRF-Token": self.csrf()})[0]
        self.assertEqual(again.status, 202)

    def test_a_non_json_error_body_from_n8n_is_shown_not_hidden(self):
        class Plain(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                self.rfile.read(int(self.headers["Content-Length"]))
                payload = b"<html>Forbidden by gateway</html>"
                self.send_response(403)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        plain = HTTPServer(("127.0.0.1", 0), Plain)
        threading.Thread(target=plain.serve_forever, daemon=True).start()
        self.addCleanup(plain.shutdown)
        cfg = app.Config(password_hash=self.hash, session_secret=SECRET, store=self.store, n8n_url=f"http://127.0.0.1:{plain.server_port}/x",
                         n8n_header="Authorization", n8n_prefix="Bearer ", n8n_token="t" * 24, secure_cookie=True, trust_proxy=True)
        error = app.call_n8n(cfg, "bu1", "2026-W39", {})
        self.assertEqual(error, "n8n menjawab 403: <html>Forbidden by gateway</html>.")

    def test_a_running_analysis_blocks_a_second_start_and_unsaved_results_count_as_failure(self):
        self.login()
        release = threading.Event()
        FakeN8n.on_call = lambda _: release.wait(5)
        first = self.call("POST", "/api/analysis", {"bu": "bu1", "period": "2026-W39"}, {"X-CSRF-Token": self.csrf()})[0]
        second = self.call("POST", "/api/analysis", {"bu": "bu1", "period": "2026-W39"}, {"X-CSRF-Token": self.csrf()})[0]
        self.assertEqual((first.status, second.status), (202, 409))
        self.assertIn('data-state="running"', self.call("GET", "/report/bu1/2026-W39")[1])
        release.set()
        for _ in range(60):
            state = json.loads(self.call("GET", "/api/analysis/status?bu=bu1&period=2026-W39")[1])
            if state["state"] != "running":
                break
            time.sleep(0.05)
        self.assertEqual(state["state"], "failed")  # n8n answered 200 but no analysis row appeared
        self.assertIn("tidak tersimpan", state["error"])

    def test_analysis_rejects_bad_input_and_missing_reports(self):
        self.login()
        h = {"X-CSRF-Token": self.csrf()}
        self.assertEqual(self.call("POST", "/api/analysis", {"bu": "bu1", "period": "x"}, h)[0].status, 400)
        self.assertEqual(self.call("POST", "/api/analysis", {"bu": "BU1;", "period": "2026-W39"}, h)[0].status, 400)
        self.assertEqual(self.call("POST", "/api/analysis", {"bu": "bu1", "period": "2026-W11"}, h)[0].status, 404)

    # ---- targets page
    def test_targets_page_lists_the_right_fields_per_bu(self):
        self.login()
        soup = BeautifulSoup(self.call("GET", "/targets?bu=bu1")[1], "html.parser")
        self.assertEqual([l.get_text() for l in soup.select('form[action="/targets/month"] label')][1:], [f"Target {n} (Rp)" for n in ("Dashcam", "GPS Tracker", "Fuel", "MDVR", "OBD")])
        self.assertIn("Belum ada target tersimpan untuk Perusahaan 1", soup.get_text())
        bu2 = BeautifulSoup(self.call("GET", "/targets?bu=bu2")[1], "html.parser")
        self.assertIsNone(bu2.select_one('form[action="/targets/month"]'))
        self.assertIn("Perusahaan 2 tidak memakai target bulanan", bu2.get_text())
        labels = [l.get_text() for l in bu2.select('form[action="/targets/year"] label')]
        self.assertEqual(labels[1:], ["Target Semester 1, Januari sampai Juni (jumlah SQL Ecosystem)", "Target Semester 2, Juli sampai Desember (jumlah SQL Ecosystem)"])
        self.assertEqual(self.call("GET", "/targets?bu=bu9")[0].status, 404)

    def test_saving_targets_is_append_only_and_skips_unchanged_values(self):
        self.login()
        form = {"csrf": self.csrf(), "bu": "bu1", "month": "2026-10", "hw_0": "150.000.000", "hw_1": "", "hw_2": "", "hw_3": "", "hw_4": ""}
        response, _ = self.call("POST", "/targets/month", form)
        self.assertEqual((response.status, response.getheader("Location")), (303, "/targets?bu=bu1&year=2026&month=2026-10&saved=month"))
        again, _ = self.call("POST", "/targets/month", form)
        self.assertIn("saved=same", again.getheader("Location"))
        self.assertEqual(len(self.store.entries), 1)
        self.call("POST", "/targets/month", {**form, "hw_0": "175000000"})
        self.assertEqual([e["amount"] for e in self.store.entries], [Decimal(150000000), Decimal(175000000)])
        soup = BeautifulSoup(self.call("GET", "/targets?bu=bu1&month=2026-12&saved=month")[1], "html.parser")
        self.assertEqual(soup.select_one("#hw-0")["value"], "175.000.000")  # carried forward to later months
        self.assertIn("Target bulanan Perusahaan 1 tersimpan.", soup.get_text())
        self.assertEqual(len(soup.select(".vw-table tbody tr")), 2)
        self.call("POST", "/targets/month", {**form, "month": "2026-11", "hw_0": "0"})
        self.assertEqual(self.store.entries[-1]["amount"], 0)
        later = BeautifulSoup(self.call("GET", "/targets?bu=bu1&month=2026-12")[1], "html.parser")
        self.assertEqual(later.select_one("#hw-0")["value"], "")  # zero clears the target from that month on

    def test_invalid_target_input_saves_nothing_and_explains_which_field(self):
        self.login()
        response, body = self.call("POST", "/targets/month", {"csrf": self.csrf(), "bu": "bu1", "month": "2026-10", "hw_0": "1.000", "hw_1": "abc", "hw_2": "1,5", "hw_3": "", "hw_4": ""})
        self.assertEqual(response.status, 422)
        soup = BeautifulSoup(body, "html.parser")
        self.assertIn("Belum ada yang disimpan", soup.get_text())
        self.assertEqual(soup.select_one("#hw-1")["aria-invalid"], "true")
        self.assertEqual(soup.select_one("#hw-1")["value"], "abc")
        self.assertEqual(soup.select_one("#hw-2")["aria-invalid"], "true")
        self.assertEqual(self.store.entries, [])
        bad_month = self.call("POST", "/targets/month", {"csrf": self.csrf(), "bu": "bu1", "month": "2019-01", "hw_0": "1"})[0]
        self.assertEqual(bad_month.status, 400)
        self.assertEqual(self.call("POST", "/targets/month", {"csrf": self.csrf(), "bu": "bu2", "month": "2026-10"})[0].status, 400)

    def test_bu2_targets_are_counts_and_year_is_the_sum(self):
        self.login()
        self.call("POST", "/targets/year", {"csrf": self.csrf(), "bu": "bu2", "year": "2026", "sem1": "16", "sem2": "24"})
        self.assertEqual([(e["period_key"], e["unit"], e["amount"]) for e in self.store.entries], [("2026-S1", "count", 16), ("2026-S2", "count", 24)])
        bad = self.call("POST", "/targets/year", {"csrf": self.csrf(), "bu": "bu2", "year": "2026", "sem1": "1.5", "sem2": ""})[0]
        self.assertEqual(bad.status, 422)
        text = BeautifulSoup(self.call("GET", "/report/bu2/2026-W39")[1], "html.parser").get_text(" ")
        self.assertIn("1 SQL dari target 24 SQL", text)
        self.assertIn("1 SQL dari target 40 SQL", text)
        self.assertIn("2,5% dari target tahun", text)
        page = BeautifulSoup(self.call("GET", "/targets?bu=bu2")[1], "html.parser")
        self.assertIn("40 SQL", page.get_text())

    def test_a_database_failure_while_saving_keeps_the_typed_values(self):
        self.login()
        self.store.fail_writes = True
        response, body = self.call("POST", "/targets/year", {"csrf": self.csrf(), "bu": "bu1", "year": "2026", "sem1": "5000000", "sem2": ""})
        self.assertEqual(response.status, 503)
        self.assertIn("Target tidak tersimpan. Database marketing_reports tidak menjawab.", body)

    def test_nothing_sensitive_reaches_the_log(self):
        # The handler never writes request lines; only a method, first path segment, status and time.
        import io
        from contextlib import redirect_stdout
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            self.login("hunter2hunter2")
            self.login()
            self.call("GET", "/report/bu1/2026-W39")
        text = buffer.getvalue()
        self.assertNotIn("hunter2", text)
        self.assertNotIn(PASSWORD, text)
        self.assertNotIn("2026-W39", text)


class AuthUnitTests(unittest.TestCase):
    def test_hash_is_salted_and_rejects_short_passwords(self):
        a, b = auth.hash_password(PASSWORD), auth.hash_password(PASSWORD)
        self.assertNotEqual(a, b)
        self.assertTrue(auth.verify_password(PASSWORD, a) and auth.verify_password(PASSWORD, b))
        self.assertFalse(auth.verify_password("other password!!", a))
        self.assertFalse(auth.verify_password(PASSWORD, "garbage"))
        with self.assertRaises(ValueError):
            auth.hash_password("short")

    def test_limiter_window(self):
        now = [0.0]
        limiter = auth.LoginLimiter(clock=lambda: now[0])
        for _ in range(4):
            limiter.failed("a")
        self.assertEqual(limiter.retry_after("a"), 0)
        limiter.failed("a")
        self.assertGreater(limiter.retry_after("a"), 0)
        now[0] = 301
        self.assertEqual(limiter.retry_after("a"), 0)
        for _ in range(4):
            limiter.failed("b")
        now[0] = 700  # failures older than 5 minutes no longer count
        limiter.failed("b")
        self.assertEqual(limiter.retry_after("b"), 0)


class PrefixTests(unittest.TestCase):
    def test_the_space_after_the_scheme_is_restored_when_yaml_or_a_shell_strips_it(self):
        for raw in ("Bearer", "Bearer ", " Bearer  ", "Bearer\t"):
            self.assertEqual(app.normalize_prefix(raw), "Bearer ", repr(raw))
        self.assertEqual(app.normalize_prefix(""), "")
        self.assertEqual(app.normalize_prefix("   "), "")


class HashCliTests(unittest.TestCase):
    def test_output_file_is_plain_ascii_and_verifies(self):
        from unittest import mock
        from viewer import hash_password
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "viewer_password_hash"
            with mock.patch("getpass.getpass", return_value=PASSWORD):
                self.assertEqual(hash_password.main(["--output", str(target)]), 0)
            raw = target.read_bytes()
            self.assertFalse(raw.startswith((b"\xef\xbb\xbf", b"\xff\xfe")))
            self.assertTrue(auth.verify_password(PASSWORD, raw.decode("ascii")))
            with mock.patch("getpass.getpass", side_effect=[PASSWORD, "different password!"]):
                self.assertEqual(hash_password.main(["--output", str(Path(tmp) / "x")]), 1)
            with mock.patch("getpass.getpass", return_value="short"):
                self.assertEqual(hash_password.main(["--output", str(Path(tmp) / "y")]), 1)
            self.assertFalse((Path(tmp) / "x").exists() or (Path(tmp) / "y").exists())


class TargetRuleTests(unittest.TestCase):
    def rows(self, *entries):
        return [{"scope": s, "product": p, "period_key": k, "unit": "idr", "amount": Decimal(a)} for s, p, k, a in entries]

    def test_effective_month_uses_the_latest_row_not_after_the_month(self):
        rows = self.rows(("hardware_month", "Dashcam", "2026-01", 100), ("hardware_month", "Dashcam", "2026-07", 300), ("hardware_month", "Fuel", "2026-12", 5))
        self.assertIsNone(targets.effective_hardware(rows, "Dashcam", "2025-12"))
        self.assertEqual(targets.effective_hardware(rows, "Dashcam", "2026-06"), 100)
        self.assertEqual(targets.effective_hardware(rows, "Dashcam", "2026-07"), 300)
        self.assertEqual(targets.effective_hardware(rows, "Dashcam", "2027-03"), 300)
        self.assertIsNone(targets.effective_hardware(rows, "Fuel", "2026-11"))

    def test_year_target_needs_both_semesters(self):
        rows = self.rows(("semester", None, "2026-S1", 10))
        self.assertEqual(targets.semester_amount(rows, "2026-S1"), 10)
        self.assertIsNone(targets.year_amount(rows, "2026"))
        rows += self.rows(("semester", None, "2026-S2", 15))
        self.assertEqual(targets.year_amount(rows, "2026"), 25)

    def test_amount_parsing(self):
        self.assertEqual(targets.parse_amount(" Rp 1.250.000 ", "idr"), 1250000)
        self.assertIsNone(targets.parse_amount("  ", "idr"))
        for bad in ("1,250", "-5", "1e6", "١٢٣", "9" * 16):
            with self.assertRaises(ValueError, msg=bad):
                targets.parse_amount(bad, "idr")
        self.assertEqual(targets.parse_amount("24", "count"), 24)
        with self.assertRaises(ValueError):
            targets.parse_amount("1.000", "count")


if __name__ == "__main__":
    unittest.main()
