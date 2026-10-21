#!/usr/bin/env python3
"""Internal HTTP wrapper around generate_report.py and apply_analysis.py.

Stateless: nothing is stored and request bodies are never logged. Intended to be reachable only from the
n8n container over a private Docker network, with a bearer token read from a Docker secret.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import apply_analysis  # noqa: E402
import generate_report  # noqa: E402
from service.secretfile import read_secret  # noqa: E402

MAX_BODY_BYTES = int(os.environ.get("REPORT_MAX_BODY_BYTES", 32 * 1024 * 1024))
GENERATOR_TIMEOUT_SECONDS = int(os.environ.get("REPORT_GENERATOR_TIMEOUT", 180))
def _code_fingerprint() -> str:
    """Short hash of the files that decide a report's content. A report built by different code is a different run."""
    digest = hashlib.sha256()
    for path in [ROOT / "generate_report.py", ROOT / "apply_analysis.py", ROOT / "report_view.py", ROOT / "performa.py", *sorted((ROOT / "profiles").glob("*.json"))]:
        digest.update(path.name.encode() + b"\0" + path.read_bytes())
    return digest.hexdigest()[:8]


GENERATOR_VERSION = f"{os.environ.get('REPORT_GENERATOR_VERSION', 'dev')}+{_code_fingerprint()}"
PROFILE_NAME = re.compile(r"[a-z0-9_]{1,32}")
PERIOD = re.compile(r"\d{4}-(?:W\d{2}|\d{2})")
CONCURRENCY = threading.BoundedSemaphore(int(os.environ.get("REPORT_MAX_CONCURRENCY", 2)))


class HttpError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def load_token() -> str:
    path = os.environ.get("REPORT_SERVICE_TOKEN_FILE")
    try:
        if path:
            return read_secret(path)
        token = os.environ.get("REPORT_SERVICE_TOKEN", "").strip()
        if len(token) < 24 or not token.isascii() or not token.isprintable() or " " in token:
            raise ValueError("REPORT_SERVICE_TOKEN must be at least 24 printable ASCII characters without spaces")
        return token
    except (OSError, ValueError) as exc:
        raise SystemExit(f"layanan tidak dijalankan tanpa token yang valid: {exc}")


def generate(csv_bytes: bytes, bu: str, period: str, allow_duplicate_keys: bool) -> dict:
    if not PROFILE_NAME.fullmatch(bu):
        raise HttpError(400, "parameter bu tidak valid")
    if not PERIOD.fullmatch(period):
        raise HttpError(400, "parameter period harus YYYY-Www atau YYYY-MM")
    try:
        generate_report.load_profile(bu)
    except ValueError as exc:
        raise HttpError(400, str(exc))
    with tempfile.TemporaryDirectory(prefix="report-") as tmp:
        table = Path(tmp) / "table.csv"
        output = Path(tmp) / "report.html"
        table.write_bytes(csv_bytes)
        command = [sys.executable, str(ROOT / "generate_report.py"), "--table", str(table), "--bu", bu, "--period", period, "--output", str(output)]
        if allow_duplicate_keys:
            command.append("--allow-duplicate-keys")
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=GENERATOR_TIMEOUT_SECONDS, cwd=tmp)
        except subprocess.TimeoutExpired:
            raise HttpError(504, "pembuatan laporan melebihi batas waktu")
        if result.returncode != 0:
            message = (result.stderr or "").strip().splitlines()
            raise HttpError(422, (message[-1] if message else "pembuatan laporan gagal")[:2500])
        html = output.read_text(encoding="utf-8")
        audit = json.loads(output.with_suffix(".audit.json").read_text(encoding="utf-8"))
        facts = json.loads(output.with_suffix(".facts.json").read_text(encoding="utf-8"))
        lists = json.loads(output.with_suffix(".lists.json").read_text(encoding="utf-8"))
    return {
        "bu": bu,
        "period": audit["period"],
        "period_kind": audit["period_kind"],
        "period_start": audit["period_start"],
        "period_end": audit["period_end"],
        "source_sha256": hashlib.sha256(csv_bytes).hexdigest(),
        "generator_version": GENERATOR_VERSION,
        "html": html,
        "audit": audit,
        "facts": facts,
        "lists": lists,
        "analysis_keys": apply_analysis.analysis_keys(html),
    }


