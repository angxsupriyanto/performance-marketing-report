#!/usr/bin/env python3
"""Web viewer for stored reports: password login, report list, report page, analysis button, target settings.

Reads and writes only the marketing_reports database (role report_viewer) and calls the n8n analysis webhook.
It never reads the Google Sheet and never calls an AI model itself.
"""
from __future__ import annotations

import hmac
import html
import json
import os
import re
import secrets
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import generate_report  # noqa: E402
import report_view  # noqa: E402
from service.secretfile import read_secret  # noqa: E402
from viewer import auth, pages, targets  # noqa: E402
from viewer.store import Store, facts_of  # noqa: E402

BU = re.compile(r"[a-z0-9_]{1,32}")
PERIOD = re.compile(r"\d{4}-(?:W\d{2}|\d{2})")
MAX_FORM_BYTES = 64 * 1024
COOKIE = "vw_session"
UNITS = {"bu1": "idr", "bu2": "count"}
NOTICES = {"year": "Target semester dan 1 tahun {label} tersimpan.", "month": "Target bulanan {label} tersimpan.", "same": "Tidak ada perubahan yang perlu disimpan."}
ANALYSIS_TIMEOUT_SECONDS = int(os.environ.get("VIEWER_ANALYSIS_TIMEOUT", 420))


class HttpError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


@dataclass
class Config:
    password_hash: str
    session_secret: bytes
    store: Store
    n8n_url: str
    n8n_header: str
    n8n_prefix: str
    n8n_token: str
    secure_cookie: bool
    trust_proxy: bool

    @classmethod
    def from_env(cls) -> "Config":
        def secret(name: str) -> str:
            path = os.environ.get(f"{name}_FILE")
            if not path:
                raise SystemExit(f"{name}_FILE wajib diisi (Docker secret)")
            try:
                return read_secret(path, min_length=1)
            except (OSError, ValueError) as exc:
                raise SystemExit(f"{name}_FILE tidak bisa dipakai: {exc}")

        session_secret = secret("VIEWER_SESSION_SECRET")
        if len(session_secret) < 32:
            raise SystemExit("VIEWER_SESSION_SECRET minimal 32 karakter")
        password_hash = secret("VIEWER_PASSWORD_HASH")
        if not password_hash.startswith("scrypt$"):
            raise SystemExit("VIEWER_PASSWORD_HASH harus hasil python -m viewer.hash_password")
        n8n_token_file = os.environ.get("N8N_WEBHOOK_TOKEN_FILE")
        return cls(
            password_hash=password_hash,
            session_secret=session_secret.encode(),
            store=Store.from_env(lambda path: read_secret(path, min_length=1)),
            n8n_url=os.environ.get("N8N_ANALYSIS_URL", ""),
            n8n_header=os.environ.get("N8N_WEBHOOK_HEADER_NAME", "Authorization"),
            n8n_prefix=os.environ.get("N8N_WEBHOOK_HEADER_PREFIX", "Bearer "),
            n8n_token=read_secret(n8n_token_file, min_length=1) if n8n_token_file else "",
            secure_cookie=os.environ.get("VIEWER_COOKIE_SECURE", "true").lower() != "false",
            trust_proxy=os.environ.get("VIEWER_TRUST_PROXY_HEADERS", "false").lower() == "true",
        )


class Jobs:
    """Analysis runs started from this process. Lost on restart; the database stays the source of truth."""

    def __init__(self):
        self.items: dict[tuple[str, str], dict] = {}
        self.lock = threading.Lock()

    def get(self, key):
        with self.lock:
            item = self.items.get(key)
            return dict(item) if item else None

    def start(self, key) -> bool:
        with self.lock:
            if self.items.get(key, {}).get("state") == "running":
                return False
            self.items[key] = {"state": "running", "error": "", "started": time.time()}
            return True

    def finish(self, key, error: str = "") -> None:
        with self.lock:
            self.items[key] = {"state": "failed" if error else "done", "error": error, "started": self.items.get(key, {}).get("started", 0)}


