import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import generate_report as report

HEADERS = ["Record Key", "No", "Company", "BU", "Channel", "Source", "Campaign", "Campaign Hardware", "Industry", "Remark",
           "Inbound Date", "MQL Date", "SQL Date", "Proposal Price Quote Date", " Total Contract SQL", " ARR + OTF (Tanpa PPN) ",
           "Deal Won Date", " Total Contract Deal Won", "Deals Number", "Deals Number2"]


def lead(key, bu, hw, inbound, mql="", sql_date="", ppq="", contract="", arr="", won="", won_value="", company=None, campaign="Camp A"):
    return {"Record Key": key, "No": key, "Company": company or f"Co{key}", "BU": bu, "Channel": "Paid", "Source": "Google Ads",
            "Campaign": campaign, "Campaign Hardware": hw, "Industry": "Mfg", "Remark": "", "Inbound Date": inbound, "MQL Date": mql,
            "SQL Date": sql_date, "Proposal Price Quote Date": ppq, " Total Contract SQL": contract, " ARR + OTF (Tanpa PPN) ": arr,
            "Deal Won Date": won, " Total Contract Deal Won": won_value, "Deals Number": "", "Deals Number2": ""}


LEADS = [
    lead("1", "BU1", "GPS", "9/21/2026", mql="9/22/2026", ppq="9/24/2026", arr="Rp 1.000.000", contract="Rp 9.000.000", sql_date="9/23/2026"),
    lead("2", "BU1", "Dashcam", "9/14/2026", mql="9/15/2026"),
    lead("3", "BU2", "Ecosystem", "9/22/2026", mql="9/23/2026", sql_date="9/25/2026", contract="Rp 5.000.000", ppq="9/26/2026", arr="Rp 111.000"),
    lead("4", "BU2", "Fuel", "9/10/2026", mql="9/11/2026", sql_date="9/16/2026", contract="Rp 700.000"),
    lead("5", "BU2", "GPS", "9/23/2026", won="9/27/2026", won_value="Rp 2.500.000", sql_date="9/24/2026", contract="Rp 3.000.000"),
]


def write_table(path, leads, headers=HEADERS):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(leads)


def run(*args):
    return subprocess.run([sys.executable, str(ROOT / "generate_report.py"), *map(str, args)], capture_output=True, text=True)


class DateTests(unittest.TestCase):
    def test_times_are_ignored_and_ambiguous_forms_are_still_rejected(self):
        from datetime import date
        parse = lambda v: report.parse_date(v, "x")
        for text in ("2026-01-19", "2026-01-19 00:00:00", "2026-01-19 17:30", "2026-01-19T00:00:00", "2026-01-19T00:00:00.000Z", "2026-01-19 00:00:00+07:00", "2026-01-19 9:05:01", "1/19/2026", "1/19/2026 5:30 PM", "01/19/2026 17:30:00"):
            self.assertEqual(parse(text), date(2026, 1, 19), text)
        self.assertIsNone(parse(""))
        for bad in ("19/01/2026", "2026-13-01", "2026-02-30", "19 Jan 2026", "2026/01/19", "2026-01-19 25:00x", "20260119", "#N/A"):
            with self.assertRaises(ValueError, msg=bad):
                parse(bad)


class MoneyTests(unittest.TestCase):
    def tearDown(self):
        report.use_profile(report.load_profile("bu1"))

    def test_bu2_accepts_decimals_in_unambiguous_formats(self):
        report.use_profile(report.load_profile("bu2"))
        parse = lambda v: report.parse_money(v, "x")
        self.assertEqual(parse("12033683238.62"), report.Decimal("12033683238.62"))
        self.assertEqual(parse("Rp 1.234.567,89"), report.Decimal("1234567.89"))
        self.assertEqual(parse("1,234,567.50"), report.Decimal("1234567.50"))
        self.assertEqual(parse("1.350.000"), 1350000)
        self.assertEqual(parse("1.350"), 1350)
        self.assertEqual(parse("2500000.00"), 2500000)
        self.assertEqual(parse(" Rp - "), 0)
        for bad in ("1.234.567,891", "12,5,6", "abc", "1e9"):
            with self.assertRaises(ValueError):
                parse(bad)

    def test_bu1_still_rejects_decimals(self):
        report.use_profile(report.load_profile("bu1"))
        with self.assertRaises(ValueError):
            report.parse_money("1234567.89", "x")

    def test_display_rounds_half_up_but_sums_stay_exact(self):
        report.use_profile(report.load_profile("bu2"))
        total = report.parse_money("100.50", "x") + report.parse_money("200.50", "x")
        self.assertEqual(total, report.Decimal("301.00"))
        self.assertEqual(report.money(report.Decimal("12033683238.62")), "Rp 12.033.683.239")
        self.assertEqual(report.money(report.Decimal("0.5")), "Rp 1")


class TableModeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.table = self.root / "customers.csv"
        write_table(self.table, LEADS)

    def tearDown(self):
        self.tmp.cleanup()

    def audit(self, out):
        return json.loads(out.with_suffix(".audit.json").read_text())

    def test_bu1_uses_proposal_date_and_arr_and_ignores_bu2_rows(self):
        out = self.root / "bu1.html"
        result = run("--table", self.table, "--bu", "bu1", "--period", "2026-W39", "--output", out)
        self.assertEqual(result.returncode, 0, result.stderr)
        audit = self.audit(out)
        self.assertEqual(audit["source"], "table")
        self.assertEqual(audit["metrics"]["now"]["Submission"], 1)
        self.assertEqual(audit["metrics"]["now"]["SQL"], 1)
        self.assertEqual(audit["metrics"]["now"]["SQL Value"], 1000000)
        self.assertEqual(audit["inputs"]["table"]["rows_in_bu"], 2)
        self.assertNotIn("Ecosystem", out.read_text())

    def test_bu2_uses_sql_date_total_contract_sql_and_ecosystem(self):
        out = self.root / "bu2.html"
        result = run("--table", self.table, "--bu", "bu2", "--period", "2026-W39", "--output", out)
        self.assertEqual(result.returncode, 0, result.stderr)
        audit = self.audit(out)
        self.assertEqual(audit["stage_date_columns"]["SQL"], "SQL Date")
        self.assertEqual(audit["metrics"]["now"]["SQL"], 2)
        self.assertEqual(audit["metrics"]["now"]["SQL Value"], 8000000)
        self.assertEqual(audit["metrics"]["now"]["Deal Won Value"], 2500000)
        self.assertEqual(audit["metrics"]["prev"]["SQL Value"], 700000)
        html = out.read_text()
        soup = BeautifulSoup(html, "html.parser")
        self.assertNotIn("Campaign Hardware", html)
        self.assertIn("Daftar SQL Ecosystem Week 39", html)
        self.assertEqual([td.get_text() for td in soup.select("table")[0].select("tbody td")], ["Co3", "Mfg", "2026-09-25", "Rp 5.000.000"])
        self.assertEqual(soup.select("table")[-1].select("tbody td")[3].get_text(), "Rp 2.500.000")
        self.assertNotIn("Proposal Price Quote Date", html)
        self.assertIn("Total Contract SQL", soup.get_text())

    def test_bu2_decimal_values_are_summed_exactly(self):
        leads = [dict(r) for r in LEADS]
        leads[2][" Total Contract SQL"] = "5000000.40"
        leads[4][" Total Contract SQL"] = "Rp 3.000.000,35"
        write_table(self.table, leads)
        out = self.root / "dec.html"
        result = run("--table", self.table, "--bu", "bu2", "--period", "2026-W39", "--output", out)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.audit(out)["metrics"]["now"]["SQL Value"], 8000000.75)
        self.assertIn("Rp 8.000.001", out.read_text())

    def test_table_mode_matches_four_stage_csvs(self):
        stage_rows = {
            "Submission": [dict(r, Remark="") for r in LEADS if r["BU"] == "BU2" and r["Inbound Date"]],
            "MQL": [r for r in LEADS if r["BU"] == "BU2" and r["MQL Date"]],
            "SQL": [r for r in LEADS if r["BU"] == "BU2" and r["SQL Date"]],
            "Deal Won": [r for r in LEADS if r["BU"] == "BU2" and r["Deal Won Date"]],
        }
        paths = {}
        for stage, rows in stage_rows.items():
            paths[stage] = self.root / f"BU2 {stage}.csv"
            write_table(paths[stage], rows)
        from_table = self.root / "t.html"
        from_stages = self.root / "s.html"
        self.assertEqual(run("--table", self.table, "--bu", "bu2", "--period", "2026-09", "--output", from_table).returncode, 0)
        result = run("--bu", "bu2", "--input-dir", self.root, "--period", "2026-09", "--output", from_stages)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.audit(from_table)["metrics"], self.audit(from_stages)["metrics"])
        self.assertEqual(self.audit(from_stages)["source"], "stage_csv")
        self.assertEqual(self.audit(from_stages)["metrics"]["now"]["SQL Value"], 8700000)

    def test_unknown_bu_value_lists_what_exists(self):
        write_table(self.table, [dict(r, BU="Bisnis Unit 9") for r in LEADS])
        result = run("--table", self.table, "--bu", "bu1", "--period", "2026-W39", "--output", self.root / "x.html")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Bisnis Unit 9", result.stderr)

    def test_duplicate_record_key_is_rejected_unless_allowed(self):
        write_table(self.table, LEADS + [dict(LEADS[0], Company="Copy")])
        out = self.root / "d.html"
        result = run("--table", self.table, "--bu", "bu1", "--period", "2026-W39", "--output", out)
        self.assertEqual(result.returncode, 2)
        self.assertIn("Record Key", result.stderr)
        result = run("--table", self.table, "--bu", "bu1", "--period", "2026-W39", "--allow-duplicate-keys", "--output", out)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.audit(out)["inputs"]["table"]["duplicate_record_keys"], 1)

    def test_all_problems_are_reported_at_once_grouped_by_column(self):
        leads = [dict(r) for r in LEADS]
        leads[0]["Proposal Price Quote Date"] = "19/09/2026"
        leads[1]["Inbound Date"] = "kemarin"
        leads[2][" Total Contract SQL"] = "#N/A"
        leads[3][" Total Contract SQL"] = "Rp ??"
        write_table(self.table, leads)
        result = run("--table", self.table, "--bu", "bu2", "--period", "2026-W39", "--output", self.root / "bad.html")
        self.assertEqual(result.returncode, 2)
        message = result.stderr
        self.assertIn("Total Contract SQL: 2 baris nilai uang tidak valid", message)
        self.assertEqual(message.count("\n"), 1, "one line, so the service can return it whole")
        self.assertNotIn("Traceback", message)

    def test_date_time_text_in_the_tracker_is_accepted(self):
        leads = [dict(r) for r in LEADS]
        leads[2]["SQL Date"] = "2026-09-25 00:00:00"
        leads[4]["Deal Won Date"] = "2026-09-27 08:15:00"
        write_table(self.table, leads)
        out = self.root / "dt.html"
        result = run("--table", self.table, "--bu", "bu2", "--period", "2026-W39", "--output", out)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.audit(out)["metrics"]["now"]["SQL Value"], 8000000)
        self.assertEqual(self.audit(out)["metrics"]["now"]["Deal Won"], 1)

    def test_missing_required_column_is_named(self):
        headers = [h for h in HEADERS if h != "SQL Date"]
        write_table(self.table, [{k: v for k, v in r.items() if k != "SQL Date"} for r in LEADS], headers)
        result = run("--table", self.table, "--bu", "bu2", "--period", "2026-W39", "--output", self.root / "m.html")
        self.assertEqual(result.returncode, 2)
        self.assertIn("SQL Date", result.stderr)

    def test_analysis_keys_follow_report_products(self):
        out = self.root / "bu2.html"
        self.assertEqual(run("--table", self.table, "--bu", "bu2", "--period", "2026-W39", "--output", out).returncode, 0)
        analysis = self.root / "a.json"
        analysis.write_text(json.dumps({"executive_summary": "Ekosistem <b>naik</b>"}))
        final = self.root / "final.html"
        apply = [sys.executable, str(ROOT / "apply_analysis.py"), "--report", str(out), "--analysis", str(analysis), "--output", str(final)]
        self.assertEqual(subprocess.run(apply, capture_output=True, text=True).returncode, 0)
        analysis.write_text(json.dumps({"hardware_dashcam": "x"}))
        self.assertNotEqual(subprocess.run(apply, capture_output=True, text=True).returncode, 0)
        analysis.write_text(json.dumps({"executive_summary": "Ekosistem <b>naik</b>"}))
        self.assertIn("Ekosistem &lt;b&gt;naik&lt;/b&gt;", final.read_text())
        bu1 = self.root / "bu1.html"
        self.assertEqual(run("--table", self.table, "--bu", "bu1", "--period", "2026-W39", "--output", bu1).returncode, 0)
        apply[apply.index("--report") + 1] = str(bu1)
        analysis.write_text(json.dumps({"hardware_ecosystem": "x"}))
        rejected = subprocess.run(apply, capture_output=True, text=True)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("hardware_ecosystem", rejected.stderr)
        analysis.write_text(json.dumps({"hardware_dashcam": "Dashcam <b>naik</b>"}))
        accepted = subprocess.run(apply, capture_output=True, text=True)
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        self.assertIn("Dashcam &lt;b&gt;naik&lt;/b&gt;", final.read_text())


