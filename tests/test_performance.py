import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import performa  # noqa: E402
import report_view  # noqa: E402
from test_cohort_toggle import LEADS as COHORT_LEADS, build as build_report  # noqa: E402
from test_table_mode import run, write_table  # noqa: E402
from test_viewer import UTC, ViewerCase  # noqa: E402
from test_viewer_users import USER_PASSWORD  # noqa: E402
from viewer import auth, performance  # noqa: E402

AS_OF = date(2026, 10, 21)


def generated(bu, as_of="2026-10-21", leads=COHORT_LEADS):
    with tempfile.TemporaryDirectory() as tmp:
        table, out = Path(tmp) / "t.csv", Path(tmp) / "p.json"
        write_table(table, leads)
        proc = subprocess.run([sys.executable, str(ROOT / "generate_report.py"), "--table", str(table), "--bu", bu, "--performa-json", str(out), "--as-of", as_of], capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr
        return json.loads(out.read_text())


def snapshot(bu="bu1"):
    data = generated(bu)
    data.pop("audit")
    return {"snapshot_id": "p1", "generated_at": datetime(2026, 10, 21, 8, 0, tzinfo=UTC), "as_of": AS_OF, "data": data}


class CohortMathTests(unittest.TestCase):
    LEADS = [(date(2026, 9, 21), date(2026, 9, 22), date(2026, 9, 23)),   # same week MQL and SQL
             (date(2026, 9, 22), date(2026, 9, 30), None),                # MQL a week later, never SQL
             (date(2026, 9, 23), None, None),                             # never moved
             (date(2026, 9, 29), date(2026, 9, 29), date(2026, 10, 15))]  # next week's cohort

    def test_week_cohort_counts_are_cumulative_and_stop_where_the_period_has_not_ended(self):
        rows = {r[0]: r for r in performa.cohorts(self.LEADS, AS_OF, "week")}
        first = rows["2026-09-21"]
        self.assertEqual(first[1:4], [3, 2, 4])  # size 3, two have an MQL date, columns 0 to 3 have finished (the fifth ends 25 Oct)
        self.assertEqual(first[4], [1, 2, 2, 2, 2])  # MQL by the end of each column
        self.assertEqual(first[5], [1, 1, 1, 1, 1])  # SQL
        self.assertEqual(first[6], [1, 1, 1, 1, 1])  # SQL among leads that have an MQL date
        second = rows["2026-09-28"]
        self.assertEqual((second[1], second[2], second[3]), (1, 1, 3))
        self.assertEqual(second[5], [0, 0, 1, 1, 1])  # the SQL on 15 Oct falls in the third column (+2 weeks)
        current = performa.cohorts([(date(2026, 10, 20), None, None)], AS_OF, "week")[0]
        self.assertEqual(current[3], 0)  # this week is not over, nothing is rated

    def test_day_and_month_periods_and_year_wrap(self):
        self.assertEqual(performa.period_start(date(2026, 9, 24), "week"), date(2026, 9, 21))
        self.assertEqual(performa.period_end(date(2028, 2, 1), "month"), date(2028, 2, 29))
        self.assertEqual(performa.shift(date(2026, 11, 1), "month", 3), date(2027, 2, 1))
        self.assertEqual(performa.shift(date(2026, 12, 29), "week", 1), date(2027, 1, 5))
        months = {r[0]: r for r in performa.cohorts(self.LEADS, AS_OF, "month")}
        self.assertEqual(months["2026-09-01"][1], 4)
        self.assertEqual(months["2026-09-01"][3], 1)  # only September itself has ended by 21 Oct
        days = performa.cohorts(self.LEADS, AS_OF, "day")
        self.assertEqual(len(days), 4)
        self.assertEqual(days[0][3], 5)

    def test_an_sql_without_mql_date_is_not_counted_in_mql_to_sql(self):
        row = performa.cohorts([(date(2026, 9, 21), None, date(2026, 9, 22))], AS_OF, "week")[0]
        self.assertEqual((row[2], row[5][0], row[6][0]), (0, 1, 0))  # counts for Submission to SQL, not for MQL to SQL


class GeneratorTests(unittest.TestCase):
    def test_daily_numbers_agree_with_the_weekly_report(self):
        for bu in ("bu1", "bu2"):
            _, _, view = build_report(bu)
            data = generated(bu)
            week = [(d, e) for d, e in data["days"].items() if "2026-09-21" <= d <= "2026-09-27"]
            total = lambda key: sum(Decimal(str(e.get(key, 0))) for _, e in week)
            self.assertEqual((int(total("sub")), int(total("mql")), int(total("sql")), int(total("sqlv"))),
                             (view["metrics"]["Submission"], view["metrics"]["MQL"], view["metrics"]["SQL"], view["metrics"]["SQL Value"]), bu)
            self.assertEqual((int(total("won")), int(total("wonv"))), (view["metrics"]["Deal Won"], view["metrics"]["Deal Won Value"]), bu)

    def test_output_is_aggregates_only_and_money_survives_as_exact_text(self):
        data = generated("bu2")
        text = json.dumps(data)
        for name in ("Co1", "Co5", "Camp A", "Mfg", "Google Ads"):
            self.assertNotIn(name, text)
        self.assertEqual(data["v"], 1)
        self.assertTrue(all(isinstance(e.get("sqlv", "0"), str) for e in data["days"].values()))
        self.assertEqual(data["audit"]["rows_in_bu"], 4)

    def test_performa_mode_needs_a_table_and_no_period(self):
        proc = run("--bu", "bu1", "--performa-json", "/tmp/never.json")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("--table", proc.stderr)
        self.assertNotEqual(run("--bu", "bu1").returncode, 0)  # a normal run still demands a period


def points_for(snap, **query):
    params = performance.parse_params(query, AS_OF)
    return params, performance.series(snap, params)


class SeriesTests(unittest.TestCase):
    def setUp(self):
        self.snap = snapshot("bu1")

    def test_week_buckets_clip_to_the_range_and_label_by_iso_week(self):
        params, points = points_for(self.snap, per="minggu", **{"from": "2026-09-23", "to": "2026-10-02"})
        self.assertEqual([(p["label"], p["lo"], p["hi"]) for p in points], [("W39", date(2026, 9, 23), date(2026, 9, 27)), ("W40", date(2026, 9, 28), date(2026, 10, 2))])
        self.assertEqual(points[0]["sql"], Decimal(1))  # 23 Sep and 22 Sep SQLs: only the one inside the range is counted
        self.assertEqual(points[0]["mql"], Decimal(1))
        self.assertEqual(performance.summary(points)["sqlv"], Decimal(1000000))

    def test_day_and_month_grouping_with_zero_filled_gaps(self):
        _, days = points_for(self.snap, per="hari", **{"from": "2026-09-20", "to": "2026-09-24"})
        self.assertEqual([(p["label"], int(p["sub"])) for p in days], [("20 Sep", 0), ("21 Sep", 1), ("22 Sep", 1), ("23 Sep", 0), ("24 Sep", 0)])  # Submission follows the Inbound Date
        _, months = points_for(self.snap, per="bulan", **{"from": "2026-08-15", "to": "2026-10-20"})
        self.assertEqual([p["label"] for p in months], ["Agu 2026", "Sep 2026", "Okt 2026"])
        self.assertEqual(int(months[1]["sub"]), 4)  # inbound on 1, 10, 21 and 22 Sep
        self.assertFalse(performance.has_activity([months[0], months[2]]))

    def test_summary_rates_follow_the_report_definitions(self):
        _, points = points_for(self.snap, per="bulan", **{"from": "2026-09-01", "to": "2026-09-30"})
        total = performance.summary(points)
        self.assertEqual(total["mql_rate"], float(total["mql"] * 100 / total["sub"]))
        self.assertEqual(total["sql_rate"], float(total["sql"] * 100 / total["mql"]))
        self.assertEqual(total["won_rate"], 0.0)  # SQLs exist and none was won: a real zero
        _, quiet = points_for(self.snap, per="bulan", **{"from": "2026-08-01", "to": "2026-08-31"})
        self.assertEqual((performance.summary(quiet)["mql_rate"], performance.summary(quiet)["won_rate"]), (None, None))  # no denominator means no rate, not zero

    def test_cohort_rows_choose_periods_starting_in_the_range_and_rate_only_finished_columns(self):
        params, _ = points_for(self.snap, per="minggu", **{"from": "2026-09-21", "to": "2026-10-19"})
        rows = performance.cohort_rows(self.snap, params)
        self.assertEqual(rows[0]["label"], "W39 (21–27 Sep)")
        self.assertEqual(len(rows[0]["cells"]), 5)
        self.assertTrue(all(c is None or 0 <= c <= 100 for r in rows for c in r["cells"]))
        recent = performance.cohort_rows(self.snap, performance.parse_params({"per": "minggu", "from": "2026-10-19", "to": "2026-10-21"}, AS_OF))
        self.assertEqual(recent, [])  # no submission that week, so no cohort
        sq = performance.cohort_rows(self.snap, performance.parse_params({"per": "minggu", "from": "2026-09-21", "to": "2026-09-27", "metrik": "sql_mql"}, AS_OF))
        self.assertEqual(sq[0]["base"], 2)  # the two leads of that week's cohort that have an MQL date

    def test_parameters_have_defaults_and_refuse_nonsense(self):
        p = performance.parse_params({}, AS_OF)
        self.assertEqual((p.per, p.end, p.metrik, p.error), ("minggu", AS_OF, "mql", ""))
        self.assertEqual(p.start, date(2026, 8, 3))  # twelve ISO weeks ending with this one
        self.assertEqual(performance.parse_params({"per": "hari"}, AS_OF).start, date(2026, 10, 8))
        self.assertEqual(performance.parse_params({"per": "bulan"}, AS_OF).start, date(2026, 5, 1))
        self.assertEqual(performance.parse_params({"per": "x", "from": "kacau", "metrik": "x"}, AS_OF).per, "minggu")
        self.assertEqual(performance.parse_params({"from": "2026-10-02", "to": "2026-10-01"}, AS_OF).error, performance.ERR_ORDER)
        self.assertEqual(performance.parse_params({"per": "hari", "from": "2026-01-01", "to": "2026-10-01"}, AS_OF).error, performance.ERR_DAYS)
        self.assertEqual(performance.parse_params({"per": "minggu", "from": "2026-01-01", "to": "2026-10-01"}, AS_OF).error, "")

    def test_chart_axis_uses_round_numbers(self):
        for value, top in ((0, 4), (3, 4), (5, 8), (17, 20), (101, 200), (2500000, 4000000)):
            self.assertEqual(performance.nice_max(Decimal(value)), Decimal(top))
        self.assertEqual((performance.compact(Decimal(1500000)), performance.compact(Decimal(250000)), performance.compact(Decimal(7))), ("1,5 jt", "250 rb", "7"))


class PerformaPageTests(ViewerCase):
    def setUp(self):
        super().setUp()
        self.store.performance["bu1"] = snapshot("bu1")
        self.login()

    def soup(self, query="", status=200):
        response, body = self.call("GET", "/performa" + query)
        self.assertEqual(response.status, status, query)
        return BeautifulSoup(body, "html.parser")

    def test_the_page_has_both_charts_the_summary_and_the_cohort_like_the_mockup(self):
        soup = self.soup("?bu=bu1&per=minggu&from=2026-09-14&to=2026-10-04")
        self.assertEqual(soup.select_one("h1").get_text(), "Performa")
        self.assertEqual([h.get_text() for h in soup.select("main h2")], ["Volume per minggu", "Nilai per minggu", "Ringkasan rentang", "Cohort konversi", "Matriks cohort"])
        charts = soup.select("svg.pf-chart")
        self.assertEqual(len(charts), 2)
        self.assertIn("Submission, MQL, SQL, dan Deal Won", charts[0]["aria-label"])
        self.assertEqual(len(charts[0].select("polyline")), 4)
        self.assertEqual(len(charts[1].select("polyline")), 2)
        self.assertEqual(len(charts[0].select("title")), 4 * 3)  # four series, three weeks, a tooltip per point
        self.assertEqual([td.get_text() for td in soup.select("section[aria-label='Ringkasan periode'] tbody td:first-child")],
                         ["Submission", "MQL", "SQL", "SQL Value", "Deal Won", "Deal Won Value"])
        rates = [td.get_text() for td in soup.select("section[aria-label='Ringkasan periode'] tbody td:nth-child(3)")]
        self.assertTrue(rates[1].startswith("MQL Rate") and rates[2].startswith("SQL Rate") and rates[4].startswith("Deal Won Rate"))
        self.assertEqual([th.get_text() for th in soup.select("section[aria-label='Cohort'] thead th")],
                         ["Cohort submission", "Submission", "Periode yang sama", "+1 minggu", "+2 minggu", "+3 minggu", "+4 minggu"])
        self.assertEqual([o["value"] for o in soup.select("#metrik option")], ["mql", "sql_mql", "sql"])
        self.assertEqual(len(soup.select("details table")), 2)  # the numbers behind each chart, for those who cannot read a chart

    def test_the_numbers_on_the_page_are_the_snapshots_numbers(self):
        soup = self.soup("?bu=bu1&per=bulan&from=2026-09-01&to=2026-09-30")
        rows = {tr.select("td")[0].get_text(): tr.select("td")[1].get_text() for tr in soup.select("section[aria-label='Ringkasan periode'] tbody tr")}
        days = self.store.performance["bu1"]["data"]["days"]
        self.assertEqual(rows["Submission"], str(sum(e.get("sub", 0) for d, e in days.items() if d.startswith("2026-09"))))
        self.assertEqual(rows["SQL Value"], "Rp " + f"{sum(int(e.get('sqlv', 0)) for d, e in days.items() if d.startswith('2026-09')):,}".replace(",", "."))

    def test_per_buttons_are_links_that_keep_the_company_and_metric(self):
        soup = self.soup("?bu=bu1&per=hari&metrik=sql&from=2026-09-20&to=2026-09-25")
        seg = soup.select(".pf-seg a")
        self.assertEqual([a.get_text() for a in seg], ["Hari", "Minggu", "Bulan"])
        self.assertEqual([a.get("aria-current") for a in seg], ["true", None, None])
        self.assertIn("per=bulan", seg[2]["href"])
        self.assertIn("metrik=sql", seg[2]["href"])
        self.assertIn("bu=bu1", seg[2]["href"])
        self.assertEqual(soup.select_one("#metrik option[selected]")["value"], "sql")
        self.assertEqual([th.get_text() for th in soup.select("section[aria-label='Cohort'] thead th")][1], "Submission")
        self.assertEqual([th.get_text() for th in self.soup("?bu=bu1&metrik=sql_mql").select("section[aria-label='Cohort'] thead th")][1], "MQL")

    def test_cohort_cells_show_dash_for_unfinished_periods_and_a_tint_for_rated_ones(self):
        soup = self.soup("?bu=bu1&per=minggu&from=2026-09-14&to=2026-10-12")
        cells = [td for td in soup.select("section[aria-label='Cohort'] tbody td.num")]
        self.assertTrue(any(td.get_text() == "-" for td in cells))
        rated = [td for td in cells if td.get_text().endswith("%")]
        self.assertTrue(rated and all("rgba(33,89,169" in td.get("style", "") for td in rated))
        self.assertTrue(all("style" not in td.attrs for td in cells if td.get_text() == "-"))

    def test_bad_ranges_explain_themselves_and_draw_no_charts(self):
        for query, text in (("?from=2026-10-02&to=2026-10-01", performance.ERR_ORDER), ("?per=hari&from=2026-01-01&to=2026-10-01", performance.ERR_DAYS)):
            soup = self.soup(query)
            self.assertIn(text, soup.select_one("[role=alert]").get_text())
            self.assertEqual(soup.select("svg.pf-chart"), [])
        self.assertIsNotNone(self.soup("?from=2026-10-02&to=2026-10-01").select_one("#dari[aria-invalid=true]"))

    def test_an_empty_range_a_missing_snapshot_and_a_database_failure_each_have_their_own_message(self):
        self.assertIn("Tidak ada data pada rentang ini", self.soup("?from=2020-01-01&to=2020-02-01").get_text())
        belum = self.soup("?bu=bu2")
        self.assertIn("Belum ada data performa untuk Perusahaan 2", belum.get_text())
        self.assertIn("Jalankan workflow Performa Generate di n8n", belum.get_text())
        self.store.latest_performance = lambda bu: (_ for _ in ()).throw(RuntimeError("no such table"))
        failed = self.soup("", 503)
        self.assertIn("Data performa tidak bisa dimuat", failed.get_text())
        self.assertEqual(failed.select_one("section[aria-label='Pengaturan tampilan']") is not None, True)

    def test_a_company_picker_for_admins_and_a_fixed_name_for_single_company_users(self):
        soup = self.soup()
        self.assertEqual([o.get_text() for o in soup.select("#bu option")], ["Perusahaan 1", "Perusahaan 2"])
        self.store.names = {"bu1": "McEasy", "bu2": "LOL"}
        self.assertEqual([o.get_text() for o in self.soup().select("#bu option")], ["McEasy", "LOL"])
        self.store.create_user("andi", auth.hash_password(USER_PASSWORD), "user", False, ["bu1"], True)
        self.login(USER_PASSWORD, username="andi")
        user = self.soup()
        self.assertEqual(user.select("#bu"), [])
        self.assertIn("McEasy", user.select_one("section[aria-label='Pengaturan tampilan']").get_text())
        self.assertEqual(self.call("GET", "/performa?bu=bu2")[0].status, 403)
        self.assertEqual(self.call("GET", "/performa?bu=bu9")[0].status, 404)
        self.store.create_user("semua", auth.hash_password(USER_PASSWORD), "user", True, [], True)
        self.login(USER_PASSWORD, username="semua")
        self.assertIn("Hubungi admin untuk menjalankannya.", self.soup("?bu=bu2").get_text())
        self.assertNotIn("Jalankan workflow Performa Generate di n8n, lalu", self.soup("?bu=bu2").get_text())
        self.assertEqual([a["href"] for a in user.select(".vw-menu a")], ["/performa"])  # everyone sees Performa, only admins see the rest

    def test_the_page_needs_a_session_and_never_shows_company_names_from_the_sheet(self):
        self.cookie = ""
        response, _ = self.call("GET", "/performa", cookie=False)
        self.assertEqual((response.status, response.getheader("Location")), (303, "/login"))
        self.login()
        _, body = self.call("GET", "/performa?bu=bu1&per=bulan")
        for name in ("Co1", "Co2", "Camp A"):
            self.assertNotIn(name, body)


class MatrixTests(unittest.TestCase):
    def test_counts_pair_the_row_date_with_the_column_date_per_period(self):
        events = [(date(2026, 9, 23), date(2026, 9, 21)), (date(2026, 9, 22), date(2026, 9, 1)), (date(2026, 9, 24), date(2026, 9, 22)), (date(2026, 10, 2), date(2026, 9, 22))]
        self.assertEqual(performa.matrix_counts(events, "week"), [["2026-09-21", "2026-08-31", 1], ["2026-09-21", "2026-09-21", 2], ["2026-09-28", "2026-09-21", 1]])
        self.assertEqual(performa.matrix_counts(events, "month"), [["2026-09-01", "2026-09-01", 3], ["2026-10-01", "2026-09-01", 1]])
        self.assertEqual(performa.matrix_counts([], "week"), [])

    def test_generator_output_matches_the_leads(self):
        data = generated("bu1")["matrices"]
        self.assertEqual(sorted(data), ["month", "week"])  # no per-day matrix
        week = data["week"]
        self.assertEqual(week["sub_sql"], [["2026-09-21", "2026-08-31", 1], ["2026-09-21", "2026-09-21", 1]])  # lead 2 came in on 1 Sep, lead 1 on 21 Sep
        self.assertEqual(week["mql_sql"], [["2026-09-21", "2026-08-31", 1], ["2026-09-21", "2026-09-21", 1]])
        self.assertEqual(week["sub_mql"], [["2026-08-31", "2026-08-31", 1], ["2026-09-21", "2026-09-07", 1], ["2026-09-21", "2026-09-21", 2]])
        for pair, stage_key in (("sub_sql", "sql"), ("sub_mql", "mql")):  # every row total equals that period's stage count in the daily series
            days = generated("bu1")["days"]
            by_row = {}
            for row, _, n in week[pair]:
                by_row[row] = by_row.get(row, 0) + n
            weekly = {}
            for text, entry in days.items():
                d = date.fromisoformat(text)
                monday = (d - timedelta(days=d.weekday())).isoformat()
                weekly[monday] = weekly.get(monday, 0) + entry.get(stage_key, 0)
            self.assertEqual(by_row, {k: v for k, v in weekly.items() if v}, pair)

    def params(self, **query):
        return performance.parse_params({"per": "minggu", **query}, AS_OF)

    def test_rows_are_the_periods_starting_in_the_range_newest_first(self):
        m = performance.matrix(snapshot("bu1"), self.params(**{"from": "2026-10-05", "to": "2026-10-20"}))
        self.assertEqual([r["label"] for r in m["rows"]], ["2026-W43", "2026-W42", "2026-W41"])
        self.assertEqual(m["columns"][:3], ["2026-W43", "2026-W42", "2026-W41"])
        self.assertEqual(len(m["columns"]), 10)
        mid = performance.matrix(snapshot("bu1"), self.params(**{"from": "2026-10-07", "to": "2026-10-20"}))
        self.assertEqual([r["label"] for r in mid["rows"]], ["2026-W43", "2026-W42"])  # W41 started before the range

    def test_a_row_period_folds_columns_beyond_the_tenth_into_older_and_totals_everything(self):
        snap = snapshot("bu1")
        snap["data"]["matrices"]["week"]["sub_sql"] = [["2026-10-12", "2026-10-12", 4], ["2026-10-12", "2026-10-05", 7], ["2026-10-12", "2026-07-06", 3], ["2026-10-12", "2026-01-05", 2]]
        m = performance.matrix(snap, self.params(**{"from": "2026-10-12", "to": "2026-10-18"}))
        row = m["rows"][0]
        self.assertEqual([c["n"] for c in row["cells"]][:3], [4, 7, 0])
        self.assertEqual((row["older"], row["total"]), (5, 16))  # 3 + 2 fall left of the tenth column
        self.assertEqual(sum(c["n"] for c in row["cells"]) + row["older"], row["total"])
        self.assertEqual([c["bg"] for c in row["cells"]][:3], ["#a8cf5f", "#5fbf84", "transparent"])  # 4 is olive, 7 is green, 0 has no colour

    def test_heat_scale_boundaries_and_month_and_row_cap(self):
        self.assertEqual([performance.heat(n) for n in (0, 1, 2, 3, 4, 5, 6, 40)], ["transparent", "#ec8359", "#f2a54a", "#f6cf57", "#a8cf5f", "#a8cf5f", "#5fbf84", "#5fbf84"])
        snap = snapshot("bu1")
        month = performance.matrix(snap, self.params(per="bulan", **{"from": "2026-08-01", "to": "2026-10-31"}))
        self.assertEqual([r["label"] for r in month["rows"]], ["Okt 2026", "Sep 2026", "Agu 2026"])
        self.assertEqual(month["columns"][0], "Okt 2026")
        long = performance.matrix(snap, self.params(**{"from": "2024-01-01", "to": "2026-10-20"}))
        self.assertEqual((len(long["rows"]), long["truncated"]), (performance.MATRIX_MAX_ROWS, True))
        self.assertEqual(long["rows"][0]["label"], "2026-W43")

    def test_per_day_has_no_matrix_and_an_old_snapshot_says_so(self):
        snap = snapshot("bu1")
        self.assertIsNone(performance.matrix(snap, self.params(per="hari", **{"from": "2026-10-01", "to": "2026-10-10"})))
        del snap["data"]["matrices"]
        self.assertEqual(performance.matrix(snap, self.params()), {"missing": True})

    def test_the_first_row_of_the_page_matrix_for_the_real_data(self):
        snap = snapshot("bu1")
        m = performance.matrix(snap, self.params(**{"from": "2026-09-21", "to": "2026-09-27"}))
        row = m["rows"][0]
        self.assertEqual(row["label"], "2026-W39")
        self.assertEqual(row["total"], 2)
        self.assertEqual(row["older"] + sum(c["n"] for c in row["cells"]), 2)


class MatrixPageTests(ViewerCase):
    def setUp(self):
        super().setUp()
        self.store.performance["bu1"] = snapshot("bu1")
        self.login()

    def section(self, query=""):
        response, body = self.call("GET", "/performa" + query)
        self.assertEqual(response.status, 200)
        soup = BeautifulSoup(body, "html.parser")
        return soup, soup.select_one("section[aria-label='Matriks cohort']")

    def test_the_matrix_has_the_mockup_header_ten_columns_older_and_a_total_column_at_the_far_right(self):
        _, section = self.section("?bu=bu1&per=minggu&from=2026-09-14&to=2026-10-04")
        self.assertEqual(section.select_one("h2").get_text(), "Matriks cohort")
        self.assertEqual([o["value"] for o in section.select("#matriks option")], ["sub_sql", "mql_sql", "sub_mql"])
        self.assertEqual(section.select_one("thead tr th[colspan]").get_text(), "Minggu submission")
        heads = [th.get_text() for th in section.select("thead tr:nth-child(2) th")]
        self.assertEqual(len(heads), 12)
        self.assertEqual(heads[-2:], ["Lebih lama", "Total baris"])
        self.assertEqual(heads[0], "2026-W40")  # the range ends in W40, the newest column is on the left
        self.assertEqual(section.select_one("thead th[rowspan]").get_text(), "Minggu SQL")
        rows = section.select("tbody tr")
        self.assertEqual([r.select_one("th").get_text() for r in rows], ["2026-W40", "2026-W39", "2026-W38"])
        for row in rows:
            cells = row.select("td")
            self.assertEqual(len(cells), 12)
            numbers = [int(c.get_text() or 0) for c in cells[:10]]
            older = int(cells[10].get_text() or 0)
            self.assertEqual(sum(numbers) + older, int(cells[11].get_text()))  # the far right is the row total
        w39 = rows[1].select("td")
        self.assertEqual(int(w39[11].get_text()), 2)
        shaded = [c for c in w39[:10] if c.get_text()]
        self.assertTrue(shaded and all("background:#ec8359" in c["style"] for c in shaded))  # one lead each: the 1-lead colour
        self.assertEqual(len(section.select(".pf-legend span")) >= 5, True)

    def test_the_choice_changes_the_labels_and_is_kept_by_the_per_links(self):
        soup, section = self.section("?bu=bu1&per=bulan&from=2026-08-01&to=2026-10-31&matriks=mql_sql")
        self.assertEqual(section.select_one("thead tr th[colspan]").get_text(), "Bulan MQL")
        self.assertEqual(section.select_one("thead th[rowspan]").get_text(), "Bulan SQL")
        self.assertEqual(section.select_one("#matriks option[selected]")["value"], "mql_sql")
        self.assertIn("matriks=mql_sql", soup.select(".pf-seg a")[0]["href"])
        _, mql = self.section("?bu=bu1&per=minggu&from=2026-09-14&to=2026-10-04&matriks=sub_mql")
        self.assertEqual(mql.select_one("thead th[rowspan]").get_text(), "Minggu MQL")
        self.assertEqual(self.section("?matriks=bogus")[1].select_one("#matriks option[selected]")["value"], "sub_sql")

    def test_per_day_and_an_old_snapshot_show_their_own_note(self):
        _, section = self.section("?bu=bu1&per=hari&from=2026-09-20&to=2026-09-27")
        self.assertIn("Matriks tersedia per Minggu atau Bulan", section.get_text())
        self.assertIsNone(section.select_one("table"))
        del self.store.performance["bu1"]["data"]["matrices"]
        _, old = self.section("?bu=bu1&per=minggu&from=2026-09-14&to=2026-10-04")
        self.assertIn("Matriks belum ada di data ini", old.get_text())
        self.assertIn("Performa Generate", old.get_text())

    def test_the_matrix_holds_only_counts_never_company_names(self):
        _, body = self.call("GET", "/performa?bu=bu1&per=minggu&from=2026-09-14&to=2026-10-04")
        for name in ("Co1", "Co2", "Camp A"):
            self.assertNotIn(name, body)


if __name__ == "__main__":
    unittest.main()
