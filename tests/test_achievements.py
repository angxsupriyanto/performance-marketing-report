"""Achievement figures typed by hand: validation, the forms on the report page, saving, and where the figures show up."""
import json
import unittest
from decimal import Decimal

from bs4 import BeautifulSoup

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_viewer import FakeN8n, ViewerCase  # noqa: E402
from test_viewer_users import USER_PASSWORD  # noqa: E402
from viewer import auth  # noqa: E402
from viewer import achievements, targets  # noqa: E402
import report_view  # noqa: E402


class ParseAndApplyTests(unittest.TestCase):
    VIEW = {"progress": {"unit": "idr", "semester": {"key": "2026-S2", "label": "Semester 2 2026", "actual": 100}, "year": {"key": "2026", "year": "2026", "actual": 200}},
            "hardware": [{"name": "Dashcam", "month_to_date": 10}, {"name": "OBD", "month_to_date": 20}], "month": {"key": "2026-09", "label": "September 2026"}}

    def test_money_accepts_thousand_dots_and_blank_means_use_the_system_figure(self):
        self.assertEqual(achievements.parse("month", {"Dashcam": "Rp 1.500.000", "OBD": " "}, self.VIEW), {"Dashcam": 1500000})
        self.assertEqual(achievements.parse("year", {"semester": "5000", "year": ""}, self.VIEW), {"semester": 5000})
        self.assertEqual(achievements.parse("year", {}, self.VIEW), {})

    def test_counts_are_whole_numbers_only(self):
        count_view = {**self.VIEW, "progress": {**self.VIEW["progress"], "unit": "count"}}
        self.assertEqual(achievements.parse("year", {"semester": "12"}, count_view), {"semester": 12})
        with self.assertRaises(ValueError):
            achievements.parse("year", {"semester": "1.5"}, count_view)

    def test_each_rule_has_a_message(self):
        bad = {"letters": ("month", {"Dashcam": "abc"}), "comma": ("month", {"Dashcam": "1,5"}), "unknown product": ("month", {"Fuel": "1"}), "unknown scope": ("week", {}),
               "not text": ("month", {"Dashcam": 5}), "not an object": ("month", ["x"]), "too long": ("month", {"Dashcam": "1" * 20})}
        for name, (scope, raw) in bad.items():
            with self.assertRaises(ValueError, msg=name):
                achievements.parse(scope, raw, self.VIEW)
        with self.assertRaises(ValueError):
            achievements.parse("month", {"Dashcam": "1"}, {"progress": {"unit": "count"}})  # a report without products has no month form

    def test_each_form_replaces_only_its_own_part(self):
        saved = {"values": {"hardware": {"Dashcam": 1}, "semester": 2, "year": 3}}
        self.assertEqual(achievements.merge(saved, "month", {"OBD": 9}), {"hardware": {"OBD": 9}, "semester": 2, "year": 3})
        self.assertEqual(achievements.merge(saved, "month", {}), {"semester": 2, "year": 3})
        self.assertEqual(achievements.merge(saved, "year", {"year": 7}), {"hardware": {"Dashcam": 1}, "year": 7})
        self.assertEqual(achievements.merge(None, "year", {}), {})

    def test_figures_replace_the_system_ones_in_a_copy_and_the_original_stays(self):
        saved = {"values": {"hardware": {"Dashcam": 99}, "semester": 150}}
        shown = achievements.apply_view(self.VIEW, saved)
        self.assertEqual((shown["hardware"][0]["month_to_date"], shown["hardware"][1]["month_to_date"], shown["progress"]["semester"]["actual"], shown["progress"]["year"]["actual"]), (99, 20, 150, 200))
        self.assertEqual((self.VIEW["hardware"][0]["month_to_date"], self.VIEW["progress"]["semester"]["actual"]), (10, 100))
        self.assertIs(achievements.apply_view(self.VIEW, None), self.VIEW)

    def test_the_analysis_facts_follow_the_same_figures(self):
        facts = {"progress": {"unit": "idr", "windows": {"semester": {"key": "2026-S2", "label": "S2"}, "year": {"key": "2026", "label": "2026"}, "month": {"key": "2026-09", "label": "Sep"}},
                              "total": {"semester": {"sql_value": 100}, "year": {"sql_value": 200}}, "hardware": {"Dashcam": {"week_sql_value": 5, "month_to_date": 10}}}}
        shown = achievements.apply_facts(facts, {"values": {"hardware": {"Dashcam": 40}, "year": 300}})
        self.assertEqual((shown["progress"]["total"]["year"]["sql_value"], shown["progress"]["total"]["semester"]["sql_value"], shown["progress"]["hardware"]["Dashcam"]["month_to_date"]), (300, 100, 40))
        context = targets.context_for_analysis(shown, [])
        self.assertEqual((context["year"]["actual"], context["month"]["hardware"][0]["month_to_date"]), (300, 40))
        eco = {"progress": {"unit": "count", "focus_product": "Ecosystem", "windows": facts["progress"]["windows"], "total": {"semester": {"focus_sql": 6}, "year": {"focus_sql": 22}}}}
        self.assertEqual(achievements.apply_facts(eco, {"values": {"semester": 9}})["progress"]["total"]["semester"]["focus_sql"], 9)


