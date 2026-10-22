import json
import sys
import unittest
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from test_viewer import PASSWORD, FakeN8n, ViewerCase  # noqa: E402
from viewer import auth  # noqa: E402

USER_PASSWORD = "another long password"


class UserCase(ViewerCase):
    def make_user(self, username, role="user", scope="pick", companies=("bu1",), active=True, password=USER_PASSWORD):
        self.store.ensure_bootstrap_admin(self.hash)
        self.store.create_user(username, auth.hash_password(password), role, scope == "all" or role == "admin", [] if scope == "all" or role == "admin" else list(companies), active)

    def as_user(self, username, password=USER_PASSWORD):
        response, _ = self.login(password, username=username)
        self.assertEqual(response.status, 303, username)

    def save_form(self, **overrides):
        form = {"csrf": self.csrf(), "mode": "new", "username": "andi", "password": USER_PASSWORD, "role": "user", "scope": "pick", "active": "1", "company": "bu1"}
        form.update(overrides)
        return self.call("POST", "/users/save", form)


class LoginTests(UserCase):
    def test_the_first_admin_comes_from_the_old_secret_and_only_while_there_are_no_users(self):
        self.assertEqual(self.store.users, {})
        self.login()
        self.assertEqual(list(self.store.users), ["admin"])
        self.assertEqual(self.store.users["admin"]["role"], "admin")
        self.assertIsNotNone(self.store.users["admin"]["last_login_at"])
        self.store.users["admin"]["password_hash"] = auth.hash_password("changed by the admin!!")
        response, _ = self.login(PASSWORD)  # the secret no longer logs in once a user row exists
        self.assertEqual(response.status, 401)

    def test_usernames_are_case_insensitive_and_unknown_or_wrong_look_the_same(self):
        self.make_user("andi")
        self.assertEqual(self.login(USER_PASSWORD, username="  Andi ")[0].status, 303)
        _, wrong_password = self.login("not the password!!", username="andi")
        _, unknown = self.login("not the password!!", username="nobody")
        alert = lambda body: BeautifulSoup(body, "html.parser").select_one("[role=alert]").get_text()
        self.assertEqual(alert(wrong_password), alert(unknown))
        self.assertIn("Username atau password salah", alert(unknown))

    def test_a_deactivated_account_gets_a_clear_message_and_no_lockout(self):
        self.make_user("lama", active=False)
        response, body = self.login(USER_PASSWORD, username="lama")
        self.assertEqual(response.status, 403)
        self.assertIn("Akun ini dinonaktifkan. Hubungi admin.", body)
        self.assertIsNone(response.getheader("Set-Cookie"))
        self.assertEqual(self.limiter.retry_after("10.0.0.1"), 0)

    def test_deactivating_or_changing_a_password_ends_existing_sessions_at_once(self):
        self.make_user("andi")
        self.as_user("andi")
        self.assertEqual(self.call("GET", "/")[0].status, 200)
        self.store.users["andi"]["password_hash"] = auth.hash_password("brand new password")
        self.assertEqual(self.call("GET", "/")[0].status, 303)
        self.store.users["andi"]["password_hash"] = auth.hash_password(USER_PASSWORD)
        self.as_user("andi")
        self.store.users["andi"]["active"] = False
        response, _ = self.call("GET", "/")
        self.assertEqual((response.status, response.getheader("Location")), (303, "/login"))
        self.assertIn("Max-Age=0", response.getheader("Set-Cookie"))

    def test_the_login_form_asks_for_username_and_password(self):
        _, body = self.call("GET", "/login", cookie=False)
        soup = BeautifulSoup(body, "html.parser")
        self.assertEqual([i["name"] for i in soup.select("form input")], ["username", "password"])
        self.assertEqual(self.call("POST", "/login", {"username": "admin"}, cookie=False)[0].status, 401)


