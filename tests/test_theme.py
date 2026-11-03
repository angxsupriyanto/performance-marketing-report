"""Dark mode: colours become variables on the way out, the palette and the switch are in every page, and the heat cells keep dark text."""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from test_viewer import ViewerCase  # noqa: E402
from viewer import performance_pages, theme  # noqa: E402


def contrast(a: str, b: str) -> float:
    def lum(h):
        r, g, bl = (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
        f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
        return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(bl)
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


class VariableTests(unittest.TestCase):
    def test_a_colour_becomes_the_variable_for_its_role(self):
        html = ('<style>a{color:#2159a9}.b{background:#2159a9;color:#fff}.c{background:#fff;border:1px solid #6f8199;outline:2px solid #2159a9}</style>'
                '<div style="color:#17283e;background: #ffffff">x</div><svg><line stroke="#dfe7f0"/></svg><p id="add">#add</p>')
        out = theme.to_variables(html)
        self.assertIn("a{color:var(--c-link)}", out)
        self.assertIn(".b{background:var(--c-primary);color:#fff}", out)  # white text on the blue button stays white
        self.assertIn(".c{background:var(--c-surface);border:1px solid var(--c-ctrl);outline:2px solid var(--c-focus)}", out)
        self.assertIn('style="color:var(--c-text);background: var(--c-surface)"', out)
        self.assertIn('stroke="var(--c-border)"', out)
        self.assertIn("#add", out)  # an id that only looks like a colour is left alone

    def test_the_light_values_are_the_colours_the_pages_always_used(self):
        light = {name: pair[0] for name, pair in theme.PALETTE.items()}
        self.assertEqual((light["text"], light["muted"], light["link"], light["surface"], light["bg"]), ("#17283e", "#607188", "#2159a9", "#ffffff", "#f4f7fb"))

    def test_dark_pairs_are_readable(self):
        dark = {name: pair[1] for name, pair in theme.PALETTE.items()}
        for fg, bg in (("text", "bg"), ("text", "surface"), ("text2", "surface"), ("muted", "surface"), ("muted", "bg"), ("link", "surface"), ("link", "bg"),
                       ("good", "good-bg"), ("bad", "bad-bg"), ("text2", "neu-bg"), ("text", "accent-bg")):
            self.assertGreaterEqual(contrast(dark[fg], dark[bg]), 4.5, f"{fg} on {bg}")
        self.assertGreaterEqual(contrast("#ffffff", dark["primary"]), 4.5)
        self.assertGreaterEqual(contrast(dark["ctrl"], dark["surface"]), 3.0)

    def test_the_heat_text_colour_is_not_themed_and_stays_dark_on_every_heat_colour(self):
        self.assertEqual(theme.to_variables(f"color:{performance_pages.HEAT_INK}"), f"color:{performance_pages.HEAT_INK}")
        from viewer.performance import HEAT
        for _, bg in HEAT:
            self.assertGreaterEqual(contrast(performance_pages.HEAT_INK, bg), 4.5, bg)


class ApplyTests(unittest.TestCase):
    def test_the_page_gets_the_palette_the_early_choice_and_the_switch_script(self):
        out = theme.apply("<html><head><title>x</title></head><body><p style=\"color:#17283e\">a</p></body></html>", "N0NCE")
        self.assertIn('<style nonce="N0NCE">', out)
        self.assertIn('<script nonce="N0NCE">', out)
        self.assertIn("prefers-color-scheme:dark", out)
        self.assertIn(':root[data-theme="dark"]', out)
        self.assertIn("@media print", out)
        self.assertLess(out.index("localStorage.getItem('vw-theme')"), out.index("<body>"))  # the saved choice applies before the first paint
        self.assertIn("var(--c-text)", out)

    def test_a_page_without_head_or_body_still_works(self):
        self.assertIn("--c-bg", theme.apply("<p>x</p>"))


class ServedPageTests(ViewerCase):
    def test_every_html_page_carries_the_palette_and_the_menu_has_the_switch_but_json_is_untouched(self):
        self.login()
        for path in ("/", "/performa", "/budget", "/targets", "/report/bu1/2026-W39"):
            response, body = self.call("GET", path)
            self.assertEqual(response.status, 200, path)
            self.assertIn("--c-surface", body, path)
            self.assertEqual(len(re.findall(r'<button [^>]*data-theme-set="', body)), 3, path)
        _, login = self.call("GET", "/login", cookie=False)
        self.assertIn("--c-bg", login)
        self.assertNotIn('data-theme-set="', login)  # no menu there: it follows the saved or system choice
        response, body = self.call("GET", "/api/analysis?bu=bu1&period=2026-W39")
        self.assertNotIn("--c-", body)

    def test_the_content_security_policy_still_allows_only_nonced_inline_code(self):
        self.login()
        response, body = self.call("GET", "/")
        nonce = re.search(r"script-src 'nonce-([^']+)'", response.getheader("Content-Security-Policy")).group(1)
        for tag in re.findall(r"<(?:script|style)\b[^>]*>", body):
            self.assertIn(f'nonce="{nonce}"', tag, tag)


if __name__ == "__main__":
    unittest.main()
