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

    def test_verify_script_passes_with_the_right_token_and_fails_with_a_wrong_one(self):
        import shutil
        import subprocess
        import tempfile
        if not shutil.which("sh"):
            self.skipTest("sh not available")
        script = str(ROOT / "deploy" / "verify-report-service.sh")
        with tempfile.TemporaryDirectory() as tmp:
            good, bad = Path(tmp) / "good", Path(tmp) / "bad"
            good.write_text(TOKEN)
            bad.write_text("x" * 40)
            run = lambda token_file: subprocess.run(["sh", script, "--url", self.base, "--token-file", str(token_file)], capture_output=True, text=True, timeout=60)
            ok, nope = run(good), run(bad)
        self.assertEqual(ok.returncode, 0, ok.stdout)
        self.assertIn("ALL CHECKS PASSED", ok.stdout)
        self.assertEqual(nope.returncode, 1)
        self.assertIn("FAIL: the real token is accepted", nope.stdout)
        self.assertNotIn(TOKEN, ok.stdout + ok.stderr + nope.stdout)

    def test_selftest_module_covers_auth_and_a_real_report(self):
        import subprocess
        import tempfile
        from service import selftest
        with tempfile.TemporaryDirectory() as tmp:
            token = Path(tmp) / "token"
            token.write_text(TOKEN)
            result = subprocess.run([sys.executable, "-m", "service.selftest", "--url", self.base, "--token-file", str(token)], capture_output=True, text=True, cwd=ROOT, timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.count("PASS:"), 5)
        self.assertIn("ALL CHECKS PASSED", result.stdout)
        self.assertNotIn(TOKEN, result.stdout + result.stderr)
        sys.path.insert(0, str(ROOT / "n8n"))
        import build_workflows
        self.assertEqual(set(selftest.SAMPLE_COLUMNS), set(build_workflows.tracker_columns()[0]))

    def test_token_is_required_to_start(self):
        import os
        for key in ("REPORT_SERVICE_TOKEN", "REPORT_SERVICE_TOKEN_FILE"):
            os.environ.pop(key, None)
        with self.assertRaises(SystemExit):
            server.load_token()


if __name__ == "__main__":
    unittest.main()


class SecretFileTests(unittest.TestCase):
    """Token files written on Windows must give the same token a person copies into n8n."""

    CLEAN = "0123456789abcdef" * 4

    def write(self, data: bytes) -> str:
        import tempfile
        handle = tempfile.NamedTemporaryFile(delete=False)
        handle.write(data)
        handle.close()
        self.addCleanup(lambda: Path(handle.name).unlink(missing_ok=True))
        return handle.name

    def test_every_windows_encoding_yields_the_same_clean_token(self):
        from service.secretfile import read_secret
        variants = {
            "plain": self.CLEAN.encode(),
            "lf": (self.CLEAN + "\n").encode(),
            "crlf": (self.CLEAN + "\r\n").encode(),
            "utf8-bom": b"\xef\xbb\xbf" + self.CLEAN.encode() + b"\r\n",
            "utf16-le-bom (PowerShell 5 '>')": "﻿".encode("utf-16-le") + (self.CLEAN + "\r\n").encode("utf-16-le"),
            "utf16-be-bom": b"\xfe\xff" + (self.CLEAN + "\n").encode("utf-16-be"),
        }
        for name, data in variants.items():
            self.assertEqual(read_secret(self.write(data)), self.CLEAN, name)

    def test_unusable_secrets_are_refused_without_echoing_them(self):
        from service.secretfile import read_secret
        for data in (b"short", ("a" * 30 + " " + "b" * 30).encode(), ("a" * 30 + "​").encode("utf-8"), ("a" * 30 + "\nb" * 5).encode(), b"\xff\xfe\x00"):
            with self.assertRaises(ValueError) as caught:
                read_secret(self.write(data))
            self.assertNotIn("a" * 30, str(caught.exception))

    def test_service_start_reads_a_bom_token_and_authenticates_with_the_clean_one(self):
        import os
        path = self.write(b"\xef\xbb\xbf" + self.CLEAN.encode() + b"\r\n")
        os.environ["REPORT_SERVICE_TOKEN_FILE"] = path
        self.addCleanup(lambda: os.environ.pop("REPORT_SERVICE_TOKEN_FILE", None))
        token = server.load_token()
        self.assertEqual(token, self.CLEAN)
        httpd = server.make_server(token, "127.0.0.1", 0)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.shutdown)
        request = urllib.request.Request(f"http://127.0.0.1:{httpd.server_address[1]}/v1/analysis/apply", data=b"{}", method="POST")
        request.add_header("Authorization", "Bearer " + self.CLEAN)
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=30)
        caught.exception.close()
        self.assertEqual(caught.exception.code, 400)

    def test_unusable_token_file_stops_the_service_from_starting(self):
        import os
        os.environ["REPORT_SERVICE_TOKEN_FILE"] = self.write(b"short")
        self.addCleanup(lambda: os.environ.pop("REPORT_SERVICE_TOKEN_FILE", None))
        with self.assertRaises(SystemExit):
            server.load_token()
