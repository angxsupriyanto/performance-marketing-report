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
            self.assertEqual(len(soup.select(".sql-list tbody tr")), 1)
            self.assertIn("Backlog", soup.select_one(".sql-list tbody").get_text())
            self.assertNotIn("<script>alert(1)</script>", out.read_text())
            self.assertTrue(all(not x.get_text(strip=True) for x in soup.select(".executive-prose,.analysis-body,.hardware-analysis-summary p,.product-analysis p")))


if __name__ == "__main__":
    unittest.main()
