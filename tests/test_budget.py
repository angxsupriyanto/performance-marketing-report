import sys
import unittest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import report_view  # noqa: E402
from test_viewer import UTC, ViewerCase  # noqa: E402
from test_viewer_users import USER_PASSWORD  # noqa: E402
from viewer import auth, budget  # noqa: E402


def snap(month, total, campaigns, as_of=None, minute=0, snap_id=None):
    return {"snapshot_id": snap_id or f"s{minute}", "bu": "bu1", "month": month, "total_budget": total, "spend_as_of": as_of, "data": {"campaigns": campaigns},
            "saved_by": "admin", "saved_at": datetime(2026, 10, 1, 8, minute, tzinfo=UTC)}


class CalendarTests(unittest.TestCase):
    def test_weeks_belong_to_the_month_of_their_thursday_and_may_straddle_two_months(self):
        weeks = budget.weeks_of_month("2026-10")
        self.assertEqual([w[0] for w in weeks], ["2026-W40", "2026-W41", "2026-W42", "2026-W43", "2026-W44"])
        self.assertEqual((weeks[0][1], weeks[0][2]), (date(2026, 9, 28), date(2026, 10, 4)))  # starts in September
        self.assertEqual((weeks[-1][1], weeks[-1][2]), (date(2026, 10, 26), date(2026, 11, 1)))  # ends in November
        self.assertEqual(budget.weeks_of_month("2026-11")[0][0], "2026-W45")  # continues where October stopped
        self.assertEqual([budget.month_of_week(k) for k in ("2026-W39", "2026-W40", "2026-W44", "2026-W45")], ["2026-09", "2026-10", "2026-10", "2026-11"])
        covered = [w[0] for m in (f"2026-{n:02d}" for n in range(1, 13)) for w in budget.weeks_of_month(m)]
        self.assertEqual(len(covered), len(set(covered)))  # no week is in two months, so weeks never double count
        self.assertEqual(budget.weeks_of_month("2026-12")[-1][0], "2026-W53")

    def test_month_helpers(self):
        self.assertEqual((budget.shift_month("2026-01", -1), budget.shift_month("2026-12", 1), budget.month_label("2026-10")), ("2025-12", "2027-01", "Oktober 2026"))
        self.assertEqual(budget.month_bounds("2028-02"), (date(2028, 2, 1), date(2028, 2, 29)))
        self.assertEqual((budget.month_of_period("week", date(2026, 10, 26)), budget.month_of_period("month", date(2026, 10, 1))), ("2026-10", "2026-10"))
        self.assertEqual(budget.prev_week("2026-W01"), "2025-W52")
        self.assertEqual(budget.months_needed("week", date(2026, 11, 2)), ["2026-11", "2026-10"])  # W45's previous week (W44) is October's
        self.assertEqual(budget.months_needed("week", date(2026, 10, 12)), ["2026-10", "2026-09"])


OCT = {"Alpha": {"budget": 6000000, "month_spend": 3000000, "weeks": {"2026-W42": 1000000, "2026-W41": 800000}},
       "Beta": {"budget": 3000000, "month_spend": 1500000, "weeks": {"2026-W42": 500000}}}


