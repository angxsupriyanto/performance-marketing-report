import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import apply_analysis  # noqa: E402
import report_view  # noqa: E402
import generate_report as report  # noqa: E402
from test_table_mode import LEADS, lead, run, write_table  # noqa: E402


class WindowTests(unittest.TestCase):
    def window(self, period, scope):
        win = report.window(report.parse_period(period), scope)
        return win["key"], win["start"], win["end"]

    def test_a_week_belongs_to_the_month_that_holds_its_thursday(self):
        # W40 2026 runs 28 Sep - 4 Oct, Thursday is 1 Oct.
        self.assertEqual(self.window("2026-W40", "month"), ("2026-10", date(2026, 9, 28), date(2026, 10, 4)))
        # W44 2026 runs 26 Oct - 1 Nov, Thursday is 29 Oct.
        self.assertEqual(self.window("2026-W44", "month")[0], "2026-10")
        self.assertEqual(self.window("2026-W44", "month")[1], date(2026, 9, 28))
        self.assertEqual(self.window("2026-W39", "month"), ("2026-09", date(2026, 8, 31), date(2026, 9, 27)))

    def test_semester_and_year_use_the_same_thursday_rule(self):
        self.assertEqual(self.window("2026-W27", "semester"), ("2026-S2", date(2026, 6, 29), date(2026, 7, 5)))
        self.assertEqual(self.window("2026-W26", "semester")[0], "2026-S1")
        self.assertEqual(self.window("2026-W01", "year"), ("2026", date(2025, 12, 29), date(2026, 1, 4)))
        self.assertEqual(self.window("2026-W42", "year")[1], date(2025, 12, 29))

    def test_a_calendar_month_report_uses_calendar_windows(self):
        self.assertEqual(self.window("2026-09", "month"), ("2026-09", date(2026, 9, 1), date(2026, 9, 30)))
        self.assertEqual(self.window("2026-09", "semester"), ("2026-S2", date(2026, 7, 1), date(2026, 9, 30)))
        self.assertEqual(self.window("2026-09", "year"), ("2026", date(2026, 1, 1), date(2026, 9, 30)))


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def build(self, bu, period, leads=LEADS):
        table = self.root / "t.csv"
        write_table(table, leads)
        out = self.root / f"{bu}.html"
        result = run("--table", table, "--bu", bu, "--period", period, "--output", out)
        self.assertEqual(result.returncode, 0, result.stderr)
        facts = json.loads(out.with_suffix(".facts.json").read_text())
        return report_view.extract_view(out.read_text()), facts, out

    def test_bu1_hardware_rows_carry_week_and_month_to_date_values(self):
        view, facts, _ = self.build("bu1", "2026-W39")
        gps = [h for h in view["hardware"] if h["name"] == "GPS Tracker"][0]
        self.assertEqual((gps["submission"], gps["mql"], gps["sql"], gps["week"], gps["before"], gps["month_to_date"]), (1, 1, 1, 1000000, 0, 1000000))
        self.assertEqual(gps["slug"], "gps_tracker")
        self.assertEqual([h["name"] for h in view["hardware"]], ["Dashcam", "GPS Tracker", "Fuel", "MDVR", "OBD"])
        self.assertEqual(view["month"], {"key": "2026-09", "label": "September 2026"})

    def test_analysis_keys_follow_the_panels_on_the_page(self):
        view, _, out = self.build("bu1", "2026-W39")
        keys = apply_analysis.analysis_keys(out.read_text())
        self.assertEqual(keys, view["analysis_keys"])
        self.assertEqual(keys, ["executive_summary", "hardware_summary", "hardware_dashcam", "hardware_gps_tracker", "hardware_fuel", "hardware_mdvr", "hardware_obd", "next_action"])
        final = apply_analysis.apply_analysis(out.read_text(), {"hardware_gps_tracker": "GPS naik"})
        self.assertIn("GPS naik", BeautifulSoup(final, "html.parser").select_one('[data-analysis="hardware_gps_tracker"]').get_text())

    def test_progress_actuals_are_in_rupiah_for_bu1(self):
        view, facts, _ = self.build("bu1", "2026-W39")
        self.assertEqual(view["progress"], {"unit": "idr", "semester": {"key": "2026-S2", "label": "Semester 2 2026", "actual": 1000000}, "year": {"key": "2026", "year": "2026", "actual": 1000000}})
        self.assertEqual(facts["progress"]["total"]["year"]["sql_value"], 1000000)

    def test_straddling_week_is_accumulated_into_the_thursday_month(self):
        leads = [
            lead("1", "BU1", "GPS", "9/29/2026", mql="9/30/2026", ppq="9/30/2026", arr="Rp 1.000.000"),
            lead("2", "BU1", "Dashcam", "10/1/2026", mql="10/2/2026", ppq="10/2/2026", arr="Rp 2.000.000"),
            lead("3", "BU1", "GPS", "9/15/2026", ppq="9/20/2026", arr="Rp 4.000.000"),
            lead("4", "BU1", "GPS", "10/5/2026", ppq="10/6/2026", arr="Rp 8.000.000"),
        ]
        view, facts, _ = self.build("bu1", "2026-W40", leads)
        hardware = facts["progress"]["hardware"]
        self.assertEqual(facts["progress"]["windows"]["month"]["key"], "2026-10")
        self.assertEqual(hardware["GPS Tracker"], {"week_sql_value": 1000000, "month_to_date": 1000000, "month_before_period": 0})
        self.assertEqual(hardware["Dashcam"]["month_to_date"], 2000000)
        self.assertEqual(facts["progress"]["total"]["month"]["sql_value"], 3000000)
        self.assertEqual(facts["progress"]["total"]["semester"]["sql_value"], 7000000)
        self.assertEqual(view["month"]["label"], "Oktober 2026")

    def test_month_to_date_before_the_period_is_separated(self):
        leads = [
            lead("1", "BU1", "GPS", "10/6/2026", ppq="10/7/2026", arr="Rp 1.000.000"),
            lead("2", "BU1", "GPS", "10/13/2026", ppq="10/14/2026", arr="Rp 2.000.000"),
        ]
        view, facts, _ = self.build("bu1", "2026-W42", leads)
        self.assertEqual(facts["progress"]["hardware"]["GPS Tracker"], {"week_sql_value": 2000000, "month_to_date": 3000000, "month_before_period": 1000000})
        gps = [h for h in view["hardware"] if h["name"] == "GPS Tracker"][0]
        self.assertEqual((gps["week"], gps["before"], gps["month_to_date"]), (2000000, 1000000, 3000000))

    def test_bu2_view_has_focus_progress_and_lists_but_no_hardware(self):
        view, facts, out = self.build("bu2", "2026-W39")
        self.assertNotIn("hardware", view)
        self.assertEqual(facts["progress"]["focus_product"], "Ecosystem")
        self.assertEqual(facts["progress"]["total"]["year"]["focus_sql"], 1)
        self.assertEqual(facts["focus_period"], {"product": "Ecosystem", "sql": 1, "sql_value": 5000000})
        self.assertEqual(view["progress"]["unit"], "count")
        self.assertEqual(view["progress"]["year"]["actual"], 1)
        self.assertEqual(view["focus"]["rows"], [{"company": "Co3", "industry": "Mfg", "date": "2026-09-25", "value": 5000000}])
        self.assertEqual(view["won_list"]["rows"], [{"company": "Co5", "industry": "Mfg", "campaign": "Camp A", "value": 2500000, "timing": "4 hari", "same": True}])
        self.assertEqual(apply_analysis.analysis_keys(out.read_text()), ["executive_summary", "next_action"])

    def test_bu2_lists_say_so_when_the_period_has_none(self):
        leads = [lead("1", "BU2", "GPS", "9/21/2026", mql="9/22/2026", sql_date="9/23/2026", contract="Rp 3.000.000")]
        _, _, out = self.build("bu2", "2026-W39", leads)
        text = BeautifulSoup(out.read_text(), "html.parser").get_text(" ")
        self.assertIn("Tidak ada SQL Ecosystem di Week 39.", text)
        self.assertIn("Tidak ada Deal Won di Week 39.", text)

    def test_a_monthly_report_accumulates_over_calendar_windows(self):
        view, facts, _ = self.build("bu1", "2026-09")
        self.assertEqual(facts["progress"]["windows"]["month"]["start"], "2026-09-01")
        self.assertEqual(facts["progress"]["total"]["year"]["sql_value"], 1000000)
        self.assertEqual(view["progress"]["semester"]["key"], "2026-S2")
        self.assertEqual((view["label"], view["same_word"]), ("Sep 2026", "Same-month"))


if __name__ == "__main__":
    unittest.main()
