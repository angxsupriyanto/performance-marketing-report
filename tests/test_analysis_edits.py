import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from test_viewer import UTC, FakeN8n, ViewerCase  # noqa: E402
from test_viewer_users import USER_PASSWORD  # noqa: E402
from viewer import analysis_edits, auth  # noqa: E402

KEYS = ["executive_summary", "hardware_summary", "hardware_dashcam"]
AI_AT = datetime(2026, 10, 20, 16, 30, tzinfo=UTC)
fmt = lambda t: t.strftime("%d/%m %H:%M")


def report(**kw):
    return {"analysis": {"executive_summary": "teks AI", "hardware_summary": "", "hardware_dashcam": "dash AI"}, "analysis_created_at": AI_AT, "model": "gemini-x", **kw}


class EffectiveTests(unittest.TestCase):
    def test_ai_text_edit_restore_and_supersession(self):
        texts, edited = analysis_edits.effective(report(), [], KEYS, True, fmt)
        self.assertEqual((edited, texts["executive_summary"], texts["_panels"]["executive_summary"]["chip"]), (0, "teks AI", "AI · gemini-x"))
        self.assertEqual(texts["_panels"]["executive_summary"]["meta"], "Dibuat oleh model gemini-x · 20/10 16:30")
        self.assertEqual(texts["_panels"]["hardware_summary"]["edit_label"], "Tulis manual")  # empty AI panel
        later = AI_AT + timedelta(minutes=5)
        edit = {"panel_key": "executive_summary", "body": "versi saya", "edited_by": "admin", "created_at": later}
        texts, edited = analysis_edits.effective(report(), [edit], KEYS, True, fmt)
        panel = texts["_panels"]["executive_summary"]
        self.assertEqual((edited, texts["executive_summary"], panel["state"], panel["chip"]), (1, "versi saya", "edited", "Edited"))
        self.assertEqual((panel["meta"], panel["restore_label"], panel["edit_label"]), ("Diedit oleh admin · 20/10 16:35 · model awal: gemini-x", "Kembalikan ke versi AI", "Edit"))
        marker = dict(edit, body=None, created_at=later + timedelta(minutes=1))
        texts, edited = analysis_edits.effective(report(), [marker], KEYS, True, fmt)
        self.assertEqual((edited, texts["executive_summary"]), (0, "teks AI"))
        old = dict(edit, created_at=AI_AT - timedelta(minutes=1))  # older than the AI analysis: replaced by it
        texts, edited = analysis_edits.effective(report(), [old], KEYS, True, fmt)
        self.assertEqual((edited, texts["executive_summary"]), (0, "teks AI"))

    def test_manual_text_without_any_ai_analysis(self):
        edit = {"panel_key": "executive_summary", "body": "tulis tangan", "edited_by": "admin", "created_at": AI_AT}
        texts, edited = analysis_edits.effective({"analysis": None, "analysis_created_at": None, "model": None}, [edit], KEYS, True, fmt)
        panel = texts["_panels"]["executive_summary"]
        self.assertEqual((edited, panel["meta"], panel["restore_label"]), (1, "Ditulis manual oleh admin · 20/10 16:30 · belum ada analisis AI", "Hapus teks manual"))
        self.assertEqual(texts["_panels"]["hardware_dashcam"]["state"], "none")

    def test_text_rules(self):
        self.assertEqual(analysis_edits.clean_text("  halo\r\n  "), "halo")
        for bad in ("", "   ", "x" * 4001):
            with self.assertRaises(ValueError):
                analysis_edits.clean_text(bad)


