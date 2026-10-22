"""The report page must contain what the approved mockup shows, and nothing else."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import report_view  # noqa: E402
from test_table_mode import LEADS, run, write_table  # noqa: E402

LEFTOVERS = ("Highlight", "Top Contributor", "Funnel Performance", "Pipeline Timing", "Breakdown per Stage", "Cross-stage", "Campaign Detail",
             "Junk", "Volume funnel", "Nilai funnel", "Pipeline Insight", "Cross-stage Insight", "Weekly dashboard",
             "Panjang bar hanya ilustrasi", "Di mockup", "digambar ulang")


def page(bu, period="2026-W39"):
    with tempfile.TemporaryDirectory() as tmp:
        table, out = Path(tmp) / "t.csv", Path(tmp) / "r.html"
        write_table(table, LEADS)
        assert run("--table", table, "--bu", bu, "--period", period, "--output", out).returncode == 0
        html = out.read_text()
    return html, BeautifulSoup(html, "html.parser")


def visible_tables(soup):
    """The cohort switch keeps a second copy of a table for the "same period" view; the mockup's tables are the default view."""
    return [t for t in soup.select("table") if not t.find_parent(attrs={"data-cohort-view": "same"})]


def headings(soup):
    return [h.get_text() for h in soup.select("h2, h3, h4")]


def headers(soup, caption):
    table = [t for t in soup.select("table") if caption in t.select_one("caption").get_text()][0]
    return [th.get_text() for th in table.select("thead th")]


