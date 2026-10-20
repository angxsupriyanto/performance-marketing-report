import json
import sys
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from service import server  # noqa: E402
from test_table_mode import HEADERS, LEADS  # noqa: E402

TOKEN = "t" * 32


def csv_text(rows):
    import csv
    import io
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=HEADERS)
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


class ServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = server.make_server(TOKEN, "127.0.0.1", 0)
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def call(self, path, body=None, token=TOKEN, method=None):
        request = urllib.request.Request(self.base + path, data=body, method=method or ("POST" if body is not None else "GET"))
        if token:
            request.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def test_health_is_open_but_everything_else_needs_the_token(self):
        status, body = self.call("/healthz")
        self.assertEqual((status, body["status"]), (200, "ok"))
        self.assertIn("bu2", body["profiles"])
        self.assertEqual(self.call("/v1/reports?bu=bu1&period=2026-W39", b"x", token=None)[0], 401)
        self.assertEqual(self.call("/v1/reports?bu=bu1&period=2026-W39", b"x", token="wrong" * 8)[0], 401)

    def test_report_roundtrip_returns_html_audit_facts_and_keys(self):
        status, body = self.call("/v1/reports?bu=bu2&period=2026-W39", csv_text(LEADS))
        self.assertEqual(status, 200, body)
        self.assertEqual(body["audit"]["metrics"]["now"]["SQL Value"], 8000000)
        self.assertIn("hardware_ecosystem", body["analysis_keys"])
        self.assertEqual(len(body["source_sha256"]), 64)
        self.assertNotIn("Co3", json.dumps(body["facts"]))
        status, applied = self.call("/v1/analysis/apply", json.dumps({"report_html": body["html"], "analysis": {"executive_summary": "SQL naik."}}).encode())
        self.assertEqual(status, 200, applied)
        self.assertIn("SQL naik.", applied["html"])

    def test_bad_requests_are_rejected_with_clear_errors(self):
        self.assertEqual(self.call("/v1/reports?bu=bu9&period=2026-W39", csv_text(LEADS))[0], 400)
        self.assertEqual(self.call("/v1/reports?bu=bu1&period=minggu-ini", csv_text(LEADS))[0], 400)
        status, body = self.call("/v1/reports?bu=bu1&period=2026-W39", b"a,b\n1,2\n")
        self.assertEqual(status, 422)
        self.assertIn("kolom wajib", body["error"])
        status, body = self.call("/v1/analysis/apply", json.dumps({"report_html": "<html></html>", "analysis": {"nope": "x"}}).encode())
        self.assertIn(status, (400, 422))
        self.assertEqual(self.call("/v1/unknown", b"{}")[0], 404)

    def test_oversize_body_is_refused_before_reading(self):
        original = server.MAX_BODY_BYTES
        server.MAX_BODY_BYTES = 10
        try:
            self.assertEqual(self.call("/v1/reports?bu=bu1&period=2026-W39", b"x" * 100)[0], 413)
        finally:
            server.MAX_BODY_BYTES = original

    def test_token_is_required_to_start(self):
        import os
        for key in ("REPORT_SERVICE_TOKEN", "REPORT_SERVICE_TOKEN_FILE"):
            os.environ.pop(key, None)
        with self.assertRaises(SystemExit):
            server.load_token()


if __name__ == "__main__":
    unittest.main()