class ReportBudgetTests(unittest.TestCase):
    def setUp(self):
        early = {"Alpha": {"budget": 6000000, "month_spend": 2000000, "weeks": {}}, "Beta": {"budget": 3000000, "month_spend": 1000000, "weeks": {}}}
        self.snaps = {
            "2026-10": [snap("2026-10", 10000000, OCT, date(2026, 10, 18), 5), snap("2026-10", 10000000, early, date(2026, 10, 11), 1)],
            "2026-09": [snap("2026-09", 8000000, {"Alpha": {"budget": 5000000, "month_spend": 5000000, "weeks": {}}, "Beta": {"budget": 3000000, "month_spend": 2000000, "weeks": {}}}, date(2026, 9, 30), 0)],
        }

    def week42(self):
        return budget.report_budget("week", date(2026, 10, 12), date(2026, 10, 18), "2026-W42", self.snaps)

    def test_numbers_for_a_weekly_report(self):
        b = self.week42()
        self.assertEqual((b["state"], b["total"], b["week"], b["prev_week"], b["spent"], b["left"], round(b["used"], 1)),
                         ("ok", Decimal(10000000), Decimal(1500000), Decimal(800000), Decimal(4500000), Decimal(5500000), 45.0))
        self.assertEqual((b["prev"]["total"], b["prev"]["spent"], b["prev"]["left"], b["prev"]["used"]), (Decimal(8000000), Decimal(7000000), Decimal(1000000), 87.5))
        self.assertEqual([r["name"] for r in b["rows"]], ["Alpha", "Beta"])  # largest monthly spend first
        self.assertEqual((b["rows"][0]["left"], round(b["rows"][0]["used"], 1), b["rows"][0]["week"]), (Decimal(3000000), 50.0, Decimal(1000000)))
        self.assertEqual(b["unallocated"], Decimal(1000000))  # 10M total, 9M given to campaigns
        self.assertEqual((b["month_label"], b["prev_label"], b["as_of"]), ("Oktober 2026", "September 2026", date(2026, 10, 18)))

    def test_monthly_spend_is_the_latest_figure_filled_up_to_the_report_end_not_a_sum_of_weeks(self):
        early = budget.report_budget("week", date(2026, 10, 5), date(2026, 10, 11), "2026-W41", self.snaps)
        self.assertEqual((early["spent"], early["as_of"]), (Decimal(3000000), date(2026, 10, 11)))  # the 11 Oct figures, not the newer 18 Oct ones
        self.assertEqual(early["rows"][0]["spent"], Decimal(2000000))
        none = budget.report_budget("week", date(2026, 10, 5), date(2026, 10, 10), "2026-W41", self.snaps)  # nothing filled up to 10 Oct
        self.assertEqual((none["spent"], none["left"], none["used"], none["as_of"]), (None, None, None, None))
        self.assertEqual(none["total"], Decimal(10000000))
        self.assertNotEqual(self.week42()["spent"], self.week42()["week"])  # weekly and monthly are independent figures

    def test_missing_pieces_are_none_not_zero(self):
        gone = budget.report_budget("week", date(2026, 10, 12), date(2026, 10, 18), "2026-W42", {"2026-10": self.snaps["2026-10"]})
        self.assertEqual((gone["prev"]["total"], gone["prev"]["spent"], gone["prev_week"]), (None, None, Decimal(800000)))
        self.assertEqual(budget.report_budget("week", date(2026, 10, 19), date(2026, 10, 25), "2026-W43", self.snaps)["week"], None)
        self.assertEqual(budget.report_budget("week", date(2026, 10, 12), date(2026, 10, 18), "2026-W42", {})["state"], "belum")
        no_total = {"2026-10": [snap("2026-10", None, OCT, None, 1)]}
        self.assertEqual(budget.report_budget("week", date(2026, 10, 12), date(2026, 10, 18), "2026-W42", no_total)["state"], "belum")

    def test_over_budget_and_many_campaigns(self):
        many = {f"C{i:02d}": {"budget": 1000, "month_spend": 100 * i, "weeks": {}} for i in range(1, 13)}
        many["Over"] = {"budget": 500, "month_spend": 900, "weeks": {}}
        b = budget.report_budget("month", date(2026, 10, 1), date(2026, 10, 31), "2026-10", {"2026-10": [snap("2026-10", 50000, many, date(2026, 10, 31), 1)]})
        self.assertEqual(len(b["rows"]), budget.TOP_ROWS)
        self.assertEqual(b["rows"][0]["name"], "C12")
        self.assertEqual((b["rest"]["count"], b["rest"]["spent"]), (3, Decimal(100 + 200 + 300)))  # the three smallest are folded into one line
        self.assertNotIn("week", b)  # a monthly report has no weekly column
        over = {"Over": {"budget": 500, "month_spend": 900, "weeks": {}}}
        o = budget.report_budget("month", date(2026, 10, 1), date(2026, 10, 31), "2026-10", {"2026-10": [snap("2026-10", 500, over, date(2026, 10, 31), 1)]})
        self.assertEqual((o["left"], o["rows"][0]["left"], o["rows"][0]["used"]), (Decimal(-400), Decimal(-400), 180.0))