class EditFlowTests(ViewerCase):
    def setUp(self):
        super().setUp()
        self.store.analysis_at["bu1"] = datetime.now(UTC) - timedelta(hours=1)
        self.store.analysis["bu1"] = {"executive_summary": "teks AI", "hardware_summary": "ringkas", "hardware_dashcam": "dash AI"}
        self.login()

    def edit(self, **fields):
        return self.call("POST", "/api/analysis/edit", {"csrf": self.csrf(), "bu": "bu1", "period": "2026-W39", "key": "executive_summary", **fields})

    def page(self):
        return BeautifulSoup(self.call("GET", "/report/bu1/2026-W39")[1], "html.parser")

    def panel(self, soup, key):
        return soup.select_one(f'[data-panel="{key}"]')

    def test_ai_panels_show_chip_provenance_and_edit_controls_for_admin(self):
        soup = self.page()
        panel = self.panel(soup, "executive_summary")
        self.assertIn("AI · claude-sonnet-5-5", panel.get_text())
        self.assertIn("Dibuat oleh model claude-sonnet-5-5 ·", panel.select_one("[data-role=meta]").get_text())
        self.assertEqual([b.get_text() for b in panel.select("[data-role=controls] button")], ["Edit"])
        self.assertEqual(panel.select_one("textarea").get_text().strip(), "teks AI")
        self.assertEqual(len(soup.select("[data-panel]")), 8)  # executive, hardware summary, five products and next action
        self.assertEqual(soup.select_one("#vw-analysis")["data-edited"], "0")

    def test_saving_an_edit_shows_edited_and_keeps_every_version(self):
        self.assertEqual(self.edit(text="Versi <i>saya</i>")[0].status, 200)
        self.assertEqual(self.edit(text="Versi kedua")[0].status, 200)
        self.assertEqual([e["body"] for e in self.store.edits], ["Versi <i>saya</i>", "Versi kedua"])  # appended, never replaced
        soup = self.page()
        panel = self.panel(soup, "executive_summary")
        self.assertEqual(panel.select_one('[data-analysis="executive_summary"]').get_text(), "Versi kedua")
        self.assertIn("Edited", panel.get_text())
        self.assertNotIn("AI · claude", panel.select_one("div").get_text())
        self.assertIn("Diedit oleh admin ·", panel.select_one("[data-role=meta]").get_text())
        self.assertIn("model awal: claude-sonnet-5-5", panel.select_one("[data-role=meta]").get_text())
        self.assertEqual([b.get_text() for b in panel.select("[data-role=controls] button")], ["Edit", "Kembalikan ke versi AI"])
        self.assertEqual(soup.select_one("#vw-analysis")["data-edited"], "1")
        self.assertIsNotNone(soup.select_one("#vw-form [data-role=warn]"))  # the "panels were edited" warning lives in the actions form now
        self.assertNotIn("<i>saya</i>", self.call("GET", "/report/bu1/2026-W39")[1])  # stored as text, shown escaped

    def test_restoring_brings_back_the_ai_text(self):
        self.edit(text="Versi saya")
        self.assertEqual(self.edit(restore="1")[0].status, 200)
        panel = self.panel(self.page(), "executive_summary")
        self.assertEqual(panel.select_one('[data-analysis="executive_summary"]').get_text(), "teks AI")
        self.assertIn("AI · claude-sonnet-5-5", panel.get_text())
        self.assertEqual(len(self.store.edits), 2)

    def test_a_new_ai_analysis_replaces_edits_made_before_it(self):
        self.edit(text="Versi saya")
        self.store.analysis_at["bu1"] = datetime.now(UTC) + timedelta(minutes=1)
        self.store.analysis["bu1"]["executive_summary"] = "AI baru"
        soup = self.page()
        self.assertEqual(self.panel(soup, "executive_summary").select_one('[data-analysis="executive_summary"]').get_text(), "AI baru")
        self.assertEqual(soup.select_one("#vw-analysis")["data-edited"], "0")
        self.assertEqual(len(self.store.edits), 1)  # the edit stays stored as history

    def test_manual_text_before_any_analysis(self):
        self.store.analysis_at["bu1"], self.store.analysis["bu1"] = None, None
        panel = self.panel(self.page(), "executive_summary")
        self.assertEqual([b.get_text() for b in panel.select("[data-role=controls] button")], ["Tulis manual"])
        self.assertEqual(panel.select_one('[data-analysis="executive_summary"]').get_text(), "Kosong sampai analisis dibuat.")
        self.edit(text="Catatan manual")
        panel = self.panel(self.page(), "executive_summary")
        self.assertIn("Ditulis manual oleh admin ·", panel.get_text())
        self.assertIn("belum ada analisis AI", panel.get_text())
        self.assertEqual([b.get_text() for b in panel.select("[data-role=controls] button")], ["Edit", "Hapus teks manual"])

    def test_bad_edits_are_refused_and_nothing_is_saved(self):
        for fields, status in (({"text": ""}, 400), ({"text": "x" * 4001}, 400), ({"text": "ok", "key": "executive"}, 400), ({"text": "ok", "bu": "bu9"}, 404),
                               ({"text": "ok", "period": "2026-W40"}, 404), ({"text": "ok", "period": "kacau"}, 400)):
            self.assertEqual(self.edit(**fields)[0].status, status, fields)
        self.assertEqual(self.call("POST", "/api/analysis/edit", {"bu": "bu1", "period": "2026-W39", "key": "executive_summary", "text": "ok"})[0].status, 403)  # no csrf
        self.assertEqual(self.store.edits, [])

    def test_a_database_failure_is_reported_for_retry(self):
        self.store.fail_writes = True
        response, body = self.edit(text="ok")
        self.assertEqual(response.status, 503)
        self.assertIn("Edit tidak tersimpan", body)

    def test_a_missing_edit_table_leaves_the_ai_text_read_only(self):
        self.store.latest_edits = lambda run_id: (_ for _ in ()).throw(RuntimeError("no such table"))
        soup = self.page()
        self.assertEqual(soup.select("[data-act][data-key]"), [])
        self.assertEqual(self.panel(soup, "executive_summary").select_one('[data-analysis="executive_summary"]').get_text(), "teks AI")

    def test_only_admins_edit_but_everyone_with_access_sees_the_edited_text(self):
        self.edit(text="Versi saya")
        self.store.ensure_bootstrap_admin(self.hash)
        self.store.create_user("andi", auth.hash_password(USER_PASSWORD), "user", False, ["bu1"], True)
        self.login(USER_PASSWORD, username="andi")
        soup = self.page()
        panel = self.panel(soup, "executive_summary")
        self.assertEqual(panel.select_one('[data-analysis="executive_summary"]').get_text(), "Versi saya")
        self.assertIn("Edited", panel.get_text())
        self.assertEqual(soup.select("[data-act][data-key]"), [])
        self.assertIsNone(soup.select_one("textarea"))
        response, _ = self.edit(text="peretasan")
        self.assertEqual(response.status, 403)
        self.assertEqual(len(self.store.edits), 1)

    def test_creating_a_new_analysis_still_works_from_the_same_button(self):
        soup = self.page()
        self.assertIsNotNone(soup.select_one("#vw-analysis button"))
        self.assertEqual(FakeN8n.calls, [])


if __name__ == "__main__":
    unittest.main()
