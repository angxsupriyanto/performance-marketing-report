"""How long a lead's MQL, SQL and Deal Won stay valid after its Inbound Date: general limits per stage, rules per Remark, and where the settings come from."""
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
import generate_report as report  # noqa: E402
from test_table_mode import lead, run, write_table  # noqa: E402

NONE = {"MQL": None, "SQL": None, "Deal Won": None}


def settings(defaults=None, remarks=None):
    return {"defaults": {**NONE, **(defaults or {})}, "remarks": remarks or []}


def with_remark(remark, **kwargs):
    row = lead(**kwargs)
    row["Remark"] = remark
    return row


class NormalizeTests(unittest.TestCase):
    def test_a_valid_setting_is_returned_clean(self):
        cfg = report.normalize_validity({"defaults": {"MQL": None, "SQL": 6, "Deal Won": 12}, "remarks": [{"remark": "  Trial ", "MQL": "default", "SQL": 12, "Deal Won": None}]})
        self.assertEqual(cfg["defaults"], {"MQL": None, "SQL": 6, "Deal Won": 12})
        self.assertEqual(cfg["remarks"], [{"remark": "Trial", "MQL": "default", "SQL": 12, "Deal Won": None}])
        self.assertEqual(report.normalize_validity({"defaults": NONE})["remarks"], [])

    def test_each_rule_has_a_message(self):
        good = {"defaults": NONE}
        bad = {
            "not an object": [],
            "no defaults": {},
            "missing stage": {"defaults": {"MQL": None, "SQL": None}},
            "extra stage": {"defaults": {**NONE, "Submission": 1}},
            "zero months": {"defaults": {**NONE, "SQL": 0}},
            "too many months": {"defaults": {**NONE, "SQL": 61}},
            "text months": {"defaults": {**NONE, "SQL": "6"}},
            "bool months": {"defaults": {**NONE, "SQL": True}},
            "fraction": {"defaults": {**NONE, "SQL": 1.5}},
            "remarks not a list": {**good, "remarks": {}},
            "rule without text": {**good, "remarks": [{"remark": "  ", "SQL": 6}]},
            "duplicate remark": {**good, "remarks": [{"remark": "Trial"}, {"remark": " trial "}]},
            "bad rule months": {**good, "remarks": [{"remark": "Trial", "SQL": 0}]},
            "too many rules": {**good, "remarks": [{"remark": f"r{i}"} for i in range(31)]},
        }
        for name, raw in bad.items():
            with self.assertRaises(ValueError, msg=name):
                report.normalize_validity(raw)


class ExpiryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        report.use_profile(report.load_profile("bu1"))
        self.addCleanup(lambda: (report.use_profile(report.load_profile("bu1")), report.use_validity(None)))

    def read(self, *leads, config=None):
        report.use_validity(config)
        path = self.root / "t.csv"
        write_table(path, list(leads))
        return report.read_table(path)

    def keys(self, data, stage):
        return sorted(r["Record Key"] for r in data[stage])

    def test_each_stage_has_its_own_limit_and_is_judged_alone(self):
        data, info = self.read(
            lead("1", "BU1", "GPS", "1/5/2026", mql="5/6/2026", ppq="5/7/2026", arr="Rp 100", won="5/8/2026", won_value="Rp 50"),
            config=settings({"MQL": 3, "SQL": 6, "Deal Won": 4}))
        self.assertEqual(self.keys(data, "MQL"), [])  # 1/5 + 3 months = 4/5, the MQL is on 5/6
        self.assertEqual(self.keys(data, "SQL"), ["1"])  # 1/5 + 6 months = 7/5
        self.assertEqual(self.keys(data, "Deal Won"), [])  # 1/5 + 4 months = 5/5
        self.assertEqual(self.keys(data, "Submission"), ["1"])
        self.assertEqual(info["expired"], {"MQL": 1, "SQL": 0, "Deal Won": 1})
        self.assertEqual(info["sql_expired"], 0)

    def test_the_boundary_day_is_kept_and_the_next_day_is_dropped_for_every_stage(self):
        data, _ = self.read(
            lead("1", "BU1", "GPS", "3/24/2026", mql="6/24/2026", ppq="6/24/2026", arr="Rp 1", won="6/24/2026", won_value="Rp 1"),
            lead("2", "BU1", "GPS", "3/24/2026", mql="6/25/2026", ppq="6/25/2026", arr="Rp 1", won="6/25/2026", won_value="Rp 1"),
            config=settings({"MQL": 3, "SQL": 3, "Deal Won": 3}))
        for stage in ("MQL", "SQL", "Deal Won"):
            self.assertEqual(self.keys(data, stage), ["1"], stage)

    def test_a_remark_rule_overrides_the_general_limit_for_that_remark_only(self):
        rule = {"remark": "Trial", "MQL": "default", "SQL": 12, "Deal Won": None}
        data, info = self.read(
            with_remark("Trial", key="1", bu="BU1", hw="GPS", inbound="1/5/2026", ppq="11/20/2026", arr="Rp 100", won="12/20/2026", won_value="Rp 1"),
            with_remark("trial ", key="2", bu="BU1", hw="GPS", inbound="1/5/2026", ppq="11/20/2026", arr="Rp 100"),
            with_remark("Trial 14 hari", key="3", bu="BU1", hw="GPS", inbound="1/5/2026", ppq="11/20/2026", arr="Rp 100"),
            with_remark("", key="4", bu="BU1", hw="GPS", inbound="1/5/2026", ppq="11/20/2026", arr="Rp 100", won="12/20/2026", won_value="Rp 1"),
            config=settings({"SQL": 6, "Deal Won": 6}, [rule]))
        self.assertEqual(self.keys(data, "SQL"), ["1", "2"])  # 12 months for Trial, in any letter case; an exact match, so "Trial 14 hari" keeps the general 6
        self.assertEqual(self.keys(data, "Deal Won"), ["1"])  # Trial has no limit on Deal Won; the lead without Remark keeps 6 months and is dropped
        self.assertEqual(info["expired"], {"MQL": 0, "SQL": 2, "Deal Won": 1})

    def test_a_rule_can_also_add_a_limit_where_the_general_one_has_none(self):
        data, _ = self.read(
            with_remark("Trial", key="1", bu="BU1", hw="GPS", inbound="1/5/2026", mql="9/5/2026"),
            with_remark("", key="2", bu="BU1", hw="GPS", inbound="1/5/2026", mql="9/5/2026"),
            config=settings(remarks=[{"remark": "Trial", "MQL": 3, "SQL": "default", "Deal Won": "default"}]))
        self.assertEqual(self.keys(data, "MQL"), ["2"])

    def test_a_missing_inbound_date_stays_valid(self):
        data, _ = self.read(lead("1", "BU1", "GPS", "", mql="9/5/2026", ppq="9/5/2026", arr="Rp 1", won="9/5/2026", won_value="Rp 1"),
                            config=settings({"MQL": 1, "SQL": 1, "Deal Won": 1}))
        self.assertEqual([len(data[s]) for s in ("MQL", "SQL", "Deal Won")], [1, 1, 1])

    def test_without_settings_the_profile_limit_applies_and_with_settings_they_replace_it(self):
        old = lead("1", "BU1", "GPS", "1/5/2025", ppq="9/24/2026", arr="Rp 500")
        self.assertEqual(self.keys(self.read(old)[0], "SQL"), [])  # BU1 profile: SQL 6 months
        self.assertEqual(self.keys(self.read(old, config=settings())[0], "SQL"), ["1"])  # saved as "no limit": the profile is not consulted
        report.use_profile(report.load_profile("bu2"))
        data, info = self.read(lead("1", "BU2", "Ecosystem", "1/5/2025", sql_date="9/24/2026", contract="Rp 100"))
        self.assertEqual(len(data["SQL"]), 1)
        self.assertNotIn("expired", info)

    def test_audit_info_lists_remark_texts_but_only_when_short_and_capped(self):
        long = "x" * 61
        _, info = self.read(*[with_remark(r, key=str(i), bu="BU1", hw="GPS", inbound="9/1/2026") for i, r in enumerate(["Trial", "Trial", "Junk Leads", long, ""])], config=settings())
        self.assertEqual(info["remark_values"], ["Trial", "Junk Leads"])

    def test_performa_drops_the_expired_stage_but_keeps_the_lead(self):
        data, _ = self.read(lead("1", "BU1", "GPS", "1/5/2026", mql="9/5/2026", ppq="9/24/2026", arr="Rp 500", won="9/25/2026", won_value="Rp 9"),
                            config=settings({"MQL": 3, "SQL": 12, "Deal Won": 3}))
        row = report.performance(data, date(2026, 9, 27))["leads"][0]
        submission, mql, sql, won = row[:4]
        self.assertGreater(submission, 0)
        self.assertEqual((mql, won), (0, 0))
        self.assertGreater(sql, 0)
        self.assertEqual(row[5], 0)  # Deal Won value is zero with it

    def test_the_report_counts_follow_the_settings_and_the_audit_records_them_without_reaching_the_model(self):
        path = self.root / "t.csv"
        write_table(path, [
            lead("1", "BU1", "GPS", "9/21/2026", mql="9/22/2026", ppq="9/24/2026", arr="Rp 1.000.000", won="9/25/2026", won_value="Rp 700"),
            with_remark("Trial", key="2", bu="BU1", hw="GPS", inbound="1/5/2025", mql="9/22/2026", ppq="9/24/2026", arr="Rp 9.000.000", won="9/25/2026", won_value="Rp 800"),
            lead("3", "BU1", "GPS", "1/5/2025", mql="9/22/2026", ppq="9/24/2026", arr="Rp 5.000.000", won="9/25/2026", won_value="Rp 900")])
        config = self.root / "v.json"
        config.write_text(json.dumps(settings({"MQL": 12, "SQL": 12, "Deal Won": 12}, [{"remark": "Trial", "MQL": None, "SQL": None, "Deal Won": None}])))
        out = self.root / "o.html"
        result = run("--table", path, "--bu", "bu1", "--period", "2026-W39", "--output", out, "--validity", config)
        self.assertEqual(result.returncode, 0, result.stderr)
        audit = json.loads(out.with_suffix(".audit.json").read_text())
        now = audit["metrics"]["now"]
        self.assertEqual((now["MQL"], now["SQL"], now["SQL Value"], now["Deal Won"], now["Deal Won Value"]), (2, 2, 10000000, 2, 1500))
        table = audit["inputs"]["table"]
        self.assertEqual(table["expired"], {"MQL": 1, "SQL": 1, "Deal Won": 1})
        self.assertEqual(table["validity"]["defaults"]["Deal Won"], 12)
        self.assertEqual(table["remark_values"], ["Trial"])
        page = BeautifulSoup(out.read_text(encoding="utf-8"), "html.parser").get_text(" ")
        self.assertIn("Masa berlaku lead dihitung dari Inbound Date. Umum: MQL 12 bulan, SQL 12 bulan, Deal Won 12 bulan. Remark Trial: MQL tanpa batas, SQL tanpa batas, Deal Won tanpa batas.", page)
        self.assertIn("Lead yang expired dikeluarkan dari angka tahap itu: MQL 1, SQL 1, Deal Won 1.", page)
        facts = json.loads(out.with_suffix(".facts.json").read_text())
        self.assertEqual(facts["data_quality"]["expired"], {"MQL": 1, "SQL": 1, "Deal Won": 1})
        self.assertNotIn("remark_values", facts["data_quality"])
        self.assertNotIn("validity", facts["data_quality"])

    def test_no_note_when_no_limit_is_in_force(self):
        path = self.root / "t.csv"
        write_table(path, [lead("1", "BU2", "Ecosystem", "9/22/2026", mql="9/23/2026", sql_date="9/25/2026", contract="Rp 5.000.000")])
        out = self.root / "o.html"
        self.assertEqual(run("--table", path, "--bu", "bu2", "--period", "2026-W39", "--output", out).returncode, 0)
        self.assertNotIn("Masa berlaku lead", out.read_text(encoding="utf-8"))
        self.assertEqual(report.validity_note({"expired": {}, "validity": settings()}), "Masa berlaku lead dihitung dari Inbound Date. Umum: MQL tanpa batas, SQL tanpa batas, Deal Won tanpa batas. Lead yang expired dikeluarkan dari angka tahap itu: MQL 0, SQL 0, Deal Won 0.")
        self.assertEqual(report.validity_note(None), "")

    def test_a_bad_settings_file_stops_the_run_with_a_reason(self):
        path = self.root / "t.csv"
        write_table(path, [lead("1", "BU1", "GPS", "9/21/2026", mql="9/22/2026")])
        config = self.root / "v.json"
        config.write_text(json.dumps({"defaults": {"MQL": 0, "SQL": None, "Deal Won": None}}))
        result = run("--table", path, "--bu", "bu1", "--period", "2026-W39", "--output", self.root / "o.html", "--validity", config)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("batas MQL", result.stderr)


if __name__ == "__main__":
    unittest.main()