class MockupConformanceTests(unittest.TestCase):
    def test_bu1_has_exactly_the_mockup_sections_in_the_mockup_order(self):
        html, soup = page("bu1")
        self.assertEqual(headings(soup), [
            "Report", "Progress target SQL Value 2026", "Daftar SQL Week 39", "Campaign Hardware", "Target SQL Value September 2026",
            "Funnel per hardware", "Dashcam", "GPS Tracker", "Fuel", "MDVR", "OBD"])
        self.assertEqual([c.select_one("div").get_text() for c in soup.select(".cards")[0].find_all("div", recursive=False)],
                         ["Submission", "MQL", "SQL", "SQL Value", "Deal Won", "Deal Won Value"])
        self.assertEqual([c.select_one("div").get_text() for c in soup.select(".cards")[1].find_all("div", recursive=False)],
                         ["Same-week MQL", "Same-week SQL", "Same-week SQL Value"])
        self.assertEqual(len(soup.select(".cards")), 2)
        cards = {c.select_one("div").get_text(): [d.get_text() for d in c.find_all("div", recursive=False)] for c in soup.select(".cards")[0].find_all("div", recursive=False)}
        for name in ("MQL", "SQL", "Deal Won"):  # the mockup's rate line; the formula caption was dropped on request
            lines = cards[name]
            self.assertEqual(len(lines), 4, name)
            self.assertRegex(lines[3], rf"^{name} Rate [0-9]+,[0-9]% · Week 38: ([0-9]+,[0-9]%|—)$")
            self.assertNotIn("÷", " ".join(lines))
        for name in ("Submission", "SQL Value", "Deal Won Value"):
            self.assertEqual(len(cards[name]), 3, name)  # no rate line on the others
        for text in LEFTOVERS:
            self.assertNotIn(text, html, text)

    def test_bu1_tables_have_exactly_the_mockup_columns(self):
        _, soup = page("bu1")
        self.assertEqual(headers(soup, "Daftar SQL Week 39"), ["Company", "Industry", "Campaign", "SQL Value", "Inbound ke SQL"])
        self.assertEqual(headers(soup, "Campaign Hardware"), ["Produk", "Submission", "MQL", "SQL", "SQL Value", "Target", "Progress"])
        self.assertEqual(len(visible_tables(soup)), 2)
        self.assertEqual([td.get_text() for td in visible_tables(soup)[1].select("tfoot td")][0], "TOTAL 5 PRODUK")

    def test_bu2_has_exactly_the_mockup_sections_in_the_mockup_order(self):
        html, soup = page("bu2")
        self.assertEqual(headings(soup), ["Report", "Progress target SQL Ecosystem 2026", "Daftar SQL Ecosystem Week 39", "Daftar SQL Week 39", "Daftar Deal Won Week 39"])
        self.assertEqual(headers(soup, "Daftar SQL Ecosystem"), ["Company", "Industry", "Tanggal SQL", "SQL Value"])
        self.assertEqual(headers(soup, "Daftar SQL Week 39"), ["Company", "Industry", "Campaign", "SQL Value", "Inbound ke SQL"])
        self.assertEqual(headers(soup, "Daftar Deal Won"), ["Company", "Industry", "Campaign", "Deal Value", "Inbound ke Deal Won"])
        self.assertEqual([p["data-analysis"] for p in soup.select("[data-analysis]")], ["executive_summary"])
        self.assertNotIn("Campaign Hardware", html)
        for text in LEFTOVERS:
            self.assertNotIn(text, html, text)
        self.assertIn("Untuk BU2, SQL ditentukan dari kolom SQL Date dan SQL Value dari kolom Total Contract SQL.", html)

    def test_header_and_card_texts_follow_the_mockup(self):
        _, soup = page("bu1")
        text = soup.get_text(" ")
        self.assertIn("Performance Marketing Report", text)
        self.assertIn("Week 39 (21 sampai 27 Sep 2026) vs Week 38 (14 sampai 20 Sep 2026)", text)
        self.assertIn("Week 38: 0", text)
        self.assertIn("dari total", text)
        self.assertIn("Kosong sampai analisis dibuat.", text)
        self.assertIn("Target 2026 belum diatur. Atur di halaman Pengaturan target untuk melihat progress.", text)
        self.assertIn("Target September 2026 belum diatur. Atur target di halaman Pengaturan target untuk melihat progress.", text)
        self.assertIn("Lima produk hardware di Perusahaan 1. Produk lain dan tag kosong tidak dihitung.", text)
        self.assertIn("jumlah kelimanya", text)
        self.assertEqual([a["href"] for a in soup.select("a")], ["/targets", "/targets"])
        self.assertIn("Target Dashcam belum diatur.", text)

    def test_the_view_is_embedded_and_round_trips(self):
        html, _ = page("bu1")
        view = report_view.extract_view(html)
        self.assertEqual((view["v"], view["bu"], view["label"]), (1, "BU1", "Week 39"))
        self.assertEqual(report_view.render_document(view), html)
        self.assertIsNone(report_view.extract_view("<html>old report</html>"))
        self.assertEqual(view["analysis_keys"], report_view.analysis_keys(view))

    def test_html_in_data_is_escaped_everywhere(self):
        leads = [dict(r) for r in LEADS]
        leads[2]["Company"] = "<img src=x onerror=alert(1)>"
        leads[2]["Industry"] = "</script><b>"
        with tempfile.TemporaryDirectory() as tmp:
            table, out = Path(tmp) / "t.csv", Path(tmp) / "r.html"
            write_table(table, leads)
            self.assertEqual(run("--table", table, "--bu", "bu2", "--period", "2026-W39", "--output", out).returncode, 0)
            html = out.read_text()
        markup = html.split('<script type="application/json"')[0]  # the data block is inert; the visible page must be escaped
        self.assertNotIn("<img src=x", markup)
        self.assertNotIn("<b>", markup)
        self.assertEqual(html.count("</script>"), 2)  # the data block and the switch script; a company name cannot close the data block early
        self.assertEqual(html.split('<script type="application/json"')[1].split("</script>")[0].count("</"), 0)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", markup)
        view = report_view.extract_view(html)
        self.assertEqual(view["focus"]["rows"][0]["company"], "<img src=x onerror=alert(1)>")

    def test_targets_and_analysis_are_drawn_from_the_view_without_touching_numbers(self):
        html, _ = page("bu1")
        view = report_view.extract_view(html)
        tg = {"error": False, "semester": 12000000, "year": 20000000, "hardware": {"Dashcam": 3000000, "GPS Tracker": 4000000, "Fuel": None, "MDVR": None, "OBD": None}}
        analysis = {"executive_summary": "SQL <b>naik</b>", "hardware_gps_tracker": "GPS bagus"}
        soup = BeautifulSoup(report_view.render_document(view, tg, analysis), "html.parser")
        text = soup.get_text(" ")
        self.assertIn("Tercapai Rp 1.000.000 dari target Rp 12.000.000", text)
        self.assertIn("8,3% dari target semester", text)
        self.assertIn("5,0% dari target tahun", text)
        self.assertIn("Total target September 2026", text)
        self.assertIn("Rp 7.000.000", text)
        self.assertIn("SQL &lt;b&gt;naik&lt;/b&gt;".replace("&lt;", "<").replace("&gt;", ">"), text)
        self.assertEqual(soup.select_one('[data-analysis="executive_summary"]').get("style"), None)
        self.assertEqual(soup.select_one('[data-analysis="hardware_dashcam"]').get_text(), "Kosong sampai analisis dibuat.")
        rows = visible_tables(soup)[1].select("tbody tr")
        self.assertEqual([c.get_text() for c in rows[1].select("td")][4:], ["Rp 1.000.000", "Rp 4.000.000", "25,0%"])
        self.assertEqual([c.get_text() for c in rows[2].select("td")][5:], ["Belum diatur", "-"])
        broken = BeautifulSoup(report_view.render_document(view, {"error": True, "semester": None, "year": None, "hardware": {}}), "html.parser")
        self.assertEqual(len(broken.select('[role="alert"]')), 2)
        self.assertIn("Target tidak bisa dimuat. Database marketing_reports tidak menjawab. Muat ulang halaman ini.", broken.get_text())


if __name__ == "__main__":
    unittest.main()
