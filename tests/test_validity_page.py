"""The admin page for how long MQL, SQL and Deal Won stay valid: reading, saving, refusing bad input, and who may use it."""
import json
import unittest

from bs4 import BeautifulSoup

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_viewer import ViewerCase  # noqa: E402
from test_viewer_users import USER_PASSWORD  # noqa: E402
from viewer import auth, validity  # noqa: E402

BASE = {"g_mql_mode": "none", "g_mql_n": "", "g_sql_mode": "bulan", "g_sql_n": "6", "g_won_mode": "none", "g_won_n": "", "rule_count": "0"}


class FormParsingTests(unittest.TestCase):
    def test_a_filled_form_becomes_the_stored_shape(self):
        form = {**BASE, "g_won_mode": "bulan", "g_won_n": "12", "rule_count": "2",
                "r0_remark": "Trial", "r0_mql_mode": "default", "r0_sql_mode": "bulan", "r0_sql_n": "12", "r0_won_mode": "none",
                "r1_remark": "", "r1_mql_mode": "default", "r1_sql_mode": "default", "r1_won_mode": "default"}
        config, errors = validity.parse_form(form, ["Trial", "Junk Leads"])
        self.assertEqual(errors, {})
        self.assertEqual(config, {"defaults": {"MQL": None, "SQL": 6, "Deal Won": 12}, "remarks": [{"remark": "Trial", "MQL": "default", "SQL": 12, "Deal Won": None}]})

    def test_each_mistake_names_its_field(self):
        cases = {
            "g_sql_n": {**BASE, "g_sql_n": "0"},
            "g_mql_n": {**BASE, "g_mql_mode": "bulan", "g_mql_n": "abc"},
            "g_won_mode": {**BASE, "g_won_mode": "forever"},
            "r0_remark": {**BASE, "rule_count": "1", "r0_remark": "Tidak ada di daftar"},
            "r0_sql_n": {**BASE, "rule_count": "1", "r0_remark": "Trial", "r0_sql_mode": "bulan", "r0_sql_n": "61"},
            "r1_remark": {**BASE, "rule_count": "2", "r0_remark": "Trial", "r1_remark": " trial "},
            "_rules": {**BASE, "rule_count": "x"},
        }
        for field, form in cases.items():
            config, errors = validity.parse_form(form, ["Trial"])
            self.assertIsNone(config, field)
            self.assertIn(field, errors, field)

    def test_the_summary_says_what_the_report_will_say(self):
        config = {"defaults": {"MQL": None, "SQL": 6, "Deal Won": None}, "remarks": [{"remark": "Trial", "MQL": "default", "SQL": 12, "Deal Won": None}]}
        self.assertEqual(validity.summary(config), ["Acuan tanggal: Inbound Date.", "Umum: MQL tanpa batas; SQL 6 bulan; Deal Won tanpa batas.",
                                                    "Remark Trial: MQL ikut batas umum; SQL 12 bulan; Deal Won tanpa batas."])
        self.assertEqual(validity.parse_form(validity.form_values(config), ["Trial"])[0], config)  # the form values round-trip


