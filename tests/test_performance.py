import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlencode

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import performa  # noqa: E402
from test_cohort_toggle import LEADS as COHORT_LEADS, build as build_report  # noqa: E402
from test_table_mode import HEADERS, lead, run, write_table  # noqa: E402
from test_viewer import UTC, ViewerCase  # noqa: E402
from test_viewer_users import USER_PASSWORD  # noqa: E402
from viewer import auth, performance  # noqa: E402

AS_OF = date(2026, 10, 21)
DIM_HEADERS = HEADERS + ["Medium", "Category Campaign"]


def with_dims(row, channel, source, medium, campaign, category, hardware):
    return {**row, "Channel": channel, "Source": source, "Medium": medium, "Campaign": campaign, "Category Campaign": category, "Campaign Hardware": hardware}


# Week 2026-W39 is 21 to 27 September. Four BU1 leads that differ in every filter.
DIM_LEADS = [
    with_dims(lead("1", "BU1", "GPS", "9/21/2026", mql="9/22/2026", sql_date="9/23/2026", ppq="9/23/2026", arr="Rp 1.000.000"), "Paid", "Google Ads", "cpc", "Camp A", "Brand", "GPS"),
    with_dims(lead("2", "BU1", "Dashcam", "9/1/2026", mql="9/2/2026", sql_date="9/22/2026", ppq="9/22/2026", arr="Rp 2.000.000"), "Paid", "Meta Ads", "cpc", "Camp B", "Promo", "Dashcam"),
    with_dims(lead("3", "BU1", "Fuel", "9/10/2026", mql="9/22/2026"), "Organic", "SEO", "organic", "Camp A", "Brand", "Fuel"),
    with_dims(lead("4", "BU1", "Fuel", "9/22/2026", mql="9/23/2026"), "Organic", "Instagram", "social", "", "", "Fuel"),
]


