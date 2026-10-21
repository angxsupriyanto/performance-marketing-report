"""The switch "Hanya yang submission-nya di <periode>": the same lists and tables, limited to leads whose Inbound Date is in the period."""
import sys
import tempfile
import unittest
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import report_view  # noqa: E402
from test_table_mode import lead, run, write_table  # noqa: E402

# Week 2026-W39 is 21 to 27 September. "Backlog" leads came in earlier but hit the stage this week.
LEADS = [
    lead("1", "BU1", "GPS", "9/21/2026", mql="9/22/2026", sql_date="9/23/2026", ppq="9/23/2026", arr="Rp 1.000.000"),       # same-week SQL
    lead("2", "BU1", "Dashcam", "9/1/2026", mql="9/2/2026", sql_date="9/22/2026", ppq="9/22/2026", arr="Rp 2.000.000"),     # backlog SQL
    lead("3", "BU1", "Fuel", "9/10/2026", mql="9/22/2026"),                                                                 # backlog MQL
    lead("4", "BU1", "Fuel", "9/22/2026", mql="9/23/2026"),                                                                 # same-week MQL
    lead("5", "BU2", "Ecosystem", "9/22/2026", mql="9/23/2026", sql_date="9/25/2026", contract="Rp 5.000.000"),            # same-week SQL
    lead("6", "BU2", "Ecosystem", "9/1/2026", mql="9/2/2026", sql_date="9/24/2026", contract="Rp 7.000.000"),               # backlog SQL
    lead("7", "BU2", "GPS", "9/23/2026", sql_date="9/24/2026", contract="Rp 100.000", won="9/27/2026", won_value="Rp 2.500.000"),  # same-week won
    lead("8", "BU2", "GPS", "9/2/2026", sql_date="9/10/2026", contract="Rp 100.000", won="9/26/2026", won_value="Rp 4.000.000"),  # backlog won
]


def build(bu, period="2026-W39"):
    with tempfile.TemporaryDirectory() as tmp:
        table, out = Path(tmp) / "t.csv", Path(tmp) / "r.html"
        write_table(table, LEADS)
        proc = run("--table", table, "--bu", bu, "--period", period, "--output", out)
        assert proc.returncode == 0, proc.stderr
        html = out.read_text()
    return html, BeautifulSoup(html, "html.parser"), report_view.extract_view(html)


def groups(soup):
    return soup.select("[data-cohort-group]")


def rows(table):
    return [[td.get_text() for td in tr.select("td")] for tr in table.select("tbody tr")]