class RoleTests(UserCase):
    def test_a_user_sees_only_the_companies_they_were_given(self):
        self.make_user("andi", companies=("bu1",))
        self.as_user("andi")
        soup = BeautifulSoup(self.call("GET", "/")[1], "html.parser")
        self.assertEqual([a["href"] for a in soup.select("tbody a")], ["/report/bu1/2026-W39"])
        self.assertEqual(self.call("GET", "/report/bu1/2026-W39")[0].status, 200)
        denied, body = self.call("GET", "/report/bu2/2026-W39")
        self.assertEqual(denied.status, 403)
        self.assertIn("Tidak ada akses", body)
        self.assertEqual(self.call("GET", "/api/analysis/status?bu=bu2&period=2026-W39")[0].status, 403)

    def test_a_user_with_all_companies_sees_every_report(self):
        self.make_user("semua", scope="all")
        self.as_user("semua")
        soup = BeautifulSoup(self.call("GET", "/")[1], "html.parser")
        self.assertEqual(len(soup.select("tbody a")), 2)

    def test_a_user_is_view_only_everywhere(self):
        self.make_user("andi", companies=("bu1",))
        self.as_user("andi")
        _, page = self.call("GET", "/report/bu1/2026-W39")
        soup = BeautifulSoup(page, "html.parser")
        box = soup.select_one("#vw-analysis")
        self.assertIsNone(box.select_one("button"))
        self.assertIn("Hanya admin yang bisa membuat atau membuat ulang analisis.", box.get_text())
        self.assertIsNone(soup.select_one("#vw-confirm"))
        self.assertEqual(soup.select("[data-act]"), [])  # no edit controls for a viewer
        self.assertEqual([a["href"] for a in soup.select(".vw-menu a")], ["/performa"])
        self.assertIn("andi (Pengguna)", soup.select_one(".vw-menu").get_text())
        for path in ("/targets", "/users", "/users/new", "/users/edit?u=admin", "/companies"):
            self.assertEqual(self.call("GET", path)[0].status, 403, path)
        csrf = self.csrf()
        for path, body in (("/api/analysis", {"bu": "bu1", "period": "2026-W39"}), ("/targets/year", {"bu": "bu1", "year": "2026", "sem1": "1"}),
                           ("/users/save", {"mode": "new", "username": "x" * 5, "password": USER_PASSWORD, "role": "admin"}), ("/companies", {"name_bu1": "X", "name_bu2": "Y"})):
            self.assertEqual(self.call("POST", path, {"csrf": csrf, **body})[0].status, 403, path)
        self.assertEqual((FakeN8n.calls, self.store.entries, list(self.store.users), self.store.names), ([], [], ["admin", "andi"], {}))

    def test_the_admin_menu_has_the_admin_pages(self):
        self.login()
        soup = BeautifulSoup(self.call("GET", "/")[1], "html.parser")
        self.assertEqual([a["href"] for a in soup.select(".vw-menu a")], ["/performa", "/users", "/targets", "/budget", "/companies"])
        self.assertIn("admin (Admin)", soup.select_one(".vw-menu").get_text())