FORM = {"total": "10.000.000", "as_of": "2026-10-18", "n_0": "Alpha", "b_0": "6.000.000", "m_0": "3.000.000", "w_0_2026-W41": "800.000", "w_0_2026-W42": "Rp 1.000.000",
        "n_1": "Beta", "b_1": "3000000", "m_1": "", "w_1_2026-W42": ""}
TODAY = date(2026, 10, 21)


class FormTests(unittest.TestCase):
    def test_a_valid_form_becomes_the_stored_shape(self):
        parsed = budget.parse_form(FORM, "2026-10", TODAY)
        self.assertEqual(parsed["total"], 10000000)
        self.assertEqual(parsed["as_of"], date(2026, 10, 18))
        self.assertEqual(parsed["campaigns"]["Alpha"], {"budget": 6000000, "month_spend": 3000000, "weeks": {"2026-W41": 800000, "2026-W42": 1000000}})
        self.assertEqual(parsed["campaigns"]["Beta"], {"budget": 3000000, "month_spend": None, "weeks": {}})

    def assertRefused(self, overrides, field, text, today=TODAY):
        with self.assertRaises(budget.FormError) as ctx:
            budget.parse_form({**FORM, **overrides}, "2026-10", today)
        self.assertIn(field, ctx.exception.errors, ctx.exception.errors)
        self.assertIn(text, ctx.exception.errors[field])

    def test_each_rule_names_the_field(self):
        self.assertRefused({"b_0": "9.000.000"}, "total", "melebihi total budget")  # 9M + 3M > 10M
        self.assertRefused({"total": ""}, "total", "Isi total budget lebih dulu")
        self.assertRefused({"b_1": "1,5"}, "b_1", "Budget Beta")
        self.assertRefused({"w_0_2026-W44": "100"}, "w_0_2026-W44", "belum berjalan")
        self.assertRefused({"w_0_2026-W42": "abc"}, "w_0_2026-W42", "Spend W42 Alpha")
        self.assertRefused({"as_of": ""}, "as_of", "Isi tanggal")
        self.assertRefused({"as_of": "2026-09-30"}, "as_of", "di dalam Oktober 2026")
        self.assertRefused({"as_of": "2026-10-25"}, "as_of", "masa depan")
        self.assertRefused({"n_1": "alpha"}, "n_1", "dua kali")
        self.assertRefused({"n_1": "   "}, "n_1", "tidak boleh kosong")
        self.assertRefused({"n_1": "x" * 101}, "n_1", "maksimal")

    def test_zero_budget_means_none_blank_means_none_and_a_stray_date_is_dropped(self):
        parsed = budget.parse_form({**FORM, "b_1": "0", "m_0": "", "total": "6.000.000"}, "2026-10", TODAY)
        self.assertIsNone(parsed["campaigns"]["Beta"]["budget"])
        self.assertIsNone(parsed["as_of"])  # a date without any monthly spend means nothing
        self.assertEqual(parsed["total"], 6000000)
        empty = budget.parse_form({"total": "", "as_of": "", "n_0": "Solo"}, "2026-10", TODAY)  # a campaign added with no numbers survives
        self.assertEqual((empty["total"], list(empty["campaigns"])), (None, ["Solo"]))
        self.assertEqual(budget.parse_form({}, "2026-10", TODAY)["campaigns"], {})

    def test_a_week_that_straddles_the_month_is_accepted_under_its_thursday_month(self):
        parsed = budget.parse_form({**FORM, "w_0_2026-W44": "250.000"}, "2026-10", date(2026, 10, 30))
        self.assertEqual(parsed["campaigns"]["Alpha"]["weeks"]["2026-W44"], 250000)  # 26 Oct to 1 Nov, entered in October


