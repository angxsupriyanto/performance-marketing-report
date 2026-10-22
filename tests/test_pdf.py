"""Saving a report as PDF: the print version of the page, the Chromium wrapper, and the download endpoint."""
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from test_viewer import ViewerCase  # noqa: E402
from test_viewer_users import USER_PASSWORD  # noqa: E402
import report_view  # noqa: E402
from viewer import auth, pdf  # noqa: E402

CHROME = next((p for p in (os.environ.get("VIEWER_CHROMIUM"), "/opt/pw-browsers/chromium-1194/chrome-linux/chrome", shutil.which("chromium")) if p and Path(p).exists()), None)


def fake_browser(tmp: Path, body: str) -> str:
    path = tmp / "fake-chromium"
    path.write_text("#!/bin/sh\n" + body + "\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return str(path)


class WrapperTests(unittest.TestCase):
    def run_with(self, body: str):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"VIEWER_CHROMIUM": fake_browser(Path(tmp), body)}):
                return pdf.render_pdf("<p>x</p>")

    def test_the_page_is_printed_by_one_browser_process_with_no_network_and_no_header(self):
        record = tempfile.NamedTemporaryFile(delete=False)
        record.close()
        body = f'echo "$@" > {record.name}\nfor a in "$@"; do case "$a" in --print-to-pdf=*) printf "%%PDF-1.4 ok" > "${{a#--print-to-pdf=}}";; esac; done'
        self.assertEqual(self.run_with(body), b"%PDF-1.4 ok")
        args = Path(record.name).read_text()
        for flag in ("--headless", "--no-pdf-header-footer", "--host-resolver-rules=MAP * ~NOTFOUND", "--user-data-dir=", "file://"):
            self.assertIn(flag, args)
        os.unlink(record.name)

    def test_failures_become_messages_that_can_be_shown(self):
        with self.assertRaises(pdf.PdfError) as missing:
            with mock.patch.dict(os.environ, {"VIEWER_CHROMIUM": "/nonexistent/chromium"}):
                pdf.render_pdf("<p>x</p>")
        self.assertIn("Chromium tidak terpasang", str(missing.exception))
        with self.assertRaises(pdf.PdfError) as nothing:
            self.run_with("exit 1")  # the browser ran but wrote nothing
        self.assertIn("tidak berhasil", str(nothing.exception))
        with self.assertRaises(pdf.PdfError):
            self.run_with('for a in "$@"; do case "$a" in --print-to-pdf=*) printf "not a pdf" > "${a#--print-to-pdf=}";; esac; done')
        with mock.patch.object(pdf, "TIMEOUT_SECONDS", 1):
            with self.assertRaises(pdf.PdfError) as slow:
                self.run_with("sleep 5")
        self.assertIn("terlalu lama", str(slow.exception))

    def test_a_second_pdf_while_one_is_running_is_told_to_retry_and_the_gate_reopens_afterwards(self):
        self.assertTrue(pdf._gate.acquire(blocking=False))
        try:
            with self.assertRaises(pdf.PdfBusy):
                pdf.render_pdf("<p>x</p>")
        finally:
            pdf._gate.release()
        self.assertEqual(self.run_with('for a in "$@"; do case "$a" in --print-to-pdf=*) printf "%%PDF-1.4" > "${a#--print-to-pdf=}";; esac; done'), b"%PDF-1.4")

    def test_nothing_is_left_behind_in_the_temp_folder(self):
        before = {p.name for p in Path(tempfile.gettempdir()).glob("report-pdf-*")}
        self.run_with('for a in "$@"; do case "$a" in --print-to-pdf=*) printf "%%PDF-1.4" > "${a#--print-to-pdf=}";; esac; done')
        self.assertEqual({p.name for p in Path(tempfile.gettempdir()).glob("report-pdf-*")}, before)

    @unittest.skipUnless(CHROME, "no Chromium available")
    def test_a_real_browser_makes_a_real_pdf(self):
        with mock.patch.dict(os.environ, {"VIEWER_CHROMIUM": CHROME}):
            data = pdf.render_pdf("<!doctype html><meta charset=utf-8><h1>Laporan uji</h1><p>Rp 1.234.567</p>")
        self.assertTrue(data.startswith(b"%PDF"))
        if shutil.which("pdftotext"):
            with tempfile.NamedTemporaryFile(suffix=".pdf") as handle:
                handle.write(data)
                handle.flush()
                text = subprocess.run(["pdftotext", handle.name, "-"], capture_output=True, text=True).stdout
            self.assertIn("Laporan uji", text)
            self.assertIn("Rp 1.234.567", text)