class UserAdminTests(UserCase):
    def test_the_users_page_lists_everyone_with_role_access_and_status(self):
        self.make_user("andi", companies=("bu1",))
        self.make_user("semua", scope="all")
        self.make_user("lama", companies=("bu2",), active=False)
        self.login()
        soup = BeautifulSoup(self.call("GET", "/users")[1], "html.parser")
        rows = [[td.get_text(" ", strip=True) for td in tr.select("td")[:5]] for tr in soup.select("tbody tr")]
        self.assertEqual([r[0] for r in rows], ["admin", "andi", "lama", "semua"])
        self.assertEqual(rows[0][1:4], ["Admin", "Semua perusahaan", "Aktif"])
        self.assertEqual(rows[1][1:4], ["Pengguna", "Perusahaan 1", "Aktif"])
        self.assertEqual(rows[2][1:4], ["Pengguna", "Perusahaan 2", "Nonaktif"])
        self.assertEqual(rows[2][4], "Belum pernah masuk")
        self.assertEqual(rows[3][2], "Semua perusahaan")

    def test_an_admin_creates_a_user_who_can_then_log_in(self):
        self.login()
        response, _ = self.save_form(username="Budi_1", company="bu2")
        self.assertEqual(response.status, 303)
        self.assertEqual(response.getheader("Location"), "/users?saved=1&u=budi_1")
        row = self.store.users["budi_1"]
        self.assertEqual((row["role"], row["all_companies"], row["companies"], row["active"]), ("user", False, ["bu2"], True))
        self.assertTrue(auth.verify_password(USER_PASSWORD, row["password_hash"]))
        self.assertNotIn(USER_PASSWORD, json.dumps(row, default=str))
        self.assertIn("Pengguna budi_1 tersimpan.", self.call("GET", response.getheader("Location"))[1])
        self.assertEqual(self.login(USER_PASSWORD, username="budi_1")[0].status, 303)

    def test_new_user_input_is_checked_and_nothing_is_saved_on_error(self):
        self.login()
        for overrides, field in (({"username": "ab"}, "username"), ({"username": "Spasi Dalam"}, "username"), ({"password": "pendek"}, "password"),
                                 ({"scope": "pick", "company": "bu9"}, "scope")):
            response, body = self.save_form(**overrides)
            self.assertEqual(response.status, 422, overrides)
            self.assertIsNotNone(BeautifulSoup(body, "html.parser").select_one(f'[aria-invalid="true"]') or BeautifulSoup(body, "html.parser").select_one("[role=alert]"), field)
        self.assertEqual(list(self.store.users), ["admin"])
        _, body = self.save_form(password="pendek")
        self.assertIn("Password minimal 12 karakter", body)
        self.assertNotIn('value="pendek"', body)

    def test_a_duplicate_username_is_refused_with_the_mockup_text(self):
        self.make_user("andi")
        self.login()
        response, body = self.save_form(username="andi")
        self.assertEqual(response.status, 422)
        self.assertIn("Username ini sudah dipakai. Pilih yang lain.", body)

    def test_an_admin_edits_access_status_and_password_without_retyping_the_old_one(self):
        self.make_user("andi", companies=("bu1",))
        self.login()
        _, page = self.call("GET", "/users/edit?u=andi")
        soup = BeautifulSoup(page, "html.parser")
        self.assertEqual(soup.select_one("#username")["value"], "andi")
        self.assertIsNotNone(soup.select_one("#username").get("readonly"))
        self.assertEqual([c["value"] for c in soup.select("input[name=company][checked]")], ["bu1"])
        old_hash = self.store.users["andi"]["password_hash"]
        response, _ = self.save_form(mode="edit", username="andi", password="", scope="all", active="0")
        self.assertEqual(response.status, 303)
        row = self.store.users["andi"]
        self.assertEqual((row["all_companies"], row["companies"], row["active"], row["password_hash"]), (True, [], False, old_hash))
        self.save_form(mode="edit", username="andi", password="a completely new one", scope="pick", company="bu2", active="1")
        row = self.store.users["andi"]
        self.assertEqual((row["companies"], row["active"]), (["bu2"], True))
        self.assertTrue(auth.verify_password("a completely new one", row["password_hash"]))
        self.assertEqual(self.call("GET", "/users/edit?u=ghost")[0].status, 404)

    def test_admin_role_always_has_every_company_and_users_are_never_deleted(self):
        self.login()
        self.save_form(username="bos", role="admin", scope="pick", company="bu1")
        row = self.store.users["bos"]
        self.assertEqual((row["role"], row["all_companies"], row["companies"]), ("admin", True, []))
        self.assertEqual(self.call("POST", "/users/delete", {"csrf": self.csrf(), "u": "bos"})[0].status, 404)
        self.assertIn("bos", self.store.users)

    def test_the_last_active_admin_cannot_be_deactivated_or_demoted(self):
        self.login()
        for overrides in ({"active": "0"}, {"role": "user", "scope": "all"}):
            response, body = self.save_form(mode="edit", username="admin", password="", **overrides)
            self.assertEqual(response.status, 422, overrides)
            self.assertIn("ini satu-satunya admin aktif", body)
        self.assertTrue(self.store.users["admin"]["active"] and self.store.users["admin"]["role"] == "admin")
        self.save_form(username="bos", role="admin")  # with a second admin it is allowed
        self.assertEqual(self.save_form(mode="edit", username="bos", password="", role="admin", active="0")[0].status, 303)

    def test_a_database_failure_keeps_the_typed_values(self):
        self.login()
        original = self.store.create_user
        self.store.create_user = lambda *a: (_ for _ in ()).throw(RuntimeError("down"))
        response, body = self.save_form(username="andi")
        self.assertEqual(response.status, 503)
        self.assertIn("Pengguna tidak tersimpan. Database marketing_reports tidak menjawab. Coba simpan lagi.", body)
        self.assertEqual(BeautifulSoup(body, "html.parser").select_one("#username")["value"], "andi")
        self.store.create_user = original

    def test_the_users_page_survives_a_database_failure_with_a_message(self):
        self.login()
        self.store.down = True
        self.assertEqual(self.call("GET", "/users")[0].status, 503)