class BudgetPageTests(ViewerCase):
    def setUp(self):
        super().setUp()
        self.login()
        self.now = datetime.now(timezone(timedelta(hours=7))).date()
        self.month = budget.month_of_date(self.now)

    def form(self, **extra):
        first = budget.weeks_of_month(self.month)[0][0]
        base = {"csrf": self.csrf(), "bu": "bu1", "month": self.month, "base": "", "total": "10.000.000", "as_of": self.now.replace(day=1).isoformat(),
                "n_0": "Alpha", "b_0": "6.000.000", "m_0": "3.000.000", f"w_0_{first}": "800.000", "n_1": "Beta", "b_1": "3.000.000"}
        base.update(extra)
        return base

    def get(self, query=""):
        response, body = self.call("GET", "/budget" + query)
        return response, BeautifulSoup(body, "html.parser")

    def test_the_page_lists_tracker_campaigns_weeks_and_an_empty_history(self):
        response, soup = self.get()
        self.assertEqual(response.status, 200)
        self.assertEqual(soup.select_one("h1").get_text(), "Budget")
        self.assertEqual([o.get_text() for o in soup.select("#bu option")], ["Perusahaan 1", "Perusahaan 2"])
        self.assertIn(budget.month_label(self.month), [o.get_text() for o in soup.select("#month option")])
        self.assertEqual(soup.select("#t-budget [data-name]"), [])  # starts empty: the tracker names are offered, not listed
        self.assertTrue(soup.select_one("#tables").has_attr("hidden"))
        self.assertFalse(soup.select_one("#empty-box").has_attr("hidden"))
        picker = {o["data-pick-name"]: o.has_attr("hidden") for o in soup.select("#pick-list [data-pick-name]")}
        self.assertEqual(picker, {"Camp A": False})
        self.assertTrue(soup.select_one("#picker").has_attr("hidden"))
        self.assertEqual(soup.select_one("#buka")["aria-controls"], "picker")
        self.assertIsNone(soup.select_one("#baru"))  # no free-text name: every campaign comes from the tracker
        weeks = budget.weeks_of_month(self.month)
        heads = [th.get_text(" ", strip=True) for th in soup.select("#t-weeks thead th")][1:]
        self.assertEqual([h.split()[0] for h in heads], [w[0].split("-")[1] for w in weeks])
        future = {w[0] for w in weeks if w[1] > self.now}
        template = BeautifulSoup(soup.select_one("#tpl-weeks").decode_contents(), "html.parser")
        for key, _, _ in weeks:
            self.assertEqual(template.select_one(f'input[name="w___I___{key}"]').has_attr("disabled"), key in future, key)
        self.assertIn("Belum ada budget tersimpan untuk Perusahaan 1", soup.get_text())
        self.assertEqual(soup.select_one('input[name="base"]')["value"], "")
        self.assertEqual(len(soup.select("template")), 3)

    def test_the_picker_also_offers_campaigns_only_the_newer_performa_snapshot_knows(self):
        self.store.performance["bu1"] = {"snapshot_id": "p", "generated_at": datetime.now(timezone.utc), "as_of": self.now,
                                         "data": {"v": 2, "dims": {"campaign": ["", "Camp A", "Solusi - Video Monitoring - CPC"]}, "leads": []}}
        _, soup = self.get()
        self.assertEqual([o["data-pick-name"] for o in soup.select("#pick-list [data-pick-name]")], ["Camp A", "Solusi - Video Monitoring - CPC"])  # no blank name, no duplicate

    def test_the_picker_has_channel_source_medium_filters_only_when_a_performa_snapshot_exists(self):
        _, soup = self.get()
        self.assertEqual(soup.select("#picker .pk-dd"), [])  # no snapshot: just the search box
        self.store.performance["bu1"] = {"snapshot_id": "p", "generated_at": datetime.now(timezone.utc), "as_of": self.now,
                                         "data": {"v": 2, "as_of": self.now.isoformat(), "dims": {"channel": ["Paid"], "source": ["Meta Ads"], "medium": ["cpc"], "campaign": ["Camp A", "Camp Z"], "category": [""], "hardware": [""]},
                                                  "leads": [[738000, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0]]}}
        _, soup = self.get()
        self.assertEqual([d.select_one(".fl").get_text() for d in soup.select("#picker .pk-dd")], ["Channel", "Source", "Medium"])
        self.assertEqual([o["data-label"] for o in soup.select('#picker [data-key="channel"]')], ["Paid"])
        names = {o["data-label"] for o in soup.select('#pick-list [data-key="campaign"]')}
        self.assertEqual(names, {"Camp A", "Camp Z"})  # Camp A only in the report, Camp Z only in the snapshot
        script = " ".join(sc.get_text() for sc in soup.select("script") if "makeCascade" in sc.get_text())
        self.assertIn('"combos":[[0,0,0,1]]', script)

    def test_saving_adds_a_version_and_the_page_shows_it_with_history(self):
        response, _ = self.call("POST", "/budget", self.form())
        self.assertEqual((response.status, response.getheader("Location")), (303, f"/budget?bu=bu1&month={self.month}&saved=1"))
        self.assertEqual(len(self.store.snaps), 1)
        row = self.store.snaps[0]
        self.assertEqual((row["bu"], row["month"], row["total_budget"], row["saved_by"]), ("bu1", self.month, 10000000, "admin"))
        self.assertEqual(row["data"]["campaigns"]["Alpha"]["budget"], 6000000)
        _, soup = self.get(f"?bu=bu1&month={self.month}&saved=1")
        self.assertIn("Budget dan spend Perusahaan 1", soup.select_one(".vw-ok").get_text())
        self.assertEqual(soup.select_one("#total")["value"], "10.000.000")
        self.assertEqual({i["name"]: i["value"] for i in soup.select("#t-budget input[name^=b_]")}, {"b_0": "6.000.000", "b_1": "3.000.000"})  # saved campaigns show by themselves
        self.assertFalse(soup.select_one("#tables").has_attr("hidden"))
        picker = {o["data-pick-name"]: o.has_attr("hidden") for o in soup.select("#pick-list [data-pick-name]")}
        self.assertEqual(picker, {"Alpha": True, "Beta": True, "Camp A": False})  # added ones leave the list, the rest stays offered
        hist = [td.get_text() for td in soup.select("section[aria-label='Riwayat budget'] tbody td")]
        self.assertEqual(hist[:3], [budget.month_label(self.month), "Rp 10.000.000", "Rp 3.000.000"])
        self.assertIn("oleh admin", hist[4])
        self.assertEqual(soup.select_one('input[name="base"]')["value"], "snap-1")

    def test_each_save_is_a_new_row_and_a_stale_form_cannot_overwrite_a_newer_save(self):
        self.call("POST", "/budget", self.form())
        again = self.form(base="snap-1", total="12.000.000")
        self.assertEqual(self.call("POST", "/budget", again)[0].status, 303)
        self.assertEqual([s["total_budget"] for s in self.store.snaps], [10000000, 12000000])
        stale = self.call("POST", "/budget", self.form(base="snap-1", total="11.000.000"))
        self.assertEqual(stale[0].status, 409)
        self.assertIn("sudah diubah orang lain", stale[1])
        self.assertEqual(len(self.store.snaps), 2)

    def test_invalid_input_saves_nothing_keeps_what_was_typed_and_explains(self):
        response, body = self.call("POST", "/budget", self.form(b_0="9.000.000"))
        self.assertEqual(response.status, 422)
        soup = BeautifulSoup(body, "html.parser")
        self.assertIn("melebihi total budget", soup.get_text())
        self.assertEqual(soup.select_one("#total")["aria-invalid"], "true")
        self.assertEqual(soup.select_one('input[name="b_0"]')["value"], "9.000.000")
        self.assertEqual(self.store.snaps, [])
        future = next((w for w in budget.weeks_of_month(self.month) if w[1] > self.now), None)
        if future:
            bad = self.call("POST", "/budget", self.form(**{f"w_0_{future[0]}": "5"}))
            self.assertEqual(bad[0].status, 422)
            self.assertIn("belum berjalan", bad[1])
        self.assertEqual(self.call("POST", "/budget", self.form(bu="bu9"))[0].status, 400)
        self.assertEqual(self.call("POST", "/budget", self.form(month="1999-01"))[0].status, 400)

    def test_a_database_failure_keeps_the_typed_values_for_a_retry(self):
        self.store.fail_writes = True
        response, body = self.call("POST", "/budget", self.form())
        self.assertEqual(response.status, 503)
        self.assertIn("Budget tidak tersimpan", body)
        self.assertEqual(BeautifulSoup(body, "html.parser").select_one("#total")["value"], "10.000.000")
        self.store.fail_writes, self.store.down = False, True
        self.assertEqual(self.call("GET", "/budget")[0].status, 503)

    def test_an_added_campaign_is_saved_and_listed_next_time_and_gaps_from_removed_rows_are_fine(self):
        form = self.form(n_5="Campaign Baru", b_5="", total="10.000.000")  # rows 2 to 4 were removed in the browser
        self.call("POST", "/budget", form)
        self.assertEqual(sorted(self.store.snaps[0]["data"]["campaigns"]), ["Alpha", "Beta", "Campaign Baru"])
        _, soup = self.get(f"?bu=bu1&month={self.month}")
        self.assertEqual(sorted(td.get_text() for td in soup.select("#t-budget [data-name]")), ["Alpha", "Beta", "Campaign Baru"])
        self.assertIn("Campaign Baru", [td.get_text() for td in soup.select("#t-month [data-name]")])
        self.assertEqual(len(soup.select("#t-budget [data-remove]")), 3)

    def test_removing_every_campaign_saves_an_empty_list_and_a_failed_save_keeps_the_rows(self):
        only_total = {k: v for k, v in self.form().items() if not k[:2] in ("n_", "b_", "m_", "w_")}
        self.assertEqual(self.call("POST", "/budget", only_total)[0].status, 303)
        self.assertEqual(self.store.snaps[0]["data"]["campaigns"], {})
        response, body = self.call("POST", "/budget", self.form(b_1="99.000.000"))
        soup = BeautifulSoup(body, "html.parser")
        self.assertEqual(response.status, 422)
        self.assertEqual([td.get_text() for td in soup.select("#t-budget [data-name]")], ["Alpha", "Beta"])
        self.assertFalse(soup.select_one("#tables").has_attr("hidden"))

    def test_only_admins_reach_the_budget_page(self):
        self.store.create_user("andi", auth.hash_password(USER_PASSWORD), "user", True, [], True)
        self.login(USER_PASSWORD, username="andi")
        self.assertEqual(self.call("GET", "/budget")[0].status, 403)
        self.assertEqual(self.call("POST", "/budget", {"csrf": self.csrf(), "bu": "bu1", "month": self.month})[0].status, 403)
        self.assertEqual(self.store.snaps, [])
        _, home = self.call("GET", "/")
        self.assertNotIn("/budget", home)


