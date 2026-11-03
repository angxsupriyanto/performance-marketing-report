import csv
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import generate_report as report
from bs4 import BeautifulSoup


class ReportTests(unittest.TestCase):
    def test_iso_boundary_and_currency_are_explicit(self):
        self.assertEqual(date.fromisocalendar(2027, 1, 1).isoformat(), "2027-01-04")
        self.assertEqual(report.parse_money("Rp 1.350.000", "x"), 1350000)
        self.assertEqual(report.parse_money(" Rp - ", "x"), 0)
        with self.assertRaises(ValueError):
            report.parse_money("Rp 1.350,50", "x")
        with self.assertRaises(ValueError):
            report.parse_date("17/09/2026", "x")

    def test_period_parsing(self):
        week = report.parse_period("2026-W39")
        self.assertEqual((week.start.isoformat(), week.end.isoformat(), week.prev_start.isoformat()), ("2026-09-21", "2026-09-27", "2026-09-14"))
        self.assertEqual((week.short, week.prev_short), ("W39", "W38"))
        january = report.parse_period("2027-01")
        self.assertEqual((january.start.isoformat(), january.end.isoformat()), ("2027-01-01", "2027-01-31"))
        self.assertEqual((january.prev_start.isoformat(), january.prev_end.isoformat()), ("2026-12-01", "2026-12-31"))
        self.assertEqual(report.parse_period("2028-03").prev_end.isoformat(), "2028-02-29")
        for bad in ("2026-13", "2026-W5", "september"):
            with self.assertRaises(ValueError):
                report.parse_period(bad)

    def test_unknown_profile_is_rejected(self):
        with self.assertRaises(ValueError):
            report.load_profile("bu-tidak-ada")

    def test_generated_numbers_and_empty_analysis(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_paths = {}
            data = {
                "Submission": [
                    {"Company":"<script>alert(1)</script>","Channel":"Paid","Source":"Google Ads","Campaign":"Solusi - GPS Tracker - CPC","Campaign Hardware":"GPS","Industry":"Manufaktur","Remark":"Follow Up","Inbound Date":"9/21/2026","MQL Date":"9/21/2026"},
                    {"Company":"Lead baru","Channel":"Organic","Source":"Website","Campaign":"Halaman - Home","Campaign Hardware":"","Industry":"","Remark":"Junk leads","Inbound Date":"9/22/2026","MQL Date":""},
                    {"Company":"Grand Total","Inbound Date":""},
                ],
                "MQL": [{"Company":"<script>alert(1)</script>","Channel":"Paid","Source":"Google Ads","Campaign":"Solusi - GPS Tracker - CPC","Campaign Hardware":"GPS","Industry":"Manufaktur","Inbound Date":"9/21/2026","MQL Date":"9/21/2026"}],
                "SQL": [{"Company":"Lead lama","Channel":"Paid","Source":"Google Ads","Campaign":"Solusi - GPS Tracker - CPC","Campaign Hardware":"GPS","Industry":"Manufaktur","Inbound Date":"9/17/2026","Proposal Price Quote Date":"9/23/2026",report.SQL_VALUE:"Rp 1.350.000"}],
                "Deal Won": [{"Company":"Lead lama","Channel":"Paid","Source":"Google Ads","Campaign":"Solusi - GPS Tracker - CPC","Campaign Hardware":"GPS","Industry":"Manufaktur","Inbound Date":"9/17/2026","Deal Won Date":"9/25/2026",report.WON_VALUE:"Rp 900.000"}],
            }
            for stage, rows in data.items():
                path = root / (stage.replace(" ", "_") + ".csv")
                keys = list(dict.fromkeys(k for row in rows for k in row))
                with path.open("w", encoding="utf-8", newline="") as handle:
                    writer = csv.DictWriter(handle, fieldnames=keys)
                    writer.writeheader();writer.writerows(rows)
                input_paths[stage] = path
            out = root / "report.html"
            cmd = [sys.executable, str(ROOT / "generate_report.py"), "--submission", str(input_paths["Submission"]), "--mql", str(input_paths["MQL"]), "--sql", str(input_paths["SQL"]), "--won", str(input_paths["Deal Won"]), "--week", "2026-W39", "--output", str(out)]
            result = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            audit = json.loads(out.with_suffix(".audit.json").read_text())
            self.assertEqual(audit["metrics"]["now"]["Submission"], 2)
            self.assertEqual(audit["metrics"]["now"]["SQL Value"], 1350000)
            self.assertEqual(audit["same_week"]["SQL"], 0)
            soup = BeautifulSoup(out.read_text(), "html.parser")
            sql_table = [t for t in soup.select("table") if "Daftar SQL Week 39" in t.select_one("caption").get_text()][0]
            self.assertEqual(len(sql_table.select("tbody tr")), 1)
            self.assertIn("Backlog", sql_table.select_one("tbody").get_text())
            self.assertNotIn("<script>alert(1)</script>", out.read_text())
            panels = soup.select("[data-analysis]")
            self.assertEqual(sorted(p["data-analysis"] for p in panels), sorted(["executive_summary", "hardware_summary", "next_action"] + ["hardware_" + n for n in ("dashcam", "gps_tracker", "fuel", "mdvr", "obd")]))
            self.assertTrue(all(p.get_text() == "Kosong sampai analisis dibuat." for p in panels))

            monthly = root / "monthly.html"
            cmd[cmd.index("--week") + 1] = "2026-09"
            cmd[cmd.index("--output") + 1] = str(monthly)
            result = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            audit = json.loads(monthly.with_suffix(".audit.json").read_text())
            self.assertEqual(audit["period_kind"], "month")
            self.assertEqual(audit["metrics"]["now"]["Submission"], 2)
            self.assertEqual(audit["metrics"]["now"]["SQL Value"], 1350000)
            self.assertEqual(audit["metrics"]["now"]["Deal Won"], 1)
            html = monthly.read_text()
            self.assertIn("Sep 2026 (1 sampai 30 Sep 2026) vs Agu 2026 (1 sampai 31 Agu 2026)", html)
            self.assertNotIn("Week —", html)
            self.assertNotIn("W—", html)
            self.assertNotIn("minggu", html)


if __name__ == "__main__":
    unittest.main()
