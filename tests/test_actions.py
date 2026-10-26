"""The actions the team took in a period: validation, the form and the Action section on the report page, saving, and what n8n receives."""
import json
import threading
import time
import unittest
from datetime import datetime, timezone

from bs4 import BeautifulSoup

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_viewer import FakeN8n, UTC, ViewerCase  # noqa: E402
from test_viewer_users import USER_PASSWORD  # noqa: E402
from viewer import actions, auth  # noqa: E402


class CleanItemsTests(unittest.TestCase):
    def test_blank_rows_are_dropped_and_text_is_trimmed_and_collapsed(self):
        items = actions.clean_items(json.dumps([{"action": "  Naikkan   bid ", "campaign": "Camp A", "note": ""}, {"action": "", "campaign": "", "note": ""}]))
        self.assertEqual(items, [{"action": "Naikkan bid", "campaign": "Camp A", "note": ""}])
        self.assertEqual(actions.clean_items(""), [])
        self.assertEqual(actions.clean_items("[]"), [])

    def test_each_rule_has_a_message(self):
        bad = {
            "not json": "{",
            "not a list": json.dumps({"action": "x"}),
            "not an object": json.dumps(["x"]),
            "a note without an action": json.dumps([{"action": "", "campaign": "", "note": "catatan"}]),
            "too long": json.dumps([{"action": "x" * 301, "campaign": "", "note": ""}]),
            "control characters": json.dumps([{"action": "a\u0007b", "campaign": "", "note": ""}]),
            "not text": json.dumps([{"action": 5}]),
            "too many": json.dumps([{"action": "x"}] * 31),
        }
        for name, raw in bad.items():
            with self.assertRaises(ValueError, msg=name):
                actions.clean_items(raw)