class AchievementPageTests(ViewerCase):
    def setUp(self):
        super().setUp()
        self.login()
        FakeN8n.calls.clear()
        FakeN8n.on_call = None
        self.store.add_targets("bu1", [("semester", None, "2026-S2", "idr", Decimal(1000000000)), ("semester", None, "2026-S1", "idr", Decimal(1000000000)),
                                       ("hardware_month", "Dashcam", "2026-09", "idr", Decimal(100000000))])
        self.store.add_targets("bu2", [("semester", None, "2026-S2", "count", Decimal(24)), ("semester", None, "2026-S1", "count", Decimal(16))])

    def page(self, bu="bu1"):
        response, body = self.call("GET", f"/report/{bu}/2026-W39")
        self.assertEqual(response.status, 200)
        return BeautifulSoup(body, "html.parser"), body

    def post(self, scope, values, reason="Deal belum masuk Sheet", bu="bu1"):
        return self.call("POST", "/api/achievements", {"bu": bu, "period": "2026-W39", "scope": scope, "values": json.dumps(values), "reason": reason}, {"X-CSRF-Token": self.csrf()})

    def test_admins_get_a_button_and_form_in_each_target_section_with_the_system_figure_shown(self):
        soup, _ = self.page()
        self.assertEqual({b["data-manual-open"] for b in soup.select("[data-manual-open]")}, {"month", "year"})
        month = soup.select_one("[data-manual-form=month]")
        self.assertEqual([i["data-key"] for i in month.select("input[data-key]")], ["Dashcam", "GPS Tracker", "Fuel", "MDVR", "OBD"])
        self.assertTrue(month.select_one("[data-role=manual-reason]"))
        self.assertIn("Rp", month.get_text())
        self.assertEqual([i["data-key"] for i in soup.select_one("[data-manual-form=year]").select("input[data-key]")], ["semester", "year"])
        self.assertIsNotNone(soup.find("script", string=lambda t: t and "api/achievements" in t))

    def test_the_company_without_products_only_gets_the_year_form_in_sql_counts(self):
        soup, _ = self.page("bu2")
        self.assertEqual({b["data-manual-open"] for b in soup.select("[data-manual-open]")}, {"year"})
        form = soup.select_one("[data-manual-form=year]")
        self.assertIn("SQL", form.get_text())
        self.assertNotIn("Rp", " ".join(i["aria-label"] for i in form.select("input[data-key]")))

    def test_no_button_while_no_target_is_set_and_none_for_a_user_who_also_cannot_save(self):
        saved = list(self.store.entries)
        self.store.entries.clear()
        soup, _ = self.page()
        self.assertEqual(soup.select("[data-manual-open]"), [])
        self.store.entries.extend(saved)
        self.assertEqual(self.post("year", {"semester": "1"})[0].status, 200)
        self.store.create_user("andi", auth.hash_password(USER_PASSWORD), "user", True, [], True)
        self.login(USER_PASSWORD, username="andi")
        soup, body = self.page()
        self.assertEqual(soup.select("[data-manual-open], [data-manual-form]"), [])
        self.assertNotIn("Deal belum masuk Sheet", body)  # the reason is for admins only
        self.assertIn("Rp 1", soup.get_text())  # but the typed figure shows for everyone
        self.assertEqual(self.post("year", {"semester": "9"})[0].status, 403)

    def test_saving_keeps_every_version_and_the_report_shows_the_typed_figure_without_a_marker(self):
        _, before = self.page()
        response, body = self.post("month", {"Dashcam": "Rp 123.000.000", "OBD": ""})
        self.assertEqual((response.status, json.loads(body)), (200, {"ok": True}))
        self.assertEqual(self.store.latest_achievements("bu1", "2026-W39")["values"], {"hardware": {"Dashcam": 123000000}})
        soup, after = self.page()
        self.assertIn("Rp 124.000.000", soup.get_text())  # Dashcam 123 juta typed + GPS Tracker 1 juta from the Sheet
        self.assertNotIn("123.000.000", before)
        self.assertEqual(soup.select_one("[data-manual-form=month] input[data-key=Dashcam]")["value"], "123000000")
        text = soup.get_text()
        for editor in soup.select("[data-editor]"):
            editor.decompose()
        report_text = soup.get_text()
        self.assertNotIn("manual", report_text.replace("Tulis manual", ""))  # no marker anywhere in the report itself: only the admin forms mention it
        self.assertIn("Deal belum masuk Sheet", text)  # inside the form, as history for the next admin
        self.assertEqual(self.post("year", {"semester": "5.000.000.000"})[0].status, 200)
        values = self.store.latest_achievements("bu1", "2026-W39")["values"]
        self.assertEqual(values, {"hardware": {"Dashcam": 123000000}, "semester": 5000000000})  # the month part was kept
        self.assertEqual(len(self.store.achievements), 2)

    def test_resetting_everything_needs_no_reason_but_a_figure_does(self):
        self.assertEqual(self.post("month", {"Dashcam": "1"}, reason="")[0].status, 400)
        self.assertEqual(self.store.achievements, [])
        self.assertEqual(self.post("month", {"Dashcam": "1"})[0].status, 200)
        self.assertEqual(self.post("month", {"Dashcam": ""}, reason="")[0].status, 200)
        self.assertEqual(self.store.latest_achievements("bu1", "2026-W39")["values"], {})

    def test_bad_input_and_failures_are_refused_with_a_reason_and_save_nothing(self):
        for scope, values in (("month", {"Dashcam": "abc"}), ("month", {"Fuel2": "1"}), ("week", {}), ("year", {"semester": "1,5"})):
            response, body = self.post(scope, values)
            self.assertEqual(response.status, 400, (scope, values))
            self.assertTrue(json.loads(body)["error"])
        response, body = self.call("POST", "/api/achievements", {"bu": "bu1", "period": "2026-W39", "scope": "month", "values": "{", "reason": "x"}, {"X-CSRF-Token": self.csrf()})
        self.assertEqual(response.status, 400)
        self.assertEqual(self.post("month", {"Dashcam": "1"}, reason="x" * 301)[0].status, 400)
        self.assertEqual(self.post("month", {"Dashcam": "1"}, bu="bu1")[0].status, 200)
        self.store.achievements.clear()
        self.store.fail_writes = True
        self.assertEqual(self.post("month", {"Dashcam": "1"})[0].status, 503)
        self.store.fail_writes = False
        self.assertEqual(self.store.achievements, [])
        self.assertEqual(self.call("POST", "/api/achievements", {"bu": "bu1", "period": "2026-W01", "scope": "month", "values": "{}", "reason": ""}, {"X-CSRF-Token": self.csrf()})[0].status, 404)

    def test_the_typed_figures_also_reach_the_pdf_page_the_target_context_and_the_analysis(self):
        self.assertEqual(self.post("year", {"semester": "700.000.000"})[0].status, 200)
        shown = achievements.apply_view(report_view.extract_view(self.store.html["bu1"][0]), self.store.latest_achievements("bu1", "2026-W39"))
        printed = report_view.print_document(shown, targets.build_tg(shown, self.store.latest_targets("bu1")))
        self.assertIn("Rp 700.000.000", printed)
        self.assertNotIn("data-manual", printed)
        FakeN8n.on_call = lambda _: self.store.analysis_at.update(bu1=__import__("datetime").datetime.now(__import__("datetime").timezone.utc))
        self.assertEqual(self.call("POST", "/api/analysis", {"bu": "bu1", "period": "2026-W39", "items": "[]"}, {"X-CSRF-Token": self.csrf()})[0].status, 202)
        for _ in range(100):
            if FakeN8n.calls:
                break
            __import__("time").sleep(0.05)
        self.assertEqual(FakeN8n.calls[0]["body"]["targets"]["semester"]["actual"], 700000000)


if __name__ == "__main__":
    unittest.main()
