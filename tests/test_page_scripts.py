"""The scripts that pages carry must at least parse: a quoting slip in a Python string becomes a silent browser error, and the markup tests cannot see it."""
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from viewer import pages  # noqa: E402

ADMIN = {"role": "admin", "username": "admin", "all_companies": True, "companies": []}


@unittest.skipUnless(shutil.which("node"), "needs node")
class PageScriptTests(unittest.TestCase):
    def check(self, name: str, source: str) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / f"{name}.js"
            path.write_text(source, encoding="utf-8")
            result = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, f"{name}: {result.stderr[:400]}")

    def scripts_of(self, html: str) -> list[str]:
        return re.findall(r'<script nonce="n">(.*?)</script>', html, re.S)

    def test_the_shared_report_scripts_parse(self):
        self.check("analysis", pages.ANALYSIS_JS)
        self.check("manual", pages.MANUAL_JS)

    def test_the_validity_page_script_parses_and_finds_its_form(self):
        html = pages.validity_page("bu1", {"bu1": "A"}, {"rule_count": "0"}, ["Trial"], ["x"], [], {}, "c", "n", ADMIN)
        scripts = self.scripts_of(html)
        self.assertTrue(scripts)
        for number, source in enumerate(scripts):
            self.check(f"validity{number}", source)
        selector = re.search(r'document\.querySelector\("(form[^"]*)"\)', scripts[-1]).group(1)
        self.assertEqual(selector, "form.vw-validity-form")
        self.assertIn('class="vw-validity-form"', html)  # the script's selector matches the markup

    def test_the_refresh_page_script_parses(self):
        html = pages.refresh_page({"bu1": "A"}, {"week": [("2026-W44", "Week 44 2026")], "month": [("2026-10", "Oktober 2026")]}, {"report": None, "performa": None}, [],
                                  {"report": True, "performa": True}, "c", "n", ADMIN)
        for number, source in enumerate(self.scripts_of(html)):
            self.check(f"refresh{number}", source)


if __name__ == "__main__":
    unittest.main()