class CompanyNameTests(UserCase):
    def test_default_names_are_perusahaan_n_and_a_saved_name_shows_everywhere(self):
        self.login()
        soup = BeautifulSoup(self.call("GET", "/companies")[1], "html.parser")
        self.assertEqual([i["value"] for i in soup.select("form input[type=text]")], ["Perusahaan 1", "Perusahaan 2"])
        response, _ = self.call("POST", "/companies", {"csrf": self.csrf(), "name_bu1": "McEasy", "name_bu2": "  LOL  "})
        self.assertEqual((response.status, response.getheader("Location")), (303, "/companies?saved=1"))
        self.assertEqual(self.store.names, {"bu1": "McEasy", "bu2": "LOL"})
        self.assertIn("Nama perusahaan tersimpan. Berlaku di semua halaman.", self.call("GET", "/companies?saved=1")[1])
        listing = BeautifulSoup(self.call("GET", "/")[1], "html.parser")
        self.assertEqual([r.select("td")[1].get_text() for r in listing.select("tbody tr")], ["McEasy", "LOL"])
        report = BeautifulSoup(self.call("GET", "/report/bu1/2026-W39")[1], "html.parser")
        self.assertEqual(report.select_one("h1.vw-h1").get_text(), "Report McEasy")
        self.assertIn("McEasy Performance Marketing Report", report.select_one("title").get_text())
        self.assertIn("lima produk hardware di McEasy".lower(), report.get_text().lower())
        eco = BeautifulSoup(self.call("GET", "/report/bu2/2026-W39")[1], "html.parser").get_text()
        self.assertIn("Target LOL adalah jumlah SQL dari campaign Ecosystem (existing user McEasy)", eco)
        targets = BeautifulSoup(self.call("GET", "/targets?bu=bu2")[1], "html.parser")
        self.assertEqual([o.get_text() for o in targets.select("#bu option")], ["McEasy", "LOL"])
        self.assertEqual(self.call("GET", "/report/bu1/2026-W39?x=1")[0].status, 200)  # ids in links are untouched
        self.assertNotIn("BU1", report.get_text())

    def test_names_are_checked_and_must_differ_ignoring_case(self):
        self.login()
        for first, second, wrong in (("", "LOL", "bu1"), ("McEasy", "<b>x</b>", "bu2"), ("x" * 33, "LOL", "bu1"), ("Sama", "sama", "bu2")):
            response, body = self.call("POST", "/companies", {"csrf": self.csrf(), "name_bu1": first, "name_bu2": second})
            self.assertEqual(response.status, 422, (first, second))
            self.assertIsNotNone(BeautifulSoup(body, "html.parser").select_one(f'input[name=name_{wrong}][aria-invalid=true]'), (first, second))
            self.assertNotIn("<b>x</b>", body)
        self.assertEqual(self.store.names, {})

    def test_a_missing_name_table_does_not_take_the_reports_down(self):
        self.login()
        self.store.company_names = lambda: (_ for _ in ()).throw(RuntimeError("no such table"))
        _, body = self.call("GET", "/")
        self.assertIn("Perusahaan 1", body)

    def test_non_admins_see_the_new_names_but_cannot_change_them(self):
        self.make_user("andi", scope="all")
        self.store.names = {"bu1": "McEasy", "bu2": "LOL"}
        self.as_user("andi")
        soup = BeautifulSoup(self.call("GET", "/")[1], "html.parser")
        self.assertEqual([r.select("td")[1].get_text() for r in soup.select("tbody tr")], ["McEasy", "LOL"])
        self.assertEqual(self.call("GET", "/companies")[0].status, 403)


if __name__ == "__main__":
    unittest.main()