class ValidityPageTests(ViewerCase):
    def setUp(self):
        super().setUp()
        self.login()
        self.store.remarks["bu1"] = ["Trial", "Junk Leads"]

    def page(self, query=""):
        response, body = self.call("GET", "/validity" + query)
        self.assertEqual(response.status, 200)
        return BeautifulSoup(body, "html.parser")

    def post(self, **fields):
        return self.call("POST", "/validity", {"csrf": self.csrf(), "bu": "bu1", **BASE, **fields})

    def test_without_a_saved_setting_the_profile_limit_is_shown_and_the_remarks_are_offered(self):
        soup = self.page()
        self.assertEqual(soup.select_one("select[name=g_sql_mode] option[selected]")["value"], "bulan")
        self.assertEqual(soup.select_one("input[name=g_sql_n]")["value"], "6")  # BU1's profile: SQL 6 months
        self.assertEqual(soup.select_one("select[name=g_mql_mode] option[selected]")["value"], "none")
        self.assertIn("batas bawaan dari profil", soup.get_text())
        template = soup.select_one("#vw-rule-tpl")
        self.assertEqual([o["value"] for o in BeautifulSoup(template.decode_contents(), "html.parser").select("select[name$=_remark] option")], ["", "Trial", "Junk Leads"])
        self.assertEqual(soup.select_one("input[name=rule_count]")["value"], "0")
        bu2 = self.page("?bu=bu2")
        self.assertEqual(bu2.select_one("select[name=g_sql_mode] option[selected]")["value"], "none")  # BU2's profile has no limit
        self.assertIn("Belum ada daftar Remark", bu2.get_text())

    def test_saving_keeps_every_version_shows_the_newest_and_the_history(self):
        response, _ = self.post(g_won_mode="bulan", g_won_n="12", rule_count="1", r0_remark="Trial", r0_mql_mode="default", r0_sql_mode="bulan", r0_sql_n="12", r0_won_mode="none")
        self.assertEqual((response.status, response.getheader("Location")), (303, "/validity?bu=bu1&saved=1"))
        saved = self.store.latest_validity("bu1")
        self.assertEqual(saved["config"], {"defaults": {"MQL": None, "SQL": 6, "Deal Won": 12}, "remarks": [{"remark": "Trial", "MQL": "default", "SQL": 12, "Deal Won": None}]})
        self.assertEqual(saved["saved_by"], "admin")
        soup = self.page("?saved=1")
        self.assertIn("tersimpan", soup.select_one(".vw-ok").get_text())
        self.assertEqual(soup.select_one("input[name=g_won_n]")["value"], "12")
        self.assertEqual(soup.select_one("select[name=r0_remark] option[selected]")["value"], "Trial")
        self.assertEqual(soup.select_one("input[name=r0_sql_n]")["value"], "12")
        self.assertIn("Remark Trial: MQL ikut batas umum; SQL 12 bulan; Deal Won tanpa batas.", soup.get_text())
        self.assertEqual(self.post(g_sql_n="9")[0].status, 303)
        self.assertEqual(len(self.store.validity), 2)  # every save is a new row
        self.assertEqual(len(self.page().select("section[aria-label='Riwayat perubahan'] tbody tr")), 2)

    def test_saving_the_same_thing_again_adds_nothing(self):
        self.post()
        response, _ = self.post()
        self.assertEqual(response.getheader("Location"), "/validity?bu=bu1&saved=same")
        self.assertEqual(len(self.store.validity), 1)

    def test_a_saved_rule_stays_selectable_even_when_its_remark_left_the_list(self):
        self.post(rule_count="1", r0_remark="Trial", r0_mql_mode="default", r0_sql_mode="default", r0_won_mode="default")
        self.store.remarks["bu1"] = ["Junk Leads"]
        soup = self.page()
        self.assertEqual([o["value"] for o in soup.select("[data-role=rules] select[name=r0_remark] option")], ["", "Junk Leads", "Trial"])
        self.assertEqual(soup.select_one("[data-role=rules] select[name=r0_remark] option[selected]")["value"], "Trial")

    def test_bad_input_is_refused_with_the_field_marked_and_the_typed_values_kept(self):
        response, body = self.post(g_sql_n="0", rule_count="1", r0_remark="Bukan remark", r0_mql_mode="default", r0_sql_mode="default", r0_won_mode="default")
        self.assertEqual(response.status, 422)
        soup = BeautifulSoup(body, "html.parser")
        self.assertIn("Belum ada yang disimpan", soup.select_one(".vw-alert").get_text())
        self.assertEqual(soup.select_one("input[name=g_sql_n]")["aria-invalid"], "true")
        self.assertEqual(soup.select_one("input[name=g_sql_n]")["value"], "0")
        self.assertEqual(self.store.validity, [])

    def test_a_failed_save_says_so_and_a_missing_database_is_a_503_page(self):
        self.store.fail_writes = True
        response, body = self.post(g_sql_n="9")
        self.assertEqual(response.status, 503)
        self.assertIn("tidak tersimpan", body)
        self.store.fail_writes = False
        self.store.down = True
        self.assertEqual(self.call("GET", "/validity")[0].status, 503)

    def test_unknown_companies_are_refused_and_only_admins_get_in(self):
        self.assertEqual(self.call("GET", "/validity?bu=bu9")[0].status, 404)
        self.assertEqual(self.post(bu="bu9")[0].status, 400)
        self.store.create_user("andi", auth.hash_password(USER_PASSWORD), "user", True, [], True)
        self.login(USER_PASSWORD, username="andi")
        self.assertEqual(self.call("GET", "/validity")[0].status, 403)
        self.assertEqual(self.post()[0].status, 403)
        self.assertNotIn("/validity", self.call("GET", "/")[1])  # the menu link is for admins
        self.assertEqual(self.store.validity, [])

    def test_the_menu_links_to_the_page_for_admins(self):
        self.assertIn('href="/validity"', self.call("GET", "/")[1])


if __name__ == "__main__":
    unittest.main()