def call_n8n(cfg: Config, bu: str, period: str, context: dict) -> str:
    """Returns an error text, or "" when n8n answered 2xx."""
    if not cfg.n8n_url or not cfg.n8n_token:
        return "Alamat atau token webhook n8n belum diatur pada layanan viewer."
    body = json.dumps({"bu": bu, "period": period, "requested_by": "viewer", "targets": context}, default=generate_report.json_default).encode()
    request = urllib.request.Request(cfg.n8n_url, data=body, method="POST", headers={"Content-Type": "application/json", cfg.n8n_header: cfg.n8n_prefix + cfg.n8n_token})
    try:
        with urllib.request.urlopen(request, timeout=ANALYSIS_TIMEOUT_SECONDS) as response:
            response.read()
        return ""
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            data = json.loads(exc.read().decode("utf-8", "replace"))
            detail = str(data.get("message") or data.get("error") or "")[:240]
        except (ValueError, AttributeError):
            pass
        return f"n8n menjawab {exc.code}" + (f": {detail}" if detail else "") + "."
    except (urllib.error.URLError, TimeoutError, OSError):
        return "n8n tidak menjawab dalam batas waktu."


def run_analysis(cfg: Config, jobs: Jobs, bu: str, period: str, context: dict) -> None:
    key = (bu, period)
    try:
        before = cfg.store.latest_analysis_time(bu, period)
        error = call_n8n(cfg, bu, period, context)
        if not error:
            after = cfg.store.latest_analysis_time(bu, period)
            if after is None or (before is not None and after <= before):
                error = "Workflow selesai tetapi analisis baru tidak tersimpan di database."
        jobs.finish(key, error)
    except Exception:  # noqa: BLE001 - the job must always leave the running state
        jobs.finish(key, "Terjadi kesalahan saat memproses analisis.")


def month_options(today: datetime) -> list[tuple[str, str]]:
    names = ("Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember")
    index = today.year * 12 + today.month - 1
    out = []
    for offset in range(-1, 13):
        year, month = divmod(index + offset, 12)
        out.append((f"{year}-{month + 1:02d}", f"{names[month]} {year}"))
    return out