class ReportSectionTests(ViewerCase):
    """Report W39 2026 is 21 to 27 September, so its month is September."""

    def setUp(self):
        super().setUp()
        sept = {"Alpha": {"budget": 6000000, "month_spend": 3000000, "weeks": {"2026-W39": 1000000, "2026-W38": 800000}}, "Beta": {"budget": 3000000, "month_spend": 1500000, "weeks": {"2026-W39": 500000}}}
        aug = {"Alpha": {"budget": 5000000, "month_spend": 4000000, "weeks": {}}}
        self.store.snaps = [snap("2026-09", 10000000, sept, date(2026, 9, 27), 3, "s3") | {"bu": "bu1"}, snap("2026-08", 8000000, aug, date(2026, 8, 31), 1, "s1") | {"bu": "bu1"}]
        self.login()

    def soup(self, bu="bu1"):
        return BeautifulSoup(self.call("GET", f"/report/{bu}/2026-W39")[1], "html.parser")

    def test_the_section_is_the_first_thing_in_the_report_with_the_mockup_cards(self):
        soup = self.soup()
        section = soup.select_one('section[aria-label="Budget dan spend September 2026"]')
        report = soup.select_one('section[aria-label="Report"]')
        self.assertIsNotNone(section)
        self.assertIs(section.find_parent("section"), report)
        titles = [h.get_text() for h in report.select("h3")]
        self.assertEqual(titles[0], "Budget dan spend September 2026")
        self.assertLess(str(report).index("Budget dan spend"), str(report).index('class="cards"'))
        cards = [(c.select("div")[0].get_text(), c.select("div")[1].get_text(), c.select("div")[2].get_text()) for c in section.select("div[style*='border: 1px solid']") if len(c.select("div")) == 3]
        self.assertEqual(cards[0], ("Total budget", "Rp 10.000.000", "Agustus 2026: Rp 8.000.000"))
        self.assertEqual(cards[1], ("Spend Week 39", "Rp 1.500.000", "Week 38: Rp 800.000"))
        self.assertEqual(cards[2], ("Spend September 2026", "Rp 4.500.000", "Agustus 2026: Rp 4.000.000"))
        self.assertEqual(cards[3], ("Sisa budget", "Rp 5.500.000", "Agustus 2026: Rp 4.000.000"))
        bar = section.select_one('[role="progressbar"]')
        self.assertEqual((bar["aria-valuenow"], bar["aria-valuemin"], bar["aria-valuemax"]), ("45", "0", "100"))
        self.assertIn("45,0%", section.get_text())
        self.assertIn("Agustus 2026: 50,0%", section.get_text())  # 4M of 8M
        self.assertIn("September 2026 bulan berjalan, belum penuh.", section.get_text())

    def test_the_table_has_the_mockup_columns_a_total_row_and_the_unallocated_remainder(self):
        section = self.soup().select_one('section[aria-label="Budget dan spend September 2026"]')
        table = section.select_one("table")
        self.assertEqual([th.get_text() for th in table.select("thead th")], ["Campaign", "Budget", "Spend Week 39", "Spend September 2026", "Sisa", "Pemakaian"])
        rows = [[td.get_text() for td in tr.select("td")] for tr in table.select("tbody tr")]
        self.assertEqual(rows[0], ["Alpha", "Rp 6.000.000", "Rp 1.000.000", "Rp 3.000.000", "Rp 3.000.000", "50,0%"])
        self.assertEqual(rows[1][0], "Beta")
        self.assertEqual(rows[2][:2], ["Belum dialokasikan ke campaign", "Rp 1.000.000"])
        self.assertEqual([td.get_text() for td in table.select("tfoot td")], ["TOTAL", "Rp 10.000.000", "Rp 1.500.000", "Rp 4.500.000", "Rp 5.500.000", "45,0%"])

    def test_admins_get_a_link_and_everyone_else_a_hint_when_budget_is_not_set(self):
        self.store.snaps = []
        soup = self.soup()
        section = soup.select_one('section[aria-label="Budget dan spend September 2026"]')
        self.assertIn("Budget September 2026 belum diatur. Atur di halaman Budget untuk melihat pemakaian.", section.get_text(" "))
        self.assertEqual(section.select_one("a")["href"], "/budget?bu=bu1&month=2026-09")
        self.store.ensure_bootstrap_admin(self.hash)
        self.store.create_user("andi", auth.hash_password(USER_PASSWORD), "user", True, [], True)
        self.login(USER_PASSWORD, username="andi")
        user = self.soup().select_one('section[aria-label="Budget dan spend September 2026"]')
        self.assertIn("Hubungi admin untuk mengatur budget.", user.get_text(" "))
        self.assertIsNone(user.select_one("a"))

    def test_a_budget_failure_does_not_hide_the_report(self):
        self.store.budget_snapshots = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no such table"))
        soup = self.soup()
        self.assertIn("Budget tidak bisa dimuat. Database marketing_reports tidak menjawab. Muat ulang halaman ini.", soup.get_text())
        self.assertEqual(len(soup.select(".cards")), 2)  # the rest of the report is intact

    def test_only_spend_that_was_filled_is_shown_and_spend_beyond_the_budget_is_called_over(self):
        sept = {"Alpha": {"budget": 1000000, "month_spend": 1500000, "weeks": {}}}
        self.store.snaps = [snap("2026-09", 2000000, sept, date(2026, 9, 27), 3, "s3") | {"bu": "bu1"}]
        section = self.soup().select_one('section[aria-label="Budget dan spend September 2026"]')
        text = section.get_text(" ")
        self.assertIn("Belum diisi", text)  # no weekly spend entered for Week 39
        self.assertIn("Agustus 2026: Belum ada data", text)
        self.assertEqual([td.get_text() for td in section.select("tbody tr")[0].select("td")][4:], ["Melebihi Rp 500.000", "150,0%"])

    def test_company_two_has_its_own_section_and_a_monthly_report_has_no_weekly_column(self):
        self.assertIn("Budget September 2026 belum diatur", self.soup("bu2").get_text())  # budgets are per company
        view = report_view.extract_view(self.store.html["bu1"][0])
        b = budget.report_budget("month", date(2026, 9, 1), date(2026, 9, 30), "2026-09", {"2026-09": self.store.snaps[:1], "2026-08": self.store.snaps[1:]})
        b.update(bu="bu1", admin=True, month="2026-09", prev_week_label="")
        soup = BeautifulSoup(report_view.render_document(view, None, None, budget=b), "html.parser")
        section = soup.select_one('section[aria-label^="Budget dan spend"]')
        self.assertEqual([th.get_text() for th in section.select("thead th")], ["Campaign", "Budget", "Spend September 2026", "Sisa", "Pemakaian"])
        self.assertNotIn("belum penuh", section.get_text())
        self.assertNotIn("Spend Week", section.get_text())


