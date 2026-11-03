"""Starting a report or Performa run from the viewer and reading its status back from what n8n reports."""
import json
import time
import unittest
from datetime import date, datetime, timedelta, timezone

from bs4 import BeautifulSoup

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_viewer import FakeN8n, UTC, ViewerCase  # noqa: E402
from test_viewer_users import USER_PASSWORD  # noqa: E402
from viewer import app, auth, refresh  # noqa: E402

COMPANIES = ["bu1", "bu2"]
NOW = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)


def job(bu="all", started=NOW, results=(), kind="report", period="2026-W44"):
    return {"job_id": "j1", "kind": kind, "bu": bu, "period": period, "requested_by": "admin", "requested_at": started,
            "results": [{"bu": b, "ok": ok, "message": m, "finished_at": started + timedelta(seconds=40)} for b, ok, m in results]}


class RefreshRulesTests(unittest.TestCase):
    def test_periods_are_the_latest_weeks_and_months_in_the_form_n8n_expects(self):
        options = refresh.period_options(date(2026, 11, 3))
        self.assertEqual(options["week"][0], ("2026-W45", "Week 45 2026"))
        self.assertEqual(len(options["week"]), 8)
        self.assertEqual(options["month"][0], ("2026-11", "November 2026"))
        self.assertEqual(options["month"][-1], ("2026-06", "Juni 2026"))
        self.assertEqual(refresh.period_options(date(2027, 1, 4))["week"][0][0], "2027-W01")  # an ISO week can belong to the year of its Thursday
        self.assertEqual(refresh.period_options(date(2027, 1, 4))["month"][1], ("2026-12", "Desember 2026"))

    def test_requests_are_checked(self):
        self.assertEqual(refresh.check_request("report", "all", "2026-W44", COMPANIES), "2026-W44")
        self.assertEqual(refresh.check_request("report", "bu2", "2026-10", COMPANIES), "2026-10")
        self.assertEqual(refresh.check_request("performa", "bu1", "ignored", COMPANIES), "")
        for args in (("x", "bu1", "2026-W44"), ("report", "bu9", "2026-W44"), ("report", "bu1", ""), ("report", "bu1", "2026-W99"), ("report", "bu1", "2026-13"), ("report", "bu1", "minggu ini"), ("performa", "bu9", "")):
            with self.assertRaises(ValueError, msg=str(args)):
                refresh.check_request(*args, COMPANIES)

    def test_status_follows_what_has_been_reported(self):
        derive = lambda j, local="": refresh.derive(j, COMPANIES, NOW + timedelta(seconds=60), local)
        self.assertEqual(derive(job("bu1"))["state"], "running")
        self.assertEqual(derive(job("all", results=[("bu1", True, "ok")]))["state"], "running")  # one of two companies has reported
        self.assertEqual(derive(job("all", results=[("bu1", True, ""), ("bu2", True, "")]))["state"], "done")
        failed = derive(job("all", results=[("bu1", True, ""), ("bu2", False, "Sheet tidak bisa dibaca")]))
        self.assertEqual((failed["state"], failed["failures"], failed["ok_companies"]), ("failed", [("bu2", "Sheet tidak bisa dibaca")], ["bu1"]))
        self.assertEqual(derive(job("bu1"), "n8n menjawab 500")["state"], "failed")  # n8n answered with an error before reporting anything
        self.assertEqual(derive(job("bu1", results=[("bu1", True, "")]), "n8n menjawab 500")["state"], "done")  # the report beats a late error answer
        late = refresh.derive(job("all", results=[("bu1", True, "")]), COMPANIES, NOW + timedelta(seconds=301), "")
        self.assertEqual(late["state"], "timeout")
        self.assertEqual(refresh.derive(job("bu1"), COMPANIES, NOW + timedelta(seconds=300), "")["state"], "running")  # exactly five minutes is still running

    def test_texts_say_what_happened_in_plain_words(self):
        names = {"bu1": "McEasy", "bu2": "LOL"}
        status = lambda j, now=NOW + timedelta(seconds=60): refresh.derive(j, COMPANIES, now, "")
        done = job("all", results=[("bu1", True, ""), ("bu2", True, "")])
        self.assertEqual(refresh.outcome_text(done, status(done), names), "Berhasil")
        self.assertEqual(refresh.duration_text(done, status(done)), "40 detik")
        partial = job("all", results=[("bu1", True, ""), ("bu2", False, "Sheet tidak bisa dibaca")])
        self.assertEqual(refresh.outcome_text(partial, status(partial), names), "Gagal. LOL: Sheet tidak bisa dibaca. Berhasil untuk McEasy.")
        running = job("bu1")
        self.assertEqual((refresh.outcome_text(running, status(running), names), refresh.duration_text(running, status(running))), ("Sedang berjalan", "-"))
        stuck = job("bu1")
        self.assertIn("5 menit", refresh.outcome_text(stuck, status(stuck, NOW + timedelta(seconds=400)), names))
        slow = {**job("bu1", results=[("bu1", True, "")])}
        slow["results"][0]["finished_at"] = NOW + timedelta(seconds=125)
        self.assertEqual(refresh.duration_text(slow, status(slow)), "2 menit 5 detik")

    def test_the_other_webhooks_are_found_next_to_the_analysis_one(self):
        self.assertEqual(app.sibling_url("http://n8n:5678/webhook/report-analysis", "report-generate"), "http://n8n:5678/webhook/report-generate")
        self.assertEqual(app.sibling_url("http://n8n:5678/webhook/other", "report-generate"), "")
        self.assertEqual(app.sibling_url("", "report-generate"), "")


