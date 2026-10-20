#!/usr/bin/env python3
"""Self-test for a running report service. Works inside the container with no shell quoting:

    docker exec report-service python -m service.selftest

It reads the token from the same secret file the service uses, never prints it, and builds one real report from
a tiny synthetic sample (no customer data), so it proves the whole path: auth, profiles, template, temp files.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

SAMPLE_COLUMNS = ["Company", "Channel", "Source", "Campaign", "Campaign Hardware", "Industry", "Remark", "Inbound Date", "MQL Date",
                  "Proposal Price Quote Date", "ARR + OTF (Tanpa PPN)", "Deal Won Date", "Total Contract Deal Won", "BU", "Record Key",
                  "SQL Date", "Total Contract SQL"]


def sample_csv() -> bytes:
    def row(**values):
        return {column: values.get(column, "") for column in SAMPLE_COLUMNS}
    rows = [
        row(Company="Contoh A", Channel="Paid", Source="Google Ads", Campaign="Contoh Ecosystem", **{"Campaign Hardware": "Ecosystem", "Industry": "Uji", "Inbound Date": "2026-09-22", "MQL Date": "2026-09-23", "BU": "BU2", "Record Key": "t1", "SQL Date": "2026-09-25", "Total Contract SQL": "5000000"}),
        row(Company="Contoh B", Channel="Paid", Source="Meta Ads", Campaign="Contoh GPS", **{"Campaign Hardware": "GPS", "Industry": "Uji", "Inbound Date": "2026-09-23", "BU": "BU2", "Record Key": "t2", "SQL Date": "2026-09-24", "Total Contract SQL": "3000000", "Deal Won Date": "2026-09-27", "Total Contract Deal Won": "2500000"}),
        row(Company="Contoh C", Channel="Organic", Source="Website", Campaign="Contoh Dashcam", **{"Campaign Hardware": "Dashcam", "Industry": "Uji", "Inbound Date": "2026-09-21", "BU": "BU1", "Record Key": "t3"}),
    ]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=SAMPLE_COLUMNS)
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def call(base: str, path: str, body: bytes | None = None, token: str | None = None):
    request = urllib.request.Request(base + path, data=body, method="POST" if body is not None else "GET")
    if token is not None:
        request.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8")
    except OSError as error:
        return 0, str(error)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=f"http://127.0.0.1:{os.environ.get('PORT', '8080')}")
    parser.add_argument("--token-file", default=os.environ.get("REPORT_SERVICE_TOKEN_FILE", "/run/secrets/report_service_token"))
    args = parser.parse_args()

    failures = 0

    def report(ok: bool, message: str) -> None:
        nonlocal failures
        print(("PASS: " if ok else "FAIL: ") + message)
        failures += 0 if ok else 1

    try:
        token = Path(args.token_file).read_text(encoding="utf-8").strip()
    except OSError:
        print("FAIL: token file cannot be read")
        return 1

    status, body = call(args.url, "/healthz")
    report(status == 200 and "bu1" in body and "bu2" in body, "health endpoint answers and lists bu1 and bu2")
    report(call(args.url, "/v1/analysis/apply", b"{}")[0] == 401, "request without token is refused (401)")
    report(call(args.url, "/v1/analysis/apply", b"{}", "x" * 40)[0] == 401, "request with wrong token is refused (401)")
    report(call(args.url, "/v1/analysis/apply", b"{}", token)[0] in (400, 422), "the real token is accepted (rejected only for its empty body)")

    status, body = call(args.url, "/v1/reports?bu=bu2&period=2026-W39", sample_csv(), token)
    try:
        result = json.loads(body)
        ok = status == 200 and result["audit"]["metrics"]["now"]["SQL Value"] == 8000000 and "hardware_ecosystem" in result["analysis_keys"] and len(result["html"]) > 1000
    except (ValueError, KeyError, TypeError):
        ok = False
    report(ok, "a BU2 report is generated from the synthetic sample with the expected numbers (SQL Value 8000000, Ecosystem slot present)")
    print("ALL CHECKS PASSED" if failures == 0 else f"{failures} CHECK(S) FAILED")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