if __name__ == "__main__":
    unittest.main()


class NurturingGroupTests(unittest.TestCase):
    def rel(self):
        labels = {"channel": ["Paid", "Owned"], "source": ["Google Ads", "Nurturing"], "medium": ["CPC", "Email", "WhatsApp", "(kosong)"],
                  "campaign": ["Solusi - CPC", "Promo A", "Promo B", "Promo W", "Mixed", "Tanpa medium"]}
        combos = [[0, 0, 0, 0], [1, 1, 1, 1], [1, 1, 1, 2], [1, 1, 2, 3], [0, 0, 0, 4], [1, 1, 1, 4], [1, 1, 3, 5]]
        return {"labels": labels, "combos": combos}

    def test_a_campaign_only_under_nurturing_maps_to_its_medium_group(self):
        from viewer import performance
        self.assertEqual(performance.nurturing_groups(self.rel()),
                         {"promo a": "Email Nurturing", "promo b": "Email Nurturing", "promo w": "WhatsApp Nurturing", "tanpa medium": "Nurturing"})
        # "Mixed" also runs under Google Ads, so it keeps its own name

    def test_without_a_nurturing_source_nothing_is_grouped(self):
        from viewer import performance
        rel = {"labels": {"channel": ["Paid"], "source": ["Google Ads"], "medium": ["CPC"], "campaign": ["A"]}, "combos": [[0, 0, 0, 0]]}
        self.assertEqual(performance.nurturing_groups(rel), {})
        self.assertEqual(performance.nurturing_groups(None), {})