class Handler(BaseHTTPRequestHandler):
    server_version = "report-viewer"
    sys_version = ""
    cfg: Config
    jobs: Jobs
    limiter: auth.LoginLimiter

    def log_message(self, fmt, *args):  # never log URLs, form fields or bodies
        pass

    # ---- plumbing
    def now(self) -> datetime:
        return datetime.now(pages.WIB)

    def client(self) -> str:
        if self.cfg.trust_proxy:
            forwarded = self.headers.get("CF-Connecting-IP", "").strip()
            if forwarded:
                return forwarded[:64]
        return self.client_address[0]

    def session_csrf(self) -> str | None:
        jar = self.headers.get("Cookie", "")
        for part in jar.split(";"):
            name, _, value = part.strip().partition("=")
            if name == COOKIE:
                return auth.read_session(self.cfg.session_secret, value)
        return None

    def session_cookie_value(self) -> str:
        for part in self.headers.get("Cookie", "").split(";"):
            name, _, value = part.strip().partition("=")
            if name == COOKIE:
                return value
        return ""

    def send(self, status: int, body: str | bytes, content_type: str = "text/html; charset=utf-8", nonce: str = "", extra: dict | None = None) -> None:
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "same-origin")  # "no-referrer" makes browsers send Origin: null on form posts
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        if self.cfg.secure_cookie:
            self.send_header("Strict-Transport-Security", "max-age=31536000")
        if nonce:
            self.send_header("Content-Security-Policy", (
                f"default-src 'none'; script-src 'nonce-{nonce}'; style-src 'nonce-{nonce}' https://fonts.googleapis.com; style-src-attr 'unsafe-inline'; "
                "font-src https://fonts.gstatic.com; img-src data:; connect-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"))
        for name, value in (extra or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(data)

    def json(self, status: int, payload: dict) -> None:
        self.send(status, json.dumps(payload, ensure_ascii=False), "application/json; charset=utf-8")

    def redirect(self, location: str, extra: dict | None = None) -> None:
        self.send(303, b"", extra={"Location": location, **(extra or {})})

    def cookie_header(self, value: str, max_age: int) -> str:
        flags = "HttpOnly; SameSite=Strict; Path=/" + ("; Secure" if self.cfg.secure_cookie else "")
        return f"{COOKIE}={value}; Max-Age={max_age}; {flags}"

    def read_form(self) -> dict[str, str]:
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            raise HttpError(411, "Content-Length wajib ada")
        if length < 0 or length > MAX_FORM_BYTES:
            raise HttpError(413, "isian terlalu besar")
        raw = self.rfile.read(length)
        if "json" in self.headers.get("Content-Type", ""):
            try:
                data = json.loads(raw.decode("utf-8"))
            except ValueError:
                raise HttpError(400, "JSON tidak valid")
            return {k: str(v) for k, v in data.items()} if isinstance(data, dict) else {}
        return {k: v[0] for k, v in parse_qs(raw.decode("utf-8", "replace"), keep_blank_values=True).items()}

    def same_origin(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return True
        host = urlparse(origin).netloc.lower()
        return host == (self.headers.get("X-Forwarded-Host") or self.headers.get("Host", "")).lower()

    # ---- routing
    def route(self, method: str) -> None:
        started = time.monotonic()
        status = 500
        path = urlparse(self.path).path
        nonce = secrets.token_urlsafe(16)
        try:
            if method == "GET" and path == "/healthz":
                status = 200
                return self.json(200, {"status": "ok", "database": self.cfg.store.ping()})
            csrf = self.session_csrf()
            query = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
            if method == "POST" and not self.same_origin():
                raise HttpError(403, "asal permintaan tidak cocok")
            if path == "/login":
                status = self.login(method, nonce)
                return
            if csrf is None:
                status = 303
                return self.redirect("/login")
            if method == "POST":
                form = self.read_form()
                supplied = self.headers.get("X-CSRF-Token") or form.get("csrf", "")
                if not hmac.compare_digest(supplied.encode(), csrf.encode()):
                    raise HttpError(403, "token sesi tidak valid; muat ulang halaman")
                if path == "/logout":
                    status = 303
                    return self.redirect("/login", {"Set-Cookie": self.cookie_header("", 0)})
                if path == "/api/analysis":
                    status = self.start_analysis(form)
                    return
                if path in ("/targets/year", "/targets/month"):
                    status = self.save_targets(path.rsplit("/", 1)[1], form, csrf, nonce)
                    return
            elif path == "/":
                status = self.list_page(csrf, nonce)
                return
            elif path.startswith("/report/"):
                status = self.report_page(path, csrf, nonce)
                return
            elif path == "/api/analysis/status":
                status = self.analysis_status(query)
                return
            elif path == "/targets":
                status = self.targets_page(query, csrf, nonce)
                return
            raise HttpError(404, "halaman tidak ditemukan")
        except HttpError as exc:
            status = exc.status
            if "application/json" in self.headers.get("Accept", "") or path.startswith("/api/"):
                self.json(exc.status, {"error": exc.message})
            else:
                body = f'<main class="vw-main"><h1 class="vw-h1">{exc.status}</h1><p>{html.escape(exc.message)}</p><a href="/">Kembali ke daftar report</a></main>'
                self.send(exc.status, pages.page("Tidak bisa diproses", body, nonce), nonce=nonce)
        except Exception:  # noqa: BLE001 - never leak internals
            status = 500
            try:
                self.json(500, {"error": "kesalahan internal"})
            except OSError:
                pass
        finally:
            print(f"{method} {path.split('/')[1] if path != '/' else '/'} -> {status} {time.monotonic() - started:.2f}s", flush=True)

    # ---- handlers
    def login(self, method: str, nonce: str) -> int:
        who = self.client()
        wait = self.limiter.retry_after(who)
        if method == "GET":
            self.send(200, pages.login(nonce, "Terlalu banyak percobaan. Coba lagi dalam 5 menit." if wait else "", bool(wait)), nonce=nonce)
            return 200
        form = self.read_form()
        if wait:
            self.send(429, pages.login(nonce, "Terlalu banyak percobaan. Coba lagi dalam 5 menit.", True), nonce=nonce, extra={"Retry-After": str(wait)})
            return 429
        if auth.verify_password(form.get("password", "")[:256], self.cfg.password_hash):
            self.limiter.succeeded(who)
            cookie, _ = auth.new_session(self.cfg.session_secret)
            self.redirect("/", {"Set-Cookie": self.cookie_header(cookie, auth.SESSION_SECONDS)})
            return 303
        self.limiter.failed(who)
        locked = bool(self.limiter.retry_after(who))
        self.send(401, pages.login(nonce, "Terlalu banyak percobaan. Coba lagi dalam 5 menit." if locked else "Password salah. Periksa lalu coba lagi.", locked), nonce=nonce)
        return 401

    def list_page(self, csrf: str, nonce: str) -> int:
        try:
            rows, error = self.cfg.store.list_reports(), ""
        except Exception:  # noqa: BLE001
            rows, error = [], "db"
        self.send(503 if error else 200, pages.report_list(rows, csrf, nonce, error), nonce=nonce)
        return 503 if error else 200

    def report_page(self, path: str, csrf: str, nonce: str) -> int:
        parts = path.split("/")
        if len(parts) != 4 or not BU.fullmatch(parts[2]) or not PERIOD.fullmatch(parts[3]):
            raise HttpError(404, "report tidak ditemukan")
        bu, period = parts[2], parts[3]
        try:
            report = self.cfg.store.get_report(bu, period)
        except Exception:  # noqa: BLE001
            raise HttpError(503, "database marketing_reports tidak menjawab; muat ulang halaman ini")
        if report is None:
            raise HttpError(404, "report tidak ditemukan")
        view = report_view.extract_view(report["html"])
        job = self.jobs.get((bu, period))
        state = pages.analysis_state(report["has_analysis"], job)
        chrome = pages.report_chrome(report, state, (job or {}).get("error", ""), csrf)
        if view is None:
            note = (
                '<main class="vw-main" style="padding-top:0"><div class="vw-box vw-pad" role="alert"><div class="vw-h2">Report ini dibuat oleh generator versi lama</div>'
                '<p style="margin:0">Isinya tidak mengikuti tampilan baru. Jalankan Report Generate lagi untuk periode ini, lalu muat ulang halaman.</p></div></main>'
            )
            self.send(200, pages.inject_chrome(f"<!doctype html><html><head><title>{html.escape(period)}</title></head><body>{note}</body></html>", chrome, nonce, csrf), nonce=nonce)
            return 200
        try:
            rows = self.cfg.store.latest_targets(bu)
        except Exception:  # noqa: BLE001
            rows = None
        analysis = report["analysis"] if isinstance(report.get("analysis"), dict) else None
        document = report_view.render_document(view, targets.build_tg(view, rows), analysis, standalone=False)
        self.send(200, pages.inject_chrome(document, chrome, nonce, csrf), nonce=nonce)
        return 200

    def start_analysis(self, form: dict) -> int:
        bu, period = form.get("bu", ""), form.get("period", "")
        if not BU.fullmatch(bu) or not PERIOD.fullmatch(period):
            raise HttpError(400, "bu atau period tidak valid")
        report = self.cfg.store.get_report(bu, period)
        if report is None:
            raise HttpError(404, "belum ada report numerik; jalankan Report Generate di n8n dahulu")
        if not self.jobs.start((bu, period)):
            raise HttpError(409, "analisis untuk report ini sedang berjalan")
        context = targets.context_for_analysis(facts_of(report), self.cfg.store.latest_targets(bu))
        threading.Thread(target=run_analysis, args=(self.cfg, self.jobs, bu, period, context), daemon=True).start()
        self.json(202, {"state": "running"})
        return 202

    def analysis_status(self, query: dict) -> int:
        bu, period = query.get("bu", ""), query.get("period", "")
        if not BU.fullmatch(bu) or not PERIOD.fullmatch(period):
            raise HttpError(400, "bu atau period tidak valid")
        job = self.jobs.get((bu, period))
        if job is None:
            self.json(200, {"state": "idle"})
        else:
            self.json(200, {"state": job["state"], "error": job["error"]})
        return 200

    def targets_context(self, bu: str, query: dict) -> dict:
        today = self.now()
        months = month_options(today)
        keys = [k for k, _ in months]
        month = query.get("month") if query.get("month") in keys else f"{today.year}-{today.month:02d}"
        years = [str(today.year), str(today.year + 1)]
        year = query.get("year") if query.get("year") in years else str(today.year)
        return {"months": months, "month": month, "years": years, "year": year}

    def render_targets(self, bu: str, ctx: dict, csrf: str, nonce: str, notice: str = "", failed: str = "", errors: dict | None = None, status: int = 200) -> int:
        store = self.cfg.store
        try:
            rows = store.latest_targets(bu)
            history = store.target_history(bu)
        except Exception:  # noqa: BLE001
            raise HttpError(503, "database marketing_reports tidak menjawab; muat ulang halaman ini")
        products = list(generate_report.load_profile(bu)["products"]) if UNITS[bu] == "idr" else []
        current = {p: targets.effective_hardware(rows, p, ctx["month"]) for p in products}
        semesters = {"S1": targets.semester_amount(rows, f"{ctx['year']}-S1"), "S2": targets.semester_amount(rows, f"{ctx['year']}-S2")}
        body = pages.targets_page(bu, UNITS[bu], products, ctx["months"], ctx["month"], current, ctx["year"], ctx["years"], semesters, history, csrf, nonce, notice, failed, errors)
        self.send(status, body, nonce=nonce)
        return status

    def targets_page(self, query: dict, csrf: str, nonce: str) -> int:
        bu = query.get("bu", "bu1")
        if bu not in UNITS:
            raise HttpError(404, "BU tidak dikenal")
        notice = NOTICES.get(query.get("saved", ""), "").format(label=bu.upper())
        return self.render_targets(bu, self.targets_context(bu, query), csrf, nonce, notice)

    def save_targets(self, kind: str, form: dict, csrf: str, nonce: str) -> int:
        bu = form.get("bu", "")
        if bu not in UNITS:
            raise HttpError(400, "BU tidak dikenal")
        unit = UNITS[bu]
        ctx = self.targets_context(bu, {"month": form.get("month", ""), "year": form.get("year", "")})
        errors: dict = {"_form": kind}
        entries: list[tuple] = []
        rows = self.cfg.store.latest_targets(bu)
        if kind == "year":
            for sem, field in (("S1", "sem1"), ("S2", "sem2")):
                try:
                    value = targets.parse_amount(form.get(field, ""), unit)
                except ValueError as exc:
                    errors[field], errors[f"_v_{field}"] = str(exc).capitalize(), form.get(field, "")
                    continue
                current = targets.semester_amount(rows, f"{ctx['year']}-{sem}")
                if value is not None and value != (current or Decimal(0)):
                    entries.append(("semester", None, f"{ctx['year']}-{sem}", unit, value))
        else:
            if unit != "idr":
                raise HttpError(400, "BU ini tidak memakai target bulanan")
            if form.get("month") != ctx["month"]:
                raise HttpError(400, "bulan tidak valid")
            for i, name in enumerate(generate_report.load_profile(bu)["products"]):
                field = f"hw_{i}"
                try:
                    value = targets.parse_amount(form.get(field, ""), unit)
                except ValueError as exc:
                    errors[field], errors[f"_v_{field}"] = str(exc).capitalize(), form.get(field, "")
                    continue
                current = targets.effective_hardware(rows, name, ctx["month"])
                if value is not None and value != (current or Decimal(0)):
                    entries.append(("hardware_month", name, ctx["month"], unit, value))
        if len(errors) > 1:
            return self.render_targets(bu, ctx, csrf, nonce, failed="Periksa isian yang ditandai. Belum ada yang disimpan.", errors=errors, status=422)
        if entries:
            try:
                self.cfg.store.add_targets(bu, entries)
            except Exception:  # noqa: BLE001
                errors["_form"] = kind
                return self.render_targets(bu, ctx, csrf, nonce, failed="Target tidak tersimpan. Database marketing_reports tidak menjawab. Coba simpan lagi.", errors=errors, status=503)
        saved = kind if entries else "same"
        self.redirect(f"/targets?bu={bu}&year={ctx['year']}&month={ctx['month']}&saved={saved}")
        return 303

    def do_GET(self):
        self.route("GET")

    def do_POST(self):
        self.route("POST")


def make_server(cfg: Config, host: str = "0.0.0.0", port: int = 8090) -> ThreadingHTTPServer:
    handler = type("BoundHandler", (Handler,), {"cfg": cfg, "jobs": Jobs(), "limiter": auth.LoginLimiter()})
    return ThreadingHTTPServer((host, port), handler)


if __name__ == "__main__":
    config = Config.from_env()
    server = make_server(config, port=int(os.environ.get("PORT", 8090)))
    print(f"report-viewer listening on :{server.server_address[1]}", flush=True)
    server.serve_forever()