class CohortToggleTests(unittest.TestCase):
    def test_view_marks_every_row_and_hardware_with_its_same_period_numbers(self):
        _, _, view = build("bu1")
        self.assertEqual([(r["company"], r["same"]) for r in view["sql_list"]["rows"]], [("Co2", False), ("Co1", True)])
        by_name = {h["name"]: h for h in view["hardware"]}
        self.assertEqual((by_name["GPS Tracker"]["same_sql"], by_name["GPS Tracker"]["same_value"]), (1, 1000000))
        self.assertEqual((by_name["Dashcam"]["sql"], by_name["Dashcam"]["same_sql"], by_name["Dashcam"]["same_value"], by_name["Dashcam"]["week"]), (1, 0, 0, 2000000))
        self.assertEqual((by_name["Fuel"]["mql"], by_name["Fuel"]["same_mql"]), (2, 1))
        _, _, bu2 = build("bu2")
        self.assertEqual([(r["company"], r["same"]) for r in bu2["won_list"]["rows"]], [("Co8", False), ("Co7", True)])

    def test_mcEasy_has_the_switch_on_sql_list_and_hardware_only(self):
        _, soup, _ = build("bu1")
        self.assertEqual(len(groups(soup)), 2)
        self.assertEqual([g.select_one("label").get_text() for g in groups(soup)], ["Hanya yang submission-nya di Week 39"] * 2)
        text = soup.get_text(" ")
        self.assertIn("Mati: semua SQL pada Week 39. Menyala: hanya SQL yang Inbound Date-nya juga di Week 39. Untuk report bulanan memakai bulan yang sama.", text)
        self.assertIn("Mati: semua MQL, SQL, dan SQL Value pada Week 39. Menyala: hanya lead yang Inbound Date-nya juga di Week 39.", text)
        self.assertIn("Kolom Target dan Progress tetap memakai semua SQL bulan berjalan.", text)
        self.assertEqual(soup.select_one("[data-cohort-note]").get("hidden"), "")

    def test_lol_has_the_switch_on_sql_list_and_deal_won_only(self):
        _, soup, _ = build("bu2")
        self.assertEqual(len(groups(soup)), 2)
        titles = [g.find_parent("div", style=True).select_one("h3").get_text() for g in groups(soup)]
        self.assertEqual(titles, ["Daftar SQL Week 39", "Daftar Deal Won Week 39"])
        self.assertEqual(soup.select("[data-cohort-note]"), [])
        self.assertIn("Mati: semua Deal Won pada Week 39. Menyala: hanya Deal Won yang Inbound Date-nya juga di Week 39.", soup.get_text(" "))

    def test_sql_list_same_view_keeps_only_backlog_free_rows_and_recomputes_the_total(self):
        _, soup, _ = build("bu1")
        group = groups(soup)[0]
        everything, same = group.select_one('[data-cohort-view="all"] table'), group.select_one('[data-cohort-view="same"] table')
        self.assertEqual([r[0] for r in rows(everything)], ["Co2", "Co1"])
        self.assertEqual([r[0] for r in rows(same)], ["Co1"])
        self.assertEqual([td.get_text() for td in same.select("tfoot td")][0], "TOTAL 1 SQL")
        self.assertEqual([td.get_text() for td in same.select("tfoot td")][1], "Rp 1.000.000")
        self.assertEqual([td.get_text() for td in everything.select("tfoot td")][1], "Rp 3.000.000")
        self.assertIn("Menampilkan 1 dari 2 SQL yang submission-nya di Week 39.", group.get_text(" "))
        self.assertEqual(group.select_one('[data-cohort-view="all"]').get("hidden"), None)  # off by default
        self.assertEqual(group.select_one('[data-cohort-view="same"]').get("hidden"), "")
        self.assertIsNone(group.select_one("[data-cohort-toggle]").get("checked"))

    def test_hardware_table_same_view_changes_mql_sql_and_value_but_not_submission_target_or_progress(self):
        _, soup, view = build("bu1")
        group = groups(soup)[1]
        everything, same = group.select_one('[data-cohort-view="all"] table'), group.select_one('[data-cohort-view="same"] table')
        by = lambda table: {r[0]: r for r in rows(table)}
        a, s = by(everything), by(same)
        self.assertEqual(a["Fuel"][1:4], ["1", "2", "0"])  # one submission this week, but two MQLs: one of them a backlog lead
        self.assertEqual(s["Fuel"][1:4], ["1", "1", "0"])  # submission stays, MQL counts only same-week leads
        self.assertEqual((a["Dashcam"][3:5], s["Dashcam"][3:5]), (["1", "Rp 2.000.000"], ["0", "Rp 0"]))
        self.assertEqual(a["GPS Tracker"][5:], s["GPS Tracker"][5:])  # Target and Progress identical
        foot = lambda table: [td.get_text() for td in table.select("tfoot td")]
        self.assertEqual(foot(everything)[4], "Rp 3.000.000")
        self.assertEqual(foot(same)[4], "Rp 1.000.000")
        self.assertEqual(foot(same)[1], foot(everything)[1])
        self.assertEqual(foot(same)[5:], foot(everything)[5:])

    def test_deal_won_same_view(self):
        _, soup, _ = build("bu2")
        group = groups(soup)[1]
        same = group.select_one('[data-cohort-view="same"] table')
        self.assertEqual([r[0] for r in rows(same)], ["Co7"])
        self.assertEqual([td.get_text() for td in same.select("tfoot td")], ["TOTAL 1 DEAL WON", "Rp 2.500.000", ""])
        self.assertIn("Menampilkan 1 dari 2 Deal Won yang submission-nya di Week 39.", group.get_text(" "))

    def test_an_empty_same_view_says_so_and_a_monthly_report_names_the_month(self):
        _, soup, _ = build("bu1", "2026-09")
        self.assertEqual(groups(soup)[0].select_one("label").get_text(), "Hanya yang submission-nya di Sep 2026")
        _, only_old, _ = build("bu1")
        view = report_view.extract_view(build("bu1")[0])
        for r in view["sql_list"]["rows"]:
            r["same"] = False
        html = report_view.render_document(view)
        empty = BeautifulSoup(html, "html.parser").select_one('[data-cohort-view="same"]')
        self.assertIn("Tidak ada SQL di Week 39.", empty.get_text())
        self.assertIn("Menampilkan 0 dari 2 SQL", empty.get_text())

    def test_reports_stored_before_the_switch_render_without_it(self):
        _, _, view = build("bu1")
        for r in view["sql_list"]["rows"]:
            del r["same"]
        for h in view["hardware"]:
            for k in ("same_mql", "same_sql", "same_value"):
                del h[k]
        soup = BeautifulSoup(report_view.render_document(view), "html.parser")
        self.assertEqual(groups(soup), [])
        self.assertEqual(len(soup.select("table")), 2)

    def test_target_cards_and_progress_do_not_depend_on_the_switch(self):
        html, soup, view = build("bu1")
        tg = {"error": False, "semester": 12000000, "year": 20000000, "hardware": {"GPS Tracker": 4000000}}
        with_tg = BeautifulSoup(report_view.render_document(view, tg), "html.parser")
        progress = with_tg.select_one('section[aria-label^="Progress target"]')
        self.assertIsNone(progress.find_parent(attrs={"data-cohort-group": True}))
        self.assertIn("Tercapai", progress.get_text())
        for group in groups(with_tg)[1:]:
            panel = group.find(string=lambda t: "Target SQL Value" in t)
            self.assertIsNotNone(panel)  # the target panel is inside the hardware group but outside both table views
            self.assertIsNone(panel.find_parent(attrs={"data-cohort-view": True}))
        self.assertEqual(len(soup.select("[data-cohort-view]")), 4)


if __name__ == "__main__":
    unittest.main()