class PrintDocumentTests(ViewerCase):
    def setUp(self):
        super().setUp()
        self.login()
        self.store.add_actions("bu1", "2026-W39", [{"action": "Naikkan bid <b>brand</b>", "campaign": "Camp A", "note": "+15%"}], "admin")
        self.store.analysis["bu1"] = {"executive_summary": "SQL naik."}

    def captured(self, path="/report/bu1/2026-W39/pdf", cookie=True):
        seen = {}

        def fake(html):
            seen["html"] = html
            return b"%PDF-1.4 fake"

        with mock.patch.object(pdf, "render_pdf", fake):
            response, body = self.call("GET", path, cookie=cookie)
        return response, body, seen.get("html")

    def test_the_download_has_the_pdf_headers_and_a_safe_file_name(self):
        response, body, _ = self.captured()
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Content-Type"), "application/pdf")
        self.assertEqual(response.getheader("Content-Disposition"), 'attachment; filename="report-Perusahaan-1-2026-W39.pdf"')
        self.assertEqual(response.getheader("Cache-Control"), "no-store")
        self.assertEqual(body, "%PDF-1.4 fake")

    def test_the_print_version_has_the_content_but_none_of_the_screen_only_controls(self):
        _, _, html = self.captured()
        soup = BeautifulSoup(html, "html.parser")
        self.assertIn("Perusahaan 1 · Week 39", soup.get_text())
        for gone in ("script", "button", "form", "[data-cohort-toggle]", "[data-editor]", "[data-role=controls]", 'a[href^="/"]', "[data-cohort-note]", "[data-cohort-view=same]"):
            self.assertEqual(soup.select(gone), [], gone)
        self.assertIsNone(soup.select_one("[hidden]"))
        text = soup.get_text(" ")
        self.assertIn("Next Action", text)
        self.assertIn("Action Week 39", text)
        self.assertIn("Naikkan bid <b>brand</b>", text)  # escaped, never markup
        self.assertNotIn("<b>brand</b>", html)
        self.assertIn("SQL naik.", text)
        self.assertNotIn("Edited", text)  # plain panels: no chips or provenance
        self.assertNotIn("Atur budget", text)
        self.assertNotIn("Ubah action", text)
        self.assertIn("@page", html)
        self.assertEqual(len(soup.select("[data-cohort-view=all]")), 2)  # the full-period lists stay

    def test_edited_text_is_what_prints(self):
        report = self.store.get_report("bu1", "2026-W39")
        self.call("POST", "/api/analysis/edit", {"bu": "bu1", "period": "2026-W39", "key": "next_action", "text": "Fokus ke GPS Tracker."}, {"X-CSRF-Token": self.csrf()})
        _, _, html = self.captured()
        self.assertIn("Fokus ke GPS Tracker.", BeautifulSoup(html, "html.parser").get_text(" "))

    def test_access_rules_are_the_same_as_the_page(self):
        self.assertEqual(self.captured(cookie=False)[0].status, 303)  # not signed in: to the login page
        self.assertEqual(self.captured("/report/bu1/2026-W39/pdf/extra")[0].status, 404)
        self.assertEqual(self.captured("/report/BU%201/2026-W39/pdf")[0].status, 404)
        self.assertEqual(self.captured("/report/bu1/2026-W99/pdf")[0].status, 404)
        self.store.create_user("andi", auth.hash_password(USER_PASSWORD), "user", False, ["bu2"], True)
        self.login(USER_PASSWORD, username="andi")
        self.assertEqual(self.captured("/report/bu1/2026-W39/pdf")[0].status, 403)
        self.assertEqual(self.captured("/report/bu2/2026-W39/pdf")[0].status, 200)

    def test_a_busy_or_broken_browser_gives_a_json_message_not_a_crash(self):
        with mock.patch.object(pdf, "render_pdf", side_effect=pdf.PdfBusy("PDF lain sedang dibuat.")):
            response, body = self.call("GET", "/report/bu1/2026-W39/pdf")
        self.assertEqual((response.status, json.loads(body)["error"]), (429, "PDF lain sedang dibuat."))
        with mock.patch.object(pdf, "render_pdf", side_effect=pdf.PdfError("PDF tidak berhasil dibuat. Coba lagi.")):
            response, body = self.call("GET", "/report/bu1/2026-W39/pdf")
        self.assertEqual((response.status, json.loads(body)["error"]), (503, "PDF tidak berhasil dibuat. Coba lagi."))

    def test_the_page_offers_the_button_to_everyone_with_access(self):
        soup = BeautifulSoup(self.call("GET", "/report/bu1/2026-W39")[1], "html.parser")
        button = soup.select_one("#vw-pdf")
        self.assertEqual((button.get_text(), button["data-href"]), ("Simpan sebagai PDF", "/report/bu1/2026-W39/pdf"))
        self.assertTrue(soup.select_one("#vw-pdf-msg").has_attr("hidden"))
        self.store.create_user("andi", auth.hash_password(USER_PASSWORD), "user", True, [], True)
        self.login(USER_PASSWORD, username="andi")
        self.assertIsNotNone(BeautifulSoup(self.call("GET", "/report/bu1/2026-W39")[1], "html.parser").select_one("#vw-pdf"))


class PrintCssTests(unittest.TestCase):
    def test_the_image_installs_chromium_unless_told_not_to(self):
        text = (ROOT / "Dockerfile").read_text()
        self.assertIn("ARG INSTALL_CHROMIUM=true", text)
        self.assertIn("apt-get install -y --no-install-recommends chromium", text)
        self.assertLess(text.index("chromium"), text.index("USER report"))  # installed as root, before the unprivileged user


if __name__ == "__main__":
    unittest.main()