def generated(bu="bu1", as_of="2026-10-21", leads=DIM_LEADS, headers=DIM_HEADERS):
    with tempfile.TemporaryDirectory() as tmp:
        table, out = Path(tmp) / "t.csv", Path(tmp) / "p.json"
        write_table(table, leads, headers)
        proc = subprocess.run([sys.executable, str(ROOT / "generate_report.py"), "--table", str(table), "--bu", bu, "--performa-json", str(out), "--as-of", as_of], capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr
        return json.loads(out.read_text())


def snapshot(bu="bu1", **kw):
    data = generated(bu, **kw)
    data.pop("audit")
    return {"snapshot_id": "p1", "generated_at": datetime(2026, 10, 21, 8, 0, tzinfo=UTC), "as_of": AS_OF, "data": data}


def load(**kw):
    return performance.load(snapshot(**kw))


def params(data=None, lists=None, **query):
    return performance.parse_params({"per": "minggu", **query}, AS_OF, lists or {})


class GeneratorTests(unittest.TestCase):
    def test_one_anonymous_row_per_lead_with_dates_values_and_filter_positions(self):
        data = generated()
        self.assertEqual((data["v"], data["as_of"], len(data["leads"])), (2, "2026-10-21", 4))
        self.assertEqual(data["dims"], {"channel": ["Organic", "Paid"], "source": ["Google Ads", "Instagram", "Meta Ads", "SEO"], "medium": ["cpc", "organic", "social"],
                                        "campaign": ["Camp A", "Camp B", ""], "category": ["Brand", "Promo", ""], "hardware": ["Dashcam", "Fuel", "GPS Tracker"]})  # an empty value sorts last
        first = data["leads"][0]  # sorted by inbound day: lead 2, inbound 1 Sep
        self.assertEqual(first[:4], [date(2026, 9, 1).toordinal(), date(2026, 9, 2).toordinal(), date(2026, 9, 22).toordinal(), 0])
        self.assertEqual(first[4:6], [2000000, 0])
        self.assertEqual([data["dims"][k][i] for k, i in zip(("channel", "source", "medium", "campaign", "category", "hardware"), first[6:])], ["Paid", "Meta Ads", "cpc", "Camp B", "Promo", "Dashcam"])
        self.assertEqual(len(data["leads"][-1]), 12)

    def test_nothing_that_identifies_a_lead_is_written(self):
        text = json.dumps(generated())
        for name in ("Co1", "Co2", "Co3", "Co4", "Mfg", '"1"'):
            self.assertNotIn(name, text)

    def test_a_lead_in_several_stages_is_one_row_and_gps_is_the_reports_gps_tracker(self):
        data = generated()
        self.assertEqual(len(data["leads"]), 4)  # lead 1 is in the Submission, MQL and SQL lists but is counted once
        self.assertIn("GPS Tracker", data["dims"]["hardware"])
        self.assertNotIn("GPS", data["dims"]["hardware"])

    def test_missing_filter_columns_give_empty_values_instead_of_failing(self):
        data = generated(leads=COHORT_LEADS[:4], headers=HEADERS)  # a sheet export without Medium and Category Campaign
        self.assertEqual((data["dims"]["medium"], data["dims"]["category"]), ([""], [""]))

    def test_performa_mode_needs_a_table_and_no_period(self):
        proc = run("--bu", "bu1", "--performa-json", "/tmp/never.json")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("--table", proc.stderr)
        self.assertNotEqual(run("--bu", "bu1").returncode, 0)  # a normal run still demands a period

    def test_decimals_survive_exactly(self):
        row = with_dims(lead("9", "BU2", "GPS", "9/21/2026", mql="9/22/2026", sql_date="9/23/2026", contract="Rp 1.234.567,5"), "Paid", "G", "cpc", "C", "B", "GPS")
        data = generated("bu2", leads=[row])
        self.assertIn(data["leads"][0][4], (1234567.5, "1234567.5", 1234568, 1234567))  # whatever the profile's money rules give, never a float artefact
        self.assertNotIn("e+", json.dumps(data["leads"]))


class ConsistencyTests(unittest.TestCase):
    def test_counts_per_week_equal_the_weekly_report(self):
        for bu in ("bu1", "bu2"):
            _, _, view = build_report(bu)
            data = performance.load(snapshot(bu, leads=COHORT_LEADS, headers=HEADERS))
            week = params(**{"from": "2026-09-21", "to": "2026-09-27"})
            total = performance.summary(performance.series(data.leads, week))
            m = view["metrics"]
            self.assertEqual((int(total["sub"]), int(total["mql"]), int(total["sql"]), int(total["sqlv"]), int(total["won"]), int(total["wonv"])),
                             (m["Submission"], m["MQL"], m["SQL"], m["SQL Value"], m["Deal Won"], m["Deal Won Value"]), bu)


class FilterTests(unittest.TestCase):
    def setUp(self):
        self.data = load()

    def chosen(self, **filters):
        return params(lists=filters)

    def test_and_between_filters_or_inside_one(self):
        count = lambda **f: len(performance.filter_leads(self.data, self.chosen(**f)))
        self.assertEqual(count(), 4)
        self.assertEqual(count(channel=["Paid"]), 2)
        self.assertEqual(count(channel=["Paid", "Organic"]), 4)  # OR inside one filter
        self.assertEqual(count(channel=["Paid"], source=["Meta Ads"]), 1)  # AND between filters
        self.assertEqual(count(channel=["Paid"], source=["SEO"]), 0)
        self.assertEqual(count(campaign=["Camp A"], category=["Brand"], hardware=["GPS Tracker", "Fuel"]), 2)
        self.assertEqual(count(medium=["social"]), 1)

    def test_a_lead_without_a_value_is_chosen_by_the_empty_label(self):
        self.assertEqual(len(performance.filter_leads(self.data, self.chosen(campaign=[performance.EMPTY_LABEL]))), 1)
        self.assertEqual(len(performance.filter_leads(self.data, self.chosen(campaign=["Camp A", performance.EMPTY_LABEL]))), 3)

    def test_an_unknown_value_selects_nothing_rather_than_everything(self):
        self.assertEqual(performance.filter_leads(self.data, self.chosen(channel=["Tidak ada"])), [])

    def test_options_count_leads_matching_every_other_filter_but_not_their_own(self):
        opts = performance.options(self.data, self.chosen(channel=["Paid"]))
        self.assertEqual({o["value"]: o["count"] for o in opts["channel"]}, {"Paid": 2, "Organic": 2})  # its own filter does not shrink its own list
        self.assertEqual({o["value"]: o["count"] for o in opts["source"]}, {"Google Ads": 1, "Meta Ads": 1})  # Organic sources are gone
        self.assertEqual([o["value"] for o in opts["campaign"]], ["Camp A", "Camp B"])
        self.assertTrue(all(o["selected"] for o in opts["channel"] if o["value"] == "Paid"))

    def test_a_chosen_value_stays_listed_even_when_other_filters_leave_it_no_leads(self):
        opts = performance.options(self.data, self.chosen(channel=["Paid"], source=["SEO"]))
        seo = next(o for o in opts["source"] if o["value"] == "SEO")
        self.assertEqual((seo["count"], seo["selected"]), (0, True))  # so it can still be un-chosen

    def test_options_sort_by_count_then_name_with_empty_last(self):
        values = [o["value"] for o in performance.options(self.data, self.chosen())["campaign"]]
        self.assertEqual(values, ["Camp A", "Camp B", performance.EMPTY_LABEL])
        self.assertEqual([o["count"] for o in performance.options(self.data, self.chosen())["hardware"]], [2, 1, 1])

    def test_filters_change_the_numbers_everywhere_not_just_the_list(self):
        wide = params(**{"from": "2026-08-31", "to": "2026-09-27"})
        everything = performance.summary(performance.series(self.data.leads, wide))
        paid = performance.summary(performance.series(performance.filter_leads(self.data, params(lists={"channel": ["Paid"]}, **{"from": "2026-08-31", "to": "2026-09-27"})), wide))
        self.assertEqual((int(everything["sub"]), int(paid["sub"])), (4, 2))
        self.assertEqual((int(everything["sqlv"]), int(paid["sqlv"])), (3000000, 3000000))  # both SQLs are Paid
        organic = performance.summary(performance.series(performance.filter_leads(self.data, params(lists={"channel": ["Organic"]}, **{"from": "2026-08-31", "to": "2026-09-27"})), wide))
        self.assertEqual((int(organic["mql"]), int(organic["sql"]), int(organic["sqlv"])), (2, 0, 0))


class SeriesAndMatrixTests(unittest.TestCase):
    def setUp(self):
        self.data = load(leads=COHORT_LEADS[:4], headers=HEADERS)

    def test_week_buckets_clip_to_the_range_and_label_by_iso_week(self):
        p = params(**{"from": "2026-09-23", "to": "2026-10-02"})
        points = performance.series(self.data.leads, p)
        self.assertEqual([(x["label"], x["lo"], x["hi"]) for x in points], [("W39", date(2026, 9, 23), date(2026, 9, 27)), ("W40", date(2026, 9, 28), date(2026, 10, 2))])
        self.assertEqual((points[0]["sql"], points[0]["mql"]), (Decimal(1), Decimal(1)))  # the 22 Sep events are outside the range
        self.assertEqual(performance.summary(points)["sqlv"], Decimal(1000000))

    def test_day_and_month_grouping_with_zero_filled_gaps(self):
        days = performance.series(self.data.leads, params(per="hari", **{"from": "2026-09-20", "to": "2026-09-24"}))
        self.assertEqual([(x["label"], int(x["sub"])) for x in days], [("20 Sep", 0), ("21 Sep", 1), ("22 Sep", 1), ("23 Sep", 0), ("24 Sep", 0)])
        months = performance.series(self.data.leads, params(per="bulan", **{"from": "2026-08-15", "to": "2026-10-20"}))
        self.assertEqual([x["label"] for x in months], ["Agu 2026", "Sep 2026", "Okt 2026"])
        self.assertEqual(int(months[1]["sub"]), 4)
        self.assertFalse(performance.has_activity([months[0], months[2]]))

    def test_summary_rates_follow_the_report_definitions(self):
        total = performance.summary(performance.series(self.data.leads, params(per="bulan", **{"from": "2026-09-01", "to": "2026-09-30"})))
        self.assertEqual(total["mql_rate"], float(total["mql"] * 100 / total["sub"]))
        self.assertEqual(total["sql_rate"], float(total["sql"] * 100 / total["mql"]))
        self.assertEqual(total["won_rate"], 0.0)
        quiet = performance.summary(performance.series(self.data.leads, params(per="bulan", **{"from": "2026-08-01", "to": "2026-08-31"})))
        self.assertEqual((quiet["mql_rate"], quiet["won_rate"]), (None, None))

    def test_matrix_cells_pair_the_row_period_with_the_column_period(self):
        m = performance.matrix(self.data.leads, params(**{"from": "2026-09-21", "to": "2026-09-27"}))
        self.assertEqual(m["columns"][:2], ["2026-W39", "2026-W38"])
        row = m["rows"][0]
        self.assertEqual(row["label"], "2026-W39")
        self.assertEqual((row["cells"][0]["n"], row["total"]), (1, 2))  # one SQL from a lead that came in this week, one from 1 Sep (W36 sits in a later column)
        self.assertEqual(row["older"] + sum(c["n"] for c in row["cells"]), row["total"])
        mql = performance.matrix(self.data.leads, params(matriks="sub_mql", **{"from": "2026-08-31", "to": "2026-09-27"}))
        self.assertEqual([r["label"] for r in mql["rows"]][:2], ["2026-W39", "2026-W38"])
        self.assertEqual({r["label"]: r["total"] for r in mql["rows"]}["2026-W39"], 3)  # MQLs on 22 Sep (two) and 23 Sep (one)
        mql_sql = performance.matrix(self.data.leads, params(matriks="mql_sql", **{"from": "2026-09-21", "to": "2026-09-27"}))
        self.assertEqual(mql_sql["rows"][0]["total"], 2)

    def test_rows_are_the_periods_starting_in_the_range_newest_first_and_per_day_has_none(self):
        m = performance.matrix(self.data.leads, params(**{"from": "2026-10-05", "to": "2026-10-20"}))
        self.assertEqual([r["label"] for r in m["rows"]], ["2026-W43", "2026-W42", "2026-W41"])
        self.assertEqual(len(m["columns"]), 10)
        mid = performance.matrix(self.data.leads, params(**{"from": "2026-10-07", "to": "2026-10-20"}))
        self.assertEqual([r["label"] for r in mid["rows"]], ["2026-W43", "2026-W42"])
        self.assertIsNone(performance.matrix(self.data.leads, params(per="hari", **{"from": "2026-10-01", "to": "2026-10-10"})))

    def test_columns_beyond_the_tenth_fold_into_older_and_the_total_counts_everything(self):
        data = load(leads=[with_dims(lead("1", "BU1", "GPS", "1/5/2026", mql="1/6/2026", sql_date="10/13/2026", ppq="10/13/2026", arr="Rp 1.000.000"), "Paid", "G", "cpc", "C", "B", "GPS")], headers=DIM_HEADERS)
        row = performance.matrix(data.leads, params(**{"from": "2026-10-12", "to": "2026-10-18"}))["rows"][0]
        self.assertEqual((row["older"], row["total"], sum(c["n"] for c in row["cells"])), (1, 1, 0))

    def test_heat_scale_month_rows_and_the_row_cap(self):
        self.assertEqual([performance.heat(n) for n in (0, 1, 2, 3, 4, 5, 6, 40)], ["transparent", "#ec8359", "#f2a54a", "#f6cf57", "#a8cf5f", "#a8cf5f", "#5fbf84", "#5fbf84"])
        month = performance.matrix(self.data.leads, params(per="bulan", **{"from": "2026-08-01", "to": "2026-10-31"}))
        self.assertEqual([r["label"] for r in month["rows"]], ["Okt 2026", "Sep 2026", "Agu 2026"])
        long = performance.matrix(self.data.leads, params(**{"from": "2024-01-01", "to": "2026-10-20"}))
        self.assertEqual((len(long["rows"]), long["truncated"]), (performance.MATRIX_MAX_ROWS, True))

    def test_matrix_follows_the_filters(self):
        paid = performance.filter_leads(load(), params(lists={"channel": ["Paid"]}))
        row = performance.matrix(paid, params(**{"from": "2026-09-21", "to": "2026-09-27"}))["rows"][0]
        self.assertEqual(row["total"], 2)
        organic = performance.filter_leads(load(), params(lists={"channel": ["Organic"]}))
        self.assertEqual(performance.matrix(organic, params(**{"from": "2026-09-21", "to": "2026-09-27"}))["rows"][0]["total"], 0)


class ParameterTests(unittest.TestCase):
    def test_defaults_and_nonsense(self):
        p = performance.parse_params({}, AS_OF)
        self.assertEqual((p.per, p.end, p.matriks, p.error, p.filters), ("minggu", AS_OF, "sub_sql", "", {}))
        self.assertEqual(p.start, date(2026, 8, 3))
        self.assertEqual(performance.parse_params({"per": "hari"}, AS_OF).start, date(2026, 10, 8))
        self.assertEqual(performance.parse_params({"per": "bulan"}, AS_OF).start, date(2026, 5, 1))
        self.assertEqual(performance.parse_params({"per": "x", "from": "kacau", "matriks": "x"}, AS_OF).per, "minggu")
        self.assertEqual(performance.parse_params({"from": "2026-10-02", "to": "2026-10-01"}, AS_OF).error, performance.ERR_ORDER)
        self.assertEqual(performance.parse_params({"per": "hari", "from": "2026-01-01", "to": "2026-10-01"}, AS_OF).error, performance.ERR_DAYS)
        self.assertEqual(performance.parse_params({"per": "minggu", "from": "2026-01-01", "to": "2026-10-01"}, AS_OF).error, "")

    def test_filters_come_from_repeated_values_without_duplicates_and_ignore_unknown_keys(self):
        p = performance.parse_params({}, AS_OF, {"channel": ["Paid", "Paid", "Organic"], "bogus": ["x"], "campaign": ["x" * 201]})
        self.assertEqual(p.filters, {"channel": ["Paid", "Organic"]})
        self.assertEqual(p.active, 2)

    def test_chart_axis_uses_round_numbers(self):
        for value, top in ((0, 4), (3, 4), (5, 8), (17, 20), (101, 200), (2500000, 4000000)):
            self.assertEqual(performance.nice_max(Decimal(value)), Decimal(top))
        self.assertEqual((performance.compact(Decimal(1500000)), performance.compact(Decimal(250000)), performance.compact(Decimal(7))), ("1,5 jt", "250 rb", "7"))


class PageTests(ViewerCase):
    def setUp(self):
        super().setUp()
        self.store.performance["bu1"] = snapshot("bu1")
        self.login()

    def soup(self, query="", status=200, raw=None):
        response, body = self.call("GET", "/performa" + (raw if raw is not None else query))
        self.assertEqual(response.status, status, query)
        return BeautifulSoup(body, "html.parser")

    RANGE = "from=2026-08-31&to=2026-09-27&per=minggu"

    def test_the_sidebar_holds_company_dates_per_and_the_six_filters_with_counts(self):
        soup = self.soup("?bu=bu1&" + self.RANGE)
        side = soup.select_one("aside.pf-side")
        self.assertEqual(side.select_one("h2").get_text(), "Tampilan")
        self.assertEqual([o.get_text() for o in side.select("#bu option")], ["Perusahaan 1", "Perusahaan 2"])
        self.assertEqual((side.select_one("#dari")["value"], side.select_one("#sampai")["value"]), ("2026-08-31", "2026-09-27"))
        self.assertEqual([(i["value"], i.has_attr("checked")) for i in side.select("input[name=per]")], [("hari", False), ("minggu", True), ("bulan", False)])
        self.assertEqual([d.select_one(".fl").get_text() for d in side.select("details")], ["Channel", "Source", "Medium", "Campaign", "Category Campaign", "Campaign Hardware"])
        channel = side.select("details")[0]
        self.assertEqual([(o.select_one(".t").get_text(), o.select_one(".n").get_text()) for o in channel.select(".pf-opt")], [("Organic", "2 lead"), ("Paid", "2 lead")])
        self.assertEqual(channel.select_one(".fv").get_text(), "Semua")
        self.assertEqual(side.select_one("button[type=submit]").get_text(), "Terapkan")
        self.assertIsNone(side.select_one("a[href*='/performa?']"))  # nothing to clear yet
        self.assertIn(".pf-side{position:sticky;top:16px", " ".join(st.get_text() for st in soup.select("style")))
        self.assertEqual(soup.select_one("main")["style"], "max-width:1320px")

    def test_only_the_campaign_filter_has_a_search_box_and_chosen_campaigns_are_grouped_on_top(self):
        soup = self.soup("?bu=bu1&" + self.RANGE)
        boxes = soup.select("details [data-find]")
        self.assertEqual(len(boxes), 1)
        self.assertEqual(boxes[0].find_parent("details").select_one(".fl").get_text(), "Campaign")
        search = boxes[0].select_one("input[type=search]")
        self.assertIsNone(search.get("name"))  # the search text is never sent as a filter
        self.assertEqual(boxes[0].select_one(".pf-note").get_text(), "3 campaign")  # Camp A, Camp B and the (kosong) value
        self.assertEqual(len(boxes[0].select(".pf-grp")), 0)  # no group headings while nothing is chosen
        chosen = self.soup(raw="?bu=bu1&" + self.RANGE + "&campaign=Camp+B").select_one("details [data-find]")
        self.assertEqual([g.get_text() for g in chosen.select(".pf-grp")], ["Dipilih", "Lainnya"])
        self.assertEqual([o.select_one(".t").get_text() for o in chosen.select(".pf-opt")], ["Camp B", "Camp A", performance.EMPTY_LABEL])
        self.assertTrue(chosen.select_one(".pf-opt input").has_attr("checked"))
        self.assertEqual(len(self.soup("?bu=bu1&" + self.RANGE).select("input[type=search]")), 1)

    def test_chosen_filters_change_the_numbers_show_as_chips_and_can_be_removed_one_by_one(self):
        soup = self.soup(raw="?bu=bu1&" + self.RANGE + "&channel=Paid&source=Meta+Ads&source=Google+Ads")
        box = soup.select_one("[aria-label='Data yang sedang ditampilkan']")
        self.assertIn("Perusahaan 1 · 31 Agu 2026 sampai 27 Sep 2026 · per minggu", box.get_text())
        chips = [c.get_text().replace("×", "") for c in box.select(".pf-chip")]
        self.assertEqual(chips, ["Channel: Paid", "Source: Meta Ads", "Source: Google Ads"])  # in the order they were chosen
        rows = {tr.select("td")[0].get_text(): tr.select("td")[1].get_text() for tr in soup.select("section[aria-label='Ringkasan periode'] tbody tr")}
        self.assertEqual(rows["Submission"], "2")  # the two Paid leads, not four
        self.assertEqual(soup.select("details")[0].select_one(".fv").get_text(), "1 dipilih")
        self.assertEqual(soup.select("details")[1].select_one(".fv").get_text(), "2 dipilih")
        self.assertEqual(len([i for i in soup.select("aside input[type=checkbox]") if i.has_attr("checked")]), 3)
        remove = box.select(".pf-chip a")[0]["href"]
        self.assertNotIn("channel=Paid", remove)
        self.assertIn("source=Meta+Ads", remove)
        clear = soup.select_one("aside a.vw-link")
        self.assertEqual(clear.get_text(), "Hapus semua filter")
        for key in ("channel=", "source="):
            self.assertNotIn(key, clear["href"])
        self.assertIn("from=2026-08-31", clear["href"])  # clearing keeps the dates and the grouping

    def test_options_shrink_with_the_other_filters(self):
        soup = self.soup(raw="?bu=bu1&" + self.RANGE + "&channel=Paid")
        sources = [o.select_one(".t").get_text() for o in soup.select("details")[1].select(".pf-opt")]
        self.assertEqual(sources, ["Google Ads", "Meta Ads"])
        self.assertEqual(soup.select("details")[0].select(".pf-opt .t")[0].get_text(), "Organic")  # its own list keeps both channels

    def test_a_combination_without_leads_says_so_and_offers_the_way_out(self):
        soup = self.soup(raw="?bu=bu1&" + self.RANGE + "&channel=Paid&source=SEO")
        self.assertIn("Tidak ada lead yang cocok dengan filter ini", soup.get_text())
        self.assertEqual(soup.select("svg.pf-chart"), [])
        self.assertIsNotNone(soup.select_one(".pf-content a[href*='/performa?']"))
        none = self.soup("?bu=bu1&from=2020-01-01&to=2020-02-01")
        self.assertIn("Tidak ada data pada rentang ini", none.get_text())  # no filter involved: the plain empty message

    def test_the_empty_value_is_offered_as_kosong_and_selectable(self):
        soup = self.soup(raw="?bu=bu1&" + self.RANGE + "&campaign=" + "%28kosong%29")
        labels = [o.select_one(".t").get_text() for o in soup.select("details")[3].select(".pf-opt")]
        self.assertIn("(kosong)", labels)
        rows = {tr.select("td")[0].get_text(): tr.select("td")[1].get_text() for tr in soup.select("section[aria-label='Ringkasan periode'] tbody tr")}
        self.assertEqual(rows["Submission"], "1")

    def test_charts_summary_and_matrix_are_there_and_the_old_conversion_cohort_is_gone(self):
        soup = self.soup("?bu=bu1&" + self.RANGE)
        self.assertEqual([h.get_text() for h in soup.select("main h2")], ["Tampilan", "Filter", "Volume per minggu", "Nilai per minggu", "Ringkasan rentang", "Matriks cohort"])
        self.assertEqual(len(soup.select("svg.pf-chart")), 2)
        self.assertEqual(len(soup.select("details table")), 2)
        self.assertNotIn("Cohort konversi", soup.get_text())
        self.assertNotIn("Konversi yang dinilai", soup.get_text())
        self.assertIsNone(soup.select_one("#metrik"))

    def test_the_matrix_keeps_its_total_column_and_its_column_label_in_view(self):
        soup = self.soup("?bu=bu1&" + self.RANGE)
        section = soup.select_one("section[aria-label='Matriks cohort']")
        self.assertEqual(section.select_one("thead th[colspan] .grp").get_text(), "Minggu submission")
        self.assertIn("grp-th", section.select_one("thead th[colspan]")["class"])
        heads = section.select("thead tr:nth-child(2) th")
        self.assertEqual([h.get_text() for h in heads[-2:]], ["Lebih lama", "Total baris"])
        self.assertIn("stick-r", heads[-1]["class"])
        for row in section.select("tbody tr"):
            cells = row.select("td")
            self.assertEqual(len(cells), 12)
            self.assertIn("stick-r", cells[-1]["class"])  # the last column stays put when the table scrolls
            self.assertIn("stick-l", row.select_one("th")["class"])
            self.assertEqual(sum(int(c.get_text() or 0) for c in cells[:11]), int(cells[11].get_text()))
        css = " ".join(st.get_text() for st in soup.select("style"))
        for rule in (".pf-heat .stick-r{position:sticky;right:0", ".pf-heat .stick-l{position:sticky;left:0", ".pf-heat .grp{position:sticky"):
            self.assertIn(rule, css)
        self.assertEqual([o["value"] for o in section.select("#matriks option")], ["sub_sql", "mql_sql", "sub_mql"])
        self.assertEqual(section.select_one("#matriks")["form"], "perf-form")
        self.assertNotIn("Setiap baris adalah", section.get_text())  # the long explanation was removed on purpose

    def test_the_matrix_choice_changes_the_labels_and_per_day_has_no_matrix(self):
        mql = self.soup("?bu=bu1&" + self.RANGE + "&matriks=mql_sql").select_one("section[aria-label='Matriks cohort']")
        self.assertEqual(mql.select_one("thead th[rowspan]").get_text(), "Minggu SQL")
        self.assertEqual(mql.select_one("thead th[colspan]").get_text(), "Minggu MQL")
        month = self.soup("?bu=bu1&from=2026-07-01&to=2026-09-30&per=bulan").select_one("section[aria-label='Matriks cohort']")
        self.assertEqual(month.select_one("thead th[rowspan]").get_text(), "Bulan SQL")
        day = self.soup("?bu=bu1&from=2026-09-20&to=2026-09-27&per=hari").select_one("section[aria-label='Matriks cohort']")
        self.assertIn("Matriks tersedia per Minggu atau Bulan", day.get_text())
        self.assertIsNone(day.select_one("table"))

    def test_the_filters_in_the_address_reach_the_matrix_too(self):
        everyone = self.soup("?bu=bu1&" + self.RANGE).select("section[aria-label='Matriks cohort'] tbody tr")
        organic = self.soup(raw="?bu=bu1&" + self.RANGE + "&channel=Organic").select("section[aria-label='Matriks cohort'] tbody tr")
        total = lambda rows: sum(int(r.select("td")[-1].get_text()) for r in rows)
        self.assertGreater(total(everyone), total(organic))
        self.assertEqual(total(organic), 0)  # the Organic leads have no SQL

    def test_a_snapshot_without_lead_rows_asks_for_a_new_run_and_disables_the_filters(self):
        self.store.performance["bu1"]["data"] = {"v": 1, "as_of": "2026-10-21", "days": {}, "cohorts": {}}
        soup = self.soup("?bu=bu1")
        self.assertIn("dibuat dengan versi lama", soup.get_text())
        self.assertIn("Jalankan workflow Performa Generate", soup.get_text())
        self.assertTrue(soup.select_one("aside fieldset").has_attr("disabled"))
        self.assertIn("Filter belum tersedia di data ini", soup.select_one("aside").get_text())

    def test_bad_ranges_explain_themselves_and_draw_no_charts(self):
        for query, text in (("?from=2026-10-02&to=2026-10-01", performance.ERR_ORDER), ("?per=hari&from=2026-01-01&to=2026-10-01", performance.ERR_DAYS)):
            soup = self.soup(query)
            self.assertIn(text, soup.select_one("aside [role=alert]").get_text())
            self.assertEqual(soup.select("svg.pf-chart"), [])
        self.assertIsNotNone(self.soup("?from=2026-10-02&to=2026-10-01").select_one("#dari[aria-invalid=true]"))

    def test_missing_snapshot_and_database_failure_have_their_own_messages(self):
        belum = self.soup("?bu=bu2")
        self.assertIn("Belum ada data performa untuk Perusahaan 2", belum.get_text())
        self.store.latest_performance = lambda bu: (_for_error())
        failed = self.soup("", 503)
        self.assertIn("Data performa tidak bisa dimuat", failed.get_text())
        self.assertIsNotNone(failed.select_one("aside"))

    def test_company_picker_for_admins_fixed_name_and_access_for_single_company_users(self):
        self.store.names = {"bu1": "McEasy", "bu2": "LOL"}
        self.assertEqual([o.get_text() for o in self.soup().select("#bu option")], ["McEasy", "LOL"])
        self.store.create_user("andi", auth.hash_password(USER_PASSWORD), "user", False, ["bu1"], True)
        self.login(USER_PASSWORD, username="andi")
        user = self.soup()
        self.assertEqual(user.select("#bu"), [])
        self.assertIn("McEasy", user.select_one("aside").get_text())
        self.assertEqual(user.select_one("input[type=hidden][name=bu]")["value"], "bu1")
        self.assertEqual(self.call("GET", "/performa?bu=bu2")[0].status, 403)
        self.assertEqual(self.call("GET", "/performa?bu=bu9")[0].status, 404)
        self.assertEqual([a["href"] for a in user.select(".vw-menu a")], ["/performa"])

    def test_needs_a_session_and_never_shows_lead_names(self):
        self.cookie = ""
        response, _ = self.call("GET", "/performa", cookie=False)
        self.assertEqual((response.status, response.getheader("Location")), (303, "/login"))
        self.login()
        _, body = self.call("GET", "/performa?bu=bu1&per=bulan")
        for name in ("Co1", "Co2", "Co3", "Co4"):
            self.assertNotIn(name, body)
        self.assertEqual(self.call("GET", "/performa?bu=bu1&channel=" + "x" * 5000)[0].status, 200)  # an oversized value is ignored, not an error


def _for_error():
    raise RuntimeError("no such table")


if __name__ == "__main__":
    unittest.main()