class NurturingPickerMarkupTests(unittest.TestCase):
    def page(self, rows=()):
        from datetime import date
        from viewer import pages
        grouped = {"welcome series": "Email Nurturing", "promo wa": "WhatsApp Nurturing"}
        return pages.budget_page("bu1", {"bu1": "McEasy"}, "2026-10", [("2026-10", "Oktober 2026")], list(rows), ["Brand search", "Promo WA", "Welcome series"],
                                 [], "", "", "", date(2026, 10, 26), {}, [], "csrf", "nonce", {"username": "admin", "role": "admin"}, grouped=grouped)

    def test_a_grouped_campaign_keeps_its_name_shows_the_group_and_adds_the_group(self):
        html = self.page()
        self.assertIn('data-label="Welcome series" data-pick-name="Email Nurturing" data-group="Email Nurturing"', html)
        self.assertIn("Grup: Email Nurturing", html)
        self.assertIn('data-label="Brand search" data-pick-name="Brand search" data-group=""', html)
        self.assertIn('var groupNames=["Email Nurturing", "WhatsApp Nurturing"]', html)

    def test_a_saved_group_row_carries_the_group_tag_but_a_plain_row_does_not(self):
        row = lambda name, i: {"idx": i, "name": name, "budget": "", "month": "", "weeks": {}}
        html = self.page([row("Email Nurturing", 0), row("Brand search", 1)])
        self.assertIn('Email Nurturing <span class="pk-tag">Grup</span>', html)
        self.assertNotIn('Brand search <span class="pk-tag">', html)