if __name__ == "__main__":
    unittest.main()


class SqlAgeRuleTests(unittest.TestCase):
    """BU1: a SQL counts only when its date is at most one calendar year after the Inbound Date. BU2 has no such rule."""

    def setUp(self):
        from datetime import date
        self.date = date
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        report.use_profile(report.load_profile("bu1"))
        self.addCleanup(lambda: report.use_profile(report.load_profile("bu1")))

    def rows(self, *leads):
        path = self.root / "t.csv"
        write_table(path, list(leads))
        return report.read_table(path)

    def test_exactly_one_year_is_kept_and_one_day_later_is_dropped(self):
        data, info = self.rows(
            lead("1", "BU1", "GPS", "9/24/2025", ppq="9/24/2026", arr="Rp 100"),
            lead("2", "BU1", "GPS", "9/24/2025", ppq="9/25/2026", arr="Rp 200"),
            lead("3", "BU1", "GPS", "9/20/2026", ppq="9/21/2026", arr="Rp 300"))
        self.assertEqual(sorted(r["Record Key"] for r in data["SQL"]), ["1", "3"])
        self.assertEqual(info["sql_expired"], 1)
        self.assertEqual(len(data["Submission"]), 3)  # other stages are untouched

    def test_missing_inbound_date_stays_and_leap_day_uses_28_feb(self):
        self.assertEqual(report.add_years(self.date(2024, 2, 29), 1), self.date(2025, 2, 28))
        data, _ = self.rows(lead("1", "BU1", "GPS", "", ppq="9/24/2026", arr="Rp 100"))
        self.assertEqual(len(data["SQL"]), 1)

    def test_expired_sql_is_not_in_performa_but_the_lead_is(self):
        data, _ = self.rows(lead("1", "BU1", "GPS", "1/5/2025", mql="1/6/2025", ppq="9/24/2026", arr="Rp 500"))
        result = report.performance(data, self.date(2026, 9, 27))
        self.assertEqual(len(result["leads"]), 1)
        sub, mql, sql, won, sql_value, won_value = result["leads"][0][:6]
        self.assertGreater(sub, 0)
        self.assertGreater(mql, 0)
        self.assertEqual((sql, sql_value), (0, 0))

    def test_report_excludes_expired_sql_from_count_and_value(self):
        path = self.root / "t.csv"
        write_table(path, [
            lead("1", "BU1", "GPS", "9/21/2026", mql="9/22/2026", ppq="9/24/2026", arr="Rp 1.000.000"),
            lead("2", "BU1", "GPS", "1/5/2025", ppq="9/24/2026", arr="Rp 9.000.000")])
        out = self.root / "o.html"
        result = run("--table", path, "--bu", "bu1", "--period", "2026-W39", "--output", out)
        self.assertEqual(result.returncode, 0, result.stderr)
        audit = json.loads(out.with_suffix(".audit.json").read_text())
        self.assertEqual(audit["metrics"]["now"]["SQL"], 1)
        self.assertEqual(audit["metrics"]["now"]["SQL Value"], 1000000)
        self.assertEqual(audit["inputs"]["table"]["sql_expired"], 1)

    def test_bu2_has_no_age_rule(self):
        report.use_profile(report.load_profile("bu2"))
        data, info = self.rows(lead("1", "BU2", "Ecosystem", "1/5/2025", sql_date="9/24/2026", contract="Rp 100"))
        self.assertEqual(len(data["SQL"]), 1)
        self.assertNotIn("sql_expired", info)