def performance(csv_bytes: bytes, bu: str, allow_duplicate_keys: bool) -> dict:
    """Aggregates for the Performa page: per-day counts and values and cohort counts. Aggregates only; the CSV is never stored."""
    if not PROFILE_NAME.fullmatch(bu):
        raise HttpError(400, "parameter bu tidak valid")
    try:
        generate_report.load_profile(bu)
    except ValueError as exc:
        raise HttpError(400, str(exc))
    with tempfile.TemporaryDirectory(prefix="performa-") as tmp:
        table, output = Path(tmp) / "table.csv", Path(tmp) / "performa.json"
        table.write_bytes(csv_bytes)
        command = [sys.executable, str(ROOT / "generate_report.py"), "--table", str(table), "--bu", bu, "--performa-json", str(output)]
        if allow_duplicate_keys:
            command.append("--allow-duplicate-keys")
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=GENERATOR_TIMEOUT_SECONDS, cwd=tmp)
        except subprocess.TimeoutExpired:
            raise HttpError(504, "perhitungan performa melebihi batas waktu")
        if result.returncode != 0:
            message = (result.stderr or "").strip().splitlines()
            raise HttpError(422, (message[-1] if message else "perhitungan performa gagal")[:2500])
        data = json.loads(output.read_text(encoding="utf-8"))
    audit = data.pop("audit")
    return {"bu": bu, "as_of": data["as_of"], "source_sha256": audit["source_sha256"], "generator_version": GENERATOR_VERSION,
            "rows_total": audit["rows_total"], "rows_in_bu": audit["rows_in_bu"], "days": len(data["days"]), "data": data}


def apply(body: bytes) -> dict:
    try:
        payload = json.loads(body.decode("utf-8"))
        html, analysis = payload["report_html"], payload["analysis"]
    except (ValueError, KeyError, TypeError):
        raise HttpError(400, "body harus JSON dengan report_html dan analysis")
    if not isinstance(html, str):
        raise HttpError(400, "report_html harus teks")
    try:
        return {"html": apply_analysis.apply_analysis(html, analysis)}
    except ValueError as exc:
        raise HttpError(422, str(exc))


class Handler(BaseHTTPRequestHandler):
    server_version = "report-service"
    sys_version = ""
    token = ""

    def log_message(self, fmt, *args):  # never log URLs with parameters or bodies
        pass

    def _send(self, status: int, payload: dict) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _authorized(self) -> bool:
        header = self.headers.get("Authorization", "")
        scheme, _, supplied = header.partition(" ")
        return scheme.lower() == "bearer" and hmac.compare_digest(supplied.strip().encode(), self.token.encode())

    def _read_body(self) -> bytes:
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            raise HttpError(411, "Content-Length wajib ada")
        if length < 0 or length > MAX_BODY_BYTES:
            raise HttpError(413, f"body melebihi {MAX_BODY_BYTES} byte")
        return self.rfile.read(length)

    def _route(self, method: str) -> None:
        started = time.monotonic()
        status = 500
        try:
            url = urlparse(self.path)
            if method == "GET" and url.path == "/healthz":
                status = 200
                return self._send(200, {"status": "ok", "profiles": sorted(p.stem for p in generate_report.PROFILE_DIR.glob("*.json")), "generator_version": GENERATOR_VERSION})
            if not self._authorized():
                status = 401
                return self._send(401, {"error": "unauthorized"})
            if method == "POST" and url.path in ("/v1/reports", "/v1/performa", "/v1/analysis/apply"):
                body = self._read_body()
                with CONCURRENCY:
                    if url.path in ("/v1/reports", "/v1/performa"):
                        query = parse_qs(url.query)
                        one = lambda key: (query.get(key) or [""])[0]
                        if url.path == "/v1/reports":
                            result = generate(body, one("bu").lower(), one("period"), one("allow_duplicate_keys") == "true")
                        else:
                            result = performance(body, one("bu").lower(), one("allow_duplicate_keys") == "true")
                    else:
                        result = apply(body)
                status = 200
                return self._send(200, result)
            status = 404
            self._send(404, {"error": "not found"})
        except HttpError as exc:
            status = exc.status
            self._send(exc.status, {"error": exc.message})
        except Exception:  # noqa: BLE001 - never leak internals or data
            status = 500
            self._send(500, {"error": "internal error"})
        finally:
            print(f"{method} {urlparse(self.path).path} -> {status} {time.monotonic() - started:.2f}s", flush=True)

    def do_GET(self):
        self._route("GET")

    def do_POST(self):
        self._route("POST")


def make_server(token: str, host: str = "0.0.0.0", port: int = 8080) -> ThreadingHTTPServer:
    handler = type("BoundHandler", (Handler,), {"token": token})
    return ThreadingHTTPServer((host, port), handler)


if __name__ == "__main__":
    server = make_server(load_token(), port=int(os.environ.get("PORT", 8080)))
    print(f"report-service listening on :{server.server_address[1]}", flush=True)
    server.serve_forever()
