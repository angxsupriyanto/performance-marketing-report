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
        return BeautifulSoup(out.read_text(), "html.parser"), facts, out

    def test_bu1_hardware_table_has_target_and_progress_but_no_won_or_junk_columns(self):
        soup, facts, _ = self.build("bu1", "2026-W39")
        headers = [th.get_text() for th in soup.select(".hardware-section > .table-wrap th")]
        self.assertEqual(headers, ["Produk", "Submission", "MQL", "SQL", "SQL Value", "Target", "Progress"])
        first = soup.select(".hardware-section > .table-wrap tbody tr")[1]  # GPS Tracker
        cells = first.select("td")
        self.assertEqual(cells[0].get_text(), "GPS Tracker")
        self.assertEqual(cells[4].select_one("strong").get_text(), "Rp 1.000.000")
        self.assertEqual(cells[5]["data-slot"], "target")
        self.assertEqual(cells[6]["data-slot"], "progress")
        self.assertEqual(cells[6]["data-product"], "GPS Tracker")
        self.assertEqual(cells[6]["data-mtd"], "1000000")
        self.assertEqual(cells[5].get_text(), "Belum diatur")
        self.assertEqual(soup.select(".hardware-section > .table-wrap tfoot td")[0].get_text(), "TOTAL 5 PRODUK")

    def test_bu1_gets_a_funnel_block_and_an_analysis_slot_per_hardware(self):
        soup, facts, out = self.build("bu1", "2026-W39")
        blocks = soup.select(".hw-funnel-block")
        self.assertEqual([b["data-hardware"] for b in blocks], ["Dashcam", "GPS Tracker", "Fuel", "MDVR", "OBD"])
        self.assertEqual([b.select_one(".tgt-stack")["data-week"] for b in blocks][1], "1000000")
        keys = apply_analysis.analysis_keys(out.read_text())
        self.assertIn("hardware_gps_tracker", keys)
        self.assertIn("hardware_summary", keys)
        self.assertEqual(soup.select_one(".hardware-section .product-analysis"), None)
        final = apply_analysis.apply_analysis(out.read_text(), {"hardware_gps_tracker": "GPS naik"})
        self.assertIn("GPS naik", BeautifulSoup(final, "html.parser").select_one('.hw-funnel-block[data-hardware="GPS Tracker"] .analysis-body').get_text())

    def test_bu1_target_cards_carry_actuals_in_rupiah(self):
        soup, facts, _ = self.build("bu1", "2026-W39")
        cards = soup.select(".target-progress .tgt")
        self.assertEqual([c["data-scope"] for c in cards], ["semester", "year"])
        self.assertEqual([c["data-key"] for c in cards], ["2026-S2", "2026"])
        self.assertEqual([c["data-unit"] for c in cards], ["idr", "idr"])
        self.assertEqual(cards[0]["data-actual"], "1000000")
        self.assertIn("target belum diatur", cards[0].select_one(".tgt-line").get_text())
        self.assertIsNotNone(soup.select_one(".tgt-month[data-month-key='2026-09']"))
        self.assertEqual(facts["progress"]["total"]["year"]["sql_value"], 1000000)

    def test_straddling_week_is_accumulated_into_the_thursday_month(self):
        leads = [
            lead("1", "BU1", "GPS", "9/29/2026", mql="9/30/2026", ppq="9/30/2026", arr="Rp 1.000.000"),
            lead("2", "BU1", "Dashcam", "10/1/2026", mql="10/2/2026", ppq="10/2/2026", arr="Rp 2.000.000"),
            lead("3", "BU1", "GPS", "9/15/2026", ppq="9/20/2026", arr="Rp 4.000.000"),
            lead("4", "BU1", "GPS", "10/5/2026", ppq="10/6/2026", arr="Rp 8.000.000"),
        ]
        soup, facts, _ = self.build("bu1", "2026-W40", leads)
        hardware = facts["progress"]["hardware"]
        self.assertEqual(facts["progress"]["windows"]["month"]["key"], "2026-10")
        self.assertEqual(hardware["GPS Tracker"], {"week_sql_value": 1000000, "month_to_date": 1000000, "month_before_period": 0})
        self.assertEqual(hardware["Dashcam"]["month_to_date"], 2000000)
        self.assertEqual(facts["progress"]["total"]["month"]["sql_value"], 3000000)
        self.assertEqual(facts["progress"]["total"]["semester"]["sql_value"], 7000000)

    def test_month_to_date_before_the_period_is_separated(self):
        leads = [
            lead("1", "BU1", "GPS", "10/6/2026", ppq="10/7/2026", arr="Rp 1.000.000"),
            lead("2", "BU1", "GPS", "10/13/2026", ppq="10/14/2026", arr="Rp 2.000.000"),
        ]
        _, facts, _ = self.build("bu1", "2026-W42", leads)
        self.assertEqual(facts["progress"]["hardware"]["GPS Tracker"], {"week_sql_value": 2000000, "month_to_date": 3000000, "month_before_period": 1000000})

    def test_bu2_has_no_hardware_sections_but_a_focus_progress_and_lists(self):
        soup, facts, out = self.build("bu2", "2026-W39")
        self.assertIsNone(soup.select_one(".hardware-section"))
        self.assertIsNone(soup.select_one(".hw-funnel-block"))
        self.assertEqual(facts["progress"]["focus_product"], "Ecosystem")
        self.assertEqual(facts["progress"]["total"]["year"]["focus_sql"], 1)
        self.assertEqual(facts["focus_period"], {"product": "Ecosystem", "sql": 1, "sql_value": 5000000})
        titles = [h.get_text() for h in soup.select("section.section .section-head h2")]
        self.assertLess(titles.index("Daftar SQL · Week 39"), titles.index("Daftar SQL Ecosystem · Week 39"))
        self.assertLess(titles.index("Daftar SQL Ecosystem · Week 39"), titles.index("Daftar Deal Won · Week 39"))
        won = soup.select(".won-list tbody td")
        self.assertEqual([c.get_text() for c in won], ["Co5", "Mfg", "Camp A", "Rp 2.500.000", "4 hari"])
        self.assertEqual([h.get_text() for h in soup.select(".won-list th")], ["Company", "Industry", "Campaign", "Deal Value", "Inbound ke Deal Won"])
        self.assertEqual([h.get_text() for h in soup.select(".focus-list th")], ["Company", "Industry", "Tanggal SQL", "SQL Value"])
        keys = apply_analysis.analysis_keys(out.read_text())
        self.assertNotIn("hardware_summary", keys)
        self.assertFalse([k for k in keys if k.startswith("hardware_")])

    def test_bu2_lists_say_so_when_the_period_has_none(self):
        leads = [
            lead("1", "BU2", "GPS", "9/21/2026", mql="9/22/2026", sql_date="9/23/2026", contract="Rp 3.000.000"),
        ]
        soup, _, _ = self.build("bu2", "2026-W39", leads)
        self.assertIn("Tidak ada SQL Ecosystem di Week 39.", soup.select_one(".focus-list").get_text())
        self.assertIn("Tidak ada Deal Won di Week 39.", soup.select_one(".won-list").get_text())
        self.assertIsNone(soup.select_one(".focus-list table"))

    def test_bu1_has_no_ecosystem_or_deal_won_list(self):
        soup, _, _ = self.build("bu1", "2026-W39")
        self.assertIsNone(soup.select_one(".focus-list"))
        self.assertIsNone(soup.select_one(".won-list"))

    def test_a_monthly_report_accumulates_over_calendar_windows(self):
        soup, facts, _ = self.build("bu1", "2026-09")
        self.assertEqual(facts["progress"]["windows"]["month"]["start"], "2026-09-01")
        self.assertEqual(facts["progress"]["total"]["year"]["sql_value"], 1000000)
        self.assertEqual(soup.select(".target-progress .tgt")[0]["data-key"], "2026-S2")


if __name__ == "__main__":
    unittest.main()