class RefreshPageTests(ViewerCase):
    def setUp(self):
        super().setUp()
        self.login()
        FakeN8n.calls.clear()

    def page(self):
        response, body = self.call("GET", "/refresh")
        self.assertEqual(response.status, 200)
        return BeautifulSoup(body, "html.parser"), body

    def start(self, **fields):
        return self.call("POST", "/api/refresh", json.dumps(fields), {"X-CSRF-Token": self.csrf(), "Content-Type": "application/json"})

    def wait_for_call(self):
        for _ in range(100):
            if FakeN8n.calls:
                return
            time.sleep(0.05)
        self.fail("n8n was not called")

    def test_the_page_offers_both_runs_with_the_companies_and_periods(self):
        soup, body = self.page()
        self.assertEqual({c["data-kind-card"] for c in soup.select("[data-kind-card]")}, {"report", "performa"})
        self.assertEqual([o["value"] for o in soup.select("#r-bu option")], ["bu1", "bu2", "all"])
        self.assertEqual([o["value"] for o in soup.select("#p-bu option")], ["bu1", "bu2", "all"])
        self.assertEqual(len(soup.select("#r-period option[data-kind=week]")), 8)
        self.assertEqual(len(soup.select("#r-period option[data-kind=month]")), 6)
        self.assertIn("Belum ada proses yang dijalankan", soup.get_text())
        self.assertIn('href="/refresh"', body)  # the menu

    def test_starting_a_report_records_the_request_and_calls_n8n_with_the_job_id(self):
        response, body = self.start(kind="report", bu="all", period="2026-W44")
        self.assertEqual((response.status, json.loads(body)["state"]), (202, "running"))
        self.wait_for_call()
        call = FakeN8n.calls[0]
        self.assertEqual(call["path"], "/webhook/report-generate")
        self.assertEqual(call["headers"]["Authorization"], "Bearer n8n-token-123")
        job_id = self.store.processes[0]["job_id"]
        self.assertEqual(call["body"], {"bu": "all", "period": "2026-W44", "job_id": job_id, "requested_by": "viewer"})
        self.assertEqual((self.store.processes[0]["requested_by"], self.store.processes[0]["period"]), ("admin", "2026-W44"))

    def test_performa_has_no_period_and_goes_to_its_own_webhook(self):
        self.assertEqual(self.start(kind="performa", bu="bu1", period="2026-W44")[0].status, 202)
        self.wait_for_call()
        self.assertEqual(FakeN8n.calls[0]["path"], "/webhook/performa-generate")
        self.assertEqual(set(FakeN8n.calls[0]["body"]), {"bu", "job_id", "requested_by"})
        self.assertEqual(self.store.processes[0]["period"], "")

    def test_a_running_job_locks_its_button_and_a_second_start_is_refused(self):
        self.start(kind="report", bu="bu1", period="2026-W44")
        self.wait_for_call()
        soup, _ = self.page()
        self.assertTrue(soup.select_one("[data-start=report]").has_attr("disabled"))
        self.assertFalse(soup.select_one("[data-start=performa]").has_attr("disabled"))  # the other kind is free
        self.assertIsNotNone(soup.select_one("[aria-busy=true]"))
        response, body = self.start(kind="report", bu="bu2", period="2026-W43")
        self.assertEqual(response.status, 409)
        self.assertIn("masih berjalan", json.loads(body)["error"])
        self.assertEqual(len(self.store.processes), 1)
        status = json.loads(self.call("GET", "/api/refresh/status?kind=report")[1])
        self.assertEqual(status["state"], "running")

    def test_results_from_n8n_finish_the_job_and_unlock_the_button(self):
        self.start(kind="report", bu="all", period="2026-W44")
        self.wait_for_call()
        job_id = self.store.processes[0]["job_id"]
        self.store.report_result(job_id, "bu1", True)
        self.assertEqual(json.loads(self.call("GET", "/api/refresh/status?kind=report")[1])["state"], "running")  # LOL has not reported yet
        self.store.report_result(job_id, "bu2", True)
        self.assertEqual(json.loads(self.call("GET", "/api/refresh/status?kind=report")[1])["state"], "done")
        soup, _ = self.page()
        self.assertFalse(soup.select_one("[data-start=report]").has_attr("disabled"))
        self.assertIn("Terakhir berhasil", soup.get_text())
        row = soup.select("section[aria-label='Riwayat proses'] tbody tr")[0].get_text(" ")
        self.assertIn("Generate report", row)
        self.assertIn("Semua", row)
        self.assertIn("2026-W44", row)
        self.assertIn("Berhasil", row)
        self.assertEqual(self.start(kind="report", bu="bu1", period="2026-W44")[0].status, 202)  # a new run can start now

    def test_a_failure_is_shown_with_its_message_and_the_company_that_succeeded(self):
        self.start(kind="report", bu="all", period="2026-W44")
        job_id = self.store.processes[0]["job_id"]
        self.store.report_result(job_id, "bu1", True)
        self.store.report_result(job_id, "bu2", False, "Laporan Perusahaan 2 2026-W44 GAGAL dibuat: 422 | Kolom wajib tidak ada")
        soup, _ = self.page()
        alert = soup.select_one("[data-kind-card=report] .vw-alert[data-role=status]").get_text()
        self.assertIn("GAGAL dibuat", alert)
        self.assertIn("Berhasil untuk Perusahaan 1", alert)
        self.assertFalse(soup.select_one("[data-start=report]").has_attr("disabled"))

    def test_no_answer_within_five_minutes_unlocks_with_an_honest_message(self):
        self.start(kind="performa", bu="bu1")
        self.store.processes[0]["requested_at"] = datetime.now(UTC) - timedelta(seconds=refresh.TIMEOUT_SECONDS + 5)
        soup, _ = self.page()
        self.assertIn("Tidak ada laporan dari n8n dalam 5 menit", soup.get_text())
        self.assertFalse(soup.select_one("[data-start=performa]").has_attr("disabled"))
        self.assertEqual(self.start(kind="performa", bu="bu1")[0].status, 202)

    def test_an_error_answer_from_n8n_is_kept_and_shown(self):
        FakeN8n.status = 500
        self.start(kind="report", bu="bu1", period="2026-W44")
        self.wait_for_call()
        for _ in range(100):
            if self.jobs_error():
                break
            time.sleep(0.05)
        soup, _ = self.page()
        self.assertIn("n8n menjawab 500", soup.get_text())
        self.assertFalse(soup.select_one("[data-start=report]").has_attr("disabled"))

    def jobs_error(self):
        return (self.server.RequestHandlerClass.jobs.get(("refresh", self.store.processes[0]["job_id"])) or {}).get("error")

    def test_bad_requests_are_refused_and_record_nothing(self):
        for fields in ({"kind": "x", "bu": "bu1"}, {"kind": "report", "bu": "bu9", "period": "2026-W44"}, {"kind": "report", "bu": "bu1", "period": "2026-W99"}, {"kind": "report", "bu": "bu1"}):
            self.assertEqual(self.start(**fields)[0].status, 400, fields)
        self.store.fail_writes = True
        self.assertEqual(self.start(kind="report", bu="bu1", period="2026-W44")[0].status, 503)
        self.store.fail_writes = False
        self.assertEqual(self.store.processes, [])
        self.assertEqual(FakeN8n.calls, [])
        self.assertEqual(self.call("GET", "/api/refresh/status?kind=x")[0].status, 400)

    def test_without_a_webhook_address_the_page_says_so_and_nothing_starts(self):
        self.server.RequestHandlerClass.cfg.n8n_generate_url = ""
        soup, _ = self.page()
        self.assertTrue(soup.select_one("[data-start=report]").has_attr("disabled"))
        self.assertIn("belum diatur", soup.select_one("[data-kind-card=report]").get_text())
        self.assertEqual(self.start(kind="report", bu="bu1", period="2026-W44")[0].status, 503)
        self.assertEqual(self.store.processes, [])

    def test_only_admins_see_or_start_anything(self):
        self.store.create_user("andi", auth.hash_password(USER_PASSWORD), "user", True, [], True)
        self.login(USER_PASSWORD, username="andi")
        self.assertEqual(self.call("GET", "/refresh")[0].status, 403)
        self.assertEqual(self.start(kind="report", bu="bu1", period="2026-W44")[0].status, 403)
        self.assertEqual(self.call("GET", "/api/refresh/status?kind=report")[0].status, 403)
        self.assertNotIn("/refresh", self.call("GET", "/")[1])
        self.assertEqual(self.store.processes, [])


if __name__ == "__main__":
    unittest.main()