class ActionPageTests(ViewerCase):
    def setUp(self):
        super().setUp()
        self.login()
        FakeN8n.calls.clear()
        FakeN8n.on_call = None

    def page(self):
        response, body = self.call("GET", "/report/bu1/2026-W39")
        self.assertEqual(response.status, 200)
        return BeautifulSoup(body, "html.parser")

    def post(self, path, **fields):
        return self.call("POST", path, {"bu": "bu1", "period": "2026-W39", **fields}, {"X-CSRF-Token": self.csrf()})

    def test_the_report_starts_without_actions_and_an_admin_can_open_the_form_from_it(self):
        soup = self.page()
        section = soup.select_one('[data-role="actions"]')
        self.assertIn("Belum ada action tercatat untuk Week 39", section.get_text())
        self.assertEqual(section.select_one("button[data-act=actions-open]").get_text(), "Tambah action")
        form = soup.select_one("#vw-form")
        self.assertTrue(form.has_attr("hidden"))
        self.assertEqual(len(form.select("[data-role=rows] [data-row]")), 1)  # one empty line to start with
        self.assertIsNotNone(form.select_one("template#vw-row-tpl"))
        self.assertIn("belum diatur, jadi analisis berjalan tanpa data budget dan spend", form.get_text())  # no budget saved in this fixture
        self.assertEqual(soup.select_one("#vw-analysis button").get_text(), "Buat analisis")
        self.assertIsNone(soup.select_one("#vw-confirm"))
        self.assertEqual(soup.select_one("#vw-analysis")["data-state"], "none")

    def test_the_campaign_list_in_the_form_is_what_budget_holds_for_the_month(self):
        options = lambda soup: [o.get_text() for o in soup.select("#vw-form [data-role=rows] [data-row] select option")]
        empty = self.page()
        self.assertEqual(options(empty), ["Tidak spesifik"])
        self.assertIn("Belum ada campaign yang dipilih di Budget", empty.select_one("#vw-form").get_text())
        data = {"campaigns": {"Email Nurturing": {"budget": 100}, "Brand search": {"budget": 50}}}
        self.assertTrue(self.store.add_budget_snapshot("bu1", "2026-09", "", 1000, None, data, "admin"))
        filled = self.page()
        self.assertEqual(options(filled), ["Tidak spesifik", "Brand search", "Email Nurturing"])
        self.assertNotIn("Belum ada campaign yang dipilih di Budget", filled.select_one("#vw-form").get_text())

    def test_saving_actions_keeps_every_version_shows_the_newest_and_fills_the_form_again(self):
        items = [{"action": "Naikkan bid <b>brand</b>", "campaign": "Camp A", "note": "mulai Selasa"}, {"action": "Ganti materi", "campaign": "", "note": ""}]
        response, _ = self.post("/api/actions", items=json.dumps(items))
        self.assertEqual(response.status, 200)
        self.post("/api/actions", items=json.dumps(items[:1]))
        self.assertEqual(len(self.store.actions), 2)  # appended, never replaced
        soup = self.page()
        rows = [[td.get_text() for td in tr.select("td")] for tr in soup.select('[data-role="actions"] tbody tr')]
        self.assertEqual(rows, [["Naikkan bid <b>brand</b>", "Camp A", "mulai Selasa"]])  # escaped text, newest list only
        self.assertEqual(soup.select_one('[data-role="actions"] button[data-act=actions-open]').get_text(), "Ubah action")
        self.assertIn("Diubah oleh admin", soup.select_one('[data-role="actions"]').get_text())
        filled = [r.select_one("input[data-f=action]")["value"] for r in soup.select("#vw-form [data-role=rows] [data-row]")]
        self.assertEqual(filled, ["Naikkan bid <b>brand</b>"])
        self.assertEqual([o.get("selected") is not None for o in soup.select("#vw-form [data-row] select option")][:3].count(True), 1)
        self.assertNotIn("<b>brand</b>", self.call("GET", "/report/bu1/2026-W39")[1])

    def test_removing_every_action_is_a_valid_save(self):
        self.post("/api/actions", items=json.dumps([{"action": "x", "campaign": "", "note": ""}]))
        self.assertEqual(self.post("/api/actions", items="[]")[0].status, 200)
        self.assertEqual(self.store.latest_actions("bu1", "2026-W39")["items"], [])
        self.assertIn("Belum ada action tercatat", self.page().select_one('[data-role="actions"]').get_text())

    def test_bad_input_and_failures_are_refused_with_a_reason_and_save_nothing(self):
        bad = self.post("/api/actions", items=json.dumps([{"action": "", "campaign": "", "note": "x"}]))
        self.assertEqual(bad[0].status, 400)
        self.assertIn("baris 1", json.loads(bad[1])["error"])
        self.assertEqual(self.post("/api/actions", items="{")[0].status, 400)
        self.assertEqual(self.call("POST", "/api/actions", {"bu": "BU 9", "period": "2026-W39", "items": "[]"}, {"X-CSRF-Token": self.csrf()})[0].status, 400)
        self.assertEqual(self.call("POST", "/api/actions", {"bu": "bu9", "period": "2026-W39", "items": "[]"}, {"X-CSRF-Token": self.csrf()})[0].status, 404)  # no such report
        self.store.fail_writes = True
        down = self.post("/api/actions", items=json.dumps([{"action": "x", "campaign": "", "note": ""}]))
        self.assertEqual(down[0].status, 503)
        self.assertIn("Action tidak tersimpan", json.loads(down[1])["error"])
        self.assertEqual(self.store.actions, [])

    def test_only_admins_save_or_see_the_form_but_everyone_with_access_reads_the_list(self):
        self.post("/api/actions", items=json.dumps([{"action": "Naikkan bid", "campaign": "", "note": ""}]))
        self.store.create_user("andi", auth.hash_password(USER_PASSWORD), "user", True, [], True)
        self.login(USER_PASSWORD, username="andi")
        soup = self.page()
        self.assertIsNone(soup.select_one("#vw-form"))
        section = soup.select_one('[data-role="actions"]')
        self.assertIn("Naikkan bid", section.get_text())
        self.assertIsNone(section.select_one("button"))
        self.assertEqual(self.post("/api/actions", items="[]")[0].status, 403)
        self.assertEqual(len(self.store.actions), 1)

    def wait_done(self):
        for _ in range(60):
            state = json.loads(self.call("GET", "/api/analysis/status?bu=bu1&period=2026-W39")[1])
            if state["state"] != "running":
                return state
            time.sleep(0.05)

    def test_creating_an_analysis_saves_the_list_and_sends_it_with_the_budget_to_n8n(self):
        FakeN8n.on_call = lambda _: self.store.analysis_at.update(bu1=datetime.now(UTC))
        items = [{"action": "Naikkan bid", "campaign": "Camp A", "note": "+15%"}, {"action": "", "campaign": "", "note": ""}]
        response, body = self.post("/api/analysis", items=json.dumps(items))
        self.assertEqual((response.status, json.loads(body)), (202, {"state": "running"}))
        self.assertEqual(self.wait_done(), {"state": "done", "error": ""})
        self.assertEqual(self.store.latest_actions("bu1", "2026-W39")["items"], [{"action": "Naikkan bid", "campaign": "Camp A", "note": "+15%"}])
        sent = FakeN8n.calls[0]["body"]
        self.assertEqual(sent["actions"], [{"action": "Naikkan bid", "campaign": "Camp A", "note": "+15%"}])
        self.assertEqual(sent["budget"]["state"], "belum")  # no budget saved in this fixture: only the state is sent
        self.assertIn("targets", sent)

    def test_without_a_list_in_the_request_the_saved_one_is_reused(self):
        self.store.add_actions("bu1", "2026-W39", [{"action": "Pause iklan lama", "campaign": "", "note": ""}], "admin")
        FakeN8n.on_call = lambda _: self.store.analysis_at.update(bu1=datetime.now(UTC))
        self.assertEqual(self.post("/api/analysis")[0].status, 202)
        self.wait_done()
        self.assertEqual(FakeN8n.calls[0]["body"]["actions"], [{"action": "Pause iklan lama", "campaign": "", "note": ""}])
        self.assertEqual(len(self.store.actions), 1)  # nothing new was saved

    def test_a_bad_list_blocks_the_analysis_before_anything_starts(self):
        response, body = self.post("/api/analysis", items=json.dumps([{"action": "", "campaign": "Camp A", "note": ""}]))
        self.assertEqual(response.status, 400)
        self.assertEqual(FakeN8n.calls, [])
        FakeN8n.on_call = lambda _: self.store.analysis_at.update(bu1=datetime.now(UTC))
        self.assertEqual(self.post("/api/analysis", items="[]")[0].status, 202)  # the report is not stuck in "running"
        self.wait_done()

    def test_a_failed_save_releases_the_job_so_the_analysis_can_be_tried_again(self):
        self.store.fail_writes = True
        response, _ = self.post("/api/analysis", items=json.dumps([{"action": "x", "campaign": "", "note": ""}]))
        self.assertEqual(response.status, 503)
        self.assertEqual(FakeN8n.calls, [])
        self.store.fail_writes = False
        FakeN8n.on_call = lambda _: self.store.analysis_at.update(bu1=datetime.now(UTC))
        self.assertEqual(self.post("/api/analysis", items="[]")[0].status, 202)
        self.wait_done()


if __name__ == "__main__":
    unittest.main()
