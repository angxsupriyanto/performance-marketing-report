#!/usr/bin/env python3
"""Web viewer for stored reports: username login with admin and view-only roles, report list, report page, analysis button, target settings, user and company-name admin.

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
from viewer import access, actions, analysis_edits, auth, budget, pdf, pages, performance, performance_pages, targets  # noqa: E402
from viewer.store import Store, UserError, facts_of  # noqa: E402

BU = re.compile(r"[a-z0-9_]{1,32}")
PERIOD = re.compile(r"\d{4}-(?:W\d{2}|\d{2})")
MAX_FORM_BYTES = 64 * 1024
COOKIE = "vw_session"
UNITS = {"bu1": "idr", "bu2": "count"}
NOTICES = {"year": "Target semester dan 1 tahun {label} tersimpan.", "month": "Target bulanan {label} tersimpan.", "same": "Tidak ada perubahan yang perlu disimpan."}
USERNAME = re.compile(r"[a-z0-9._-]{3,32}")
DUMMY_HASH = auth.hash_password(secrets.token_urlsafe(18))  # checked when the username is unknown, so timing does not reveal which usernames exist
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
            n8n_prefix=normalize_prefix(os.environ.get("N8N_WEBHOOK_HEADER_PREFIX", "Bearer ")),
            n8n_token=read_secret(n8n_token_file, min_length=1) if n8n_token_file else "",
            secure_cookie=os.environ.get("VIEWER_COOKIE_SECURE", "true").lower() != "false",
            trust_proxy=os.environ.get("VIEWER_TRUST_PROXY_HEADERS", "false").lower() == "true",
        )


def normalize_prefix(prefix: str) -> str:
    """A scheme such as "Bearer" must be followed by exactly one space. YAML and shells often strip that trailing space,
    which sends "Bearer<token>" and makes n8n answer 403 even though the token is right. An empty prefix stays empty."""
    prefix = prefix.strip()
    return prefix + " " if prefix else ""


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


def call_n8n(cfg: Config, bu: str, period: str, context: dict, extra: dict | None = None) -> str:
    """Returns an error text, or "" when n8n answered 2xx. `extra` adds the team's actions and the budget figures to the request."""
    if not cfg.n8n_url or not cfg.n8n_token:
        return "Alamat atau token webhook n8n belum diatur pada layanan viewer."
    body = json.dumps({"bu": bu, "period": period, "requested_by": "viewer", "targets": context, **(extra or {})}, default=generate_report.json_default).encode()
    request = urllib.request.Request(cfg.n8n_url, data=body, method="POST", headers={"Content-Type": "application/json", cfg.n8n_header: cfg.n8n_prefix + cfg.n8n_token})
    try:
        with urllib.request.urlopen(request, timeout=ANALYSIS_TIMEOUT_SECONDS) as response:
            response.read()
        return ""
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        detail = ""
        try:
            data = json.loads(raw)
            detail = str(data.get("message") or data.get("error") or "")[:240]
        except (ValueError, AttributeError):
            pass
        if not detail:  # not JSON (a proxy page, plain text): show the start of it so the cause is visible
            detail = " ".join(raw.split())[:160]
        return f"n8n menjawab {exc.code}" + (f": {detail}" if detail else " dengan jawaban kosong") + "."
    except (urllib.error.URLError, TimeoutError, OSError):
        return "n8n tidak menjawab dalam batas waktu."


def run_analysis(cfg: Config, jobs: Jobs, bu: str, period: str, context: dict, extra: dict | None = None) -> None:
    key = (bu, period)
    try:
        before = cfg.store.latest_analysis_time(bu, period)
        error = call_n8n(cfg, bu, period, context, extra)
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
    form_lists: dict = {}
    query_lists: dict = {}
    user: dict = {}

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

    def session(self) -> tuple[str, str, str] | None:
        for part in self.headers.get("Cookie", "").split(";"):
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
        parsed = parse_qs(raw.decode("utf-8", "replace"), keep_blank_values=True)
        self.form_lists = parsed
        return {k: v[0] for k, v in parsed.items()}

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
            self.query_lists = parse_qs(urlparse(self.path).query)
            query = {k: v[0] for k, v in self.query_lists.items()}
            if method == "POST" and not self.same_origin():
                raise HttpError(403, "asal permintaan tidak cocok")
            if path == "/login":
                status = self.login(method, nonce)
                return
            session = self.session()
            try:
                user = self.load_user(session) if session else None
            except HttpError:
                if method == "GET" and path == "/" and session:  # keep the mockup's message for a list that cannot load
                    status = 503
                    return self.send(503, pages.report_list([], session[0], nonce, None, {}, "db"), nonce=nonce)
                raise
            if session is None or user is None:
                status = 303
                return self.redirect("/login", {"Set-Cookie": self.cookie_header("", 0)} if session else None)
            csrf, self.user = session[0], user
            if method == "POST":
                form = self.read_form()
                supplied = self.headers.get("X-CSRF-Token") or form.get("csrf", "")
                if not hmac.compare_digest(supplied.encode(), csrf.encode()):
                    raise HttpError(403, "token sesi tidak valid; muat ulang halaman")
                if path == "/logout":
                    status = 303
                    return self.redirect("/login", {"Set-Cookie": self.cookie_header("", 0)})
                if path == "/api/analysis":
                    self.need_admin()
                    status = self.start_analysis(form)
                    return
                if path == "/api/analysis/edit":
                    self.need_admin()
                    status = self.save_edit(form)
                    return
                if path == "/api/actions":
                    self.need_admin()
                    status = self.save_actions(form)
                    return
                if path in ("/targets/year", "/targets/month"):
                    self.need_admin()
                    status = self.save_targets(path.rsplit("/", 1)[1], form, csrf, nonce)
                    return
                if path == "/users/save":
                    self.need_admin()
                    status = self.save_user(form, csrf, nonce)
                    return
                if path == "/companies":
                    self.need_admin()
                    status = self.save_companies(form, csrf, nonce)
                    return
                if path == "/budget":
                    self.need_admin()
                    status = self.save_budget(form, csrf, nonce)
                    return
            elif path == "/":
                status = self.list_page(csrf, nonce)
                return
            elif path.startswith("/report/") and path.endswith("/pdf"):
                status = self.report_pdf(path)
                return
            elif path.startswith("/report/"):
                status = self.report_page(path, csrf, nonce)
                return
            elif path == "/api/analysis/status":
                status = self.analysis_status(query)
                return
            elif path == "/targets":
                self.need_admin()
                status = self.targets_page(query, csrf, nonce)
                return
            elif path in ("/users", "/users/new", "/users/edit"):
                self.need_admin()
                status = self.users_pages(path, query, csrf, nonce)
                return
            elif path == "/companies":
                self.need_admin()
                status = self.companies_page(query, csrf, nonce)
                return
            elif path == "/budget":
                self.need_admin()
                status = self.budget_page(query, csrf, nonce)
                return
            elif path == "/performa":
                status = self.performance_page(query, csrf, nonce)
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
    def load_user(self, session: tuple[str, str, str]) -> dict | None:
        """The signed session names a user; role, access and the active flag always come from the database."""
        try:
            user = self.cfg.store.get_user(session[1])
        except Exception:  # noqa: BLE001
            raise HttpError(503, "database marketing_reports tidak menjawab; muat ulang halaman ini")
        if user is None or not user["active"] or not hmac.compare_digest(session[2], auth.credential_tag(user["password_hash"])):
            return None
        return user

    def need_admin(self) -> None:
        if not access.is_admin(self.user):
            raise HttpError(403, "Halaman ini hanya untuk admin.")

    def names(self) -> dict[str, str]:
        try:
            return access.names_with_defaults(self.cfg.store.company_names())
        except Exception:  # noqa: BLE001 - a missing name table must not take the reports down
            return access.names_with_defaults(None)

    def login(self, method: str, nonce: str) -> int:
        who = self.client()
        wait = self.limiter.retry_after(who)
        locked_text = "Terlalu banyak percobaan. Coba lagi dalam 5 menit."
        if method == "GET":
            self.send(200, pages.login(nonce, locked_text if wait else "", bool(wait)), nonce=nonce)
            return 200
        form = self.read_form()
        if wait:
            self.send(429, pages.login(nonce, locked_text, True), nonce=nonce, extra={"Retry-After": str(wait)})
            return 429
        username = form.get("username", "").strip().lower()[:64]
        password = form.get("password", "")[:256]
        try:
            self.cfg.store.ensure_bootstrap_admin(self.cfg.password_hash)
            user = self.cfg.store.get_user(username) if USERNAME.fullmatch(username) else None
        except Exception:  # noqa: BLE001
            self.send(503, pages.login(nonce, "Database marketing_reports tidak menjawab. Coba lagi sebentar lagi."), nonce=nonce)
            return 503
        correct = auth.verify_password(password, user["password_hash"] if user else DUMMY_HASH) and user is not None
        if correct and user["active"]:
            self.limiter.succeeded(who)
            try:
                self.cfg.store.touch_login(user["username"])
            except Exception:  # noqa: BLE001 - the last-login time is informational
                pass
            cookie, _ = auth.new_session(self.cfg.session_secret, user["username"], auth.credential_tag(user["password_hash"]))
            self.redirect("/", {"Set-Cookie": self.cookie_header(cookie, auth.SESSION_SECONDS)})
            return 303
        if correct:  # right password for a deactivated account: no lockout, but say why
            self.send(403, pages.login(nonce, "Akun ini dinonaktifkan. Hubungi admin."), nonce=nonce)
            return 403
        self.limiter.failed(who)
        locked = bool(self.limiter.retry_after(who))
        self.send(401, pages.login(nonce, locked_text if locked else "Username atau password salah. Periksa lalu coba lagi.", locked), nonce=nonce)
        return 401

    def list_page(self, csrf: str, nonce: str) -> int:
        try:
            rows, error = [r for r in self.cfg.store.list_reports() if access.can_see(self.user, r["bu"])], ""
        except Exception:  # noqa: BLE001
            rows, error = [], "db"
        self.send(503 if error else 200, pages.report_list(rows, csrf, nonce, self.user, self.names(), error), nonce=nonce)
        return 503 if error else 200

    def report_page(self, path: str, csrf: str, nonce: str) -> int:
        parts = path.split("/")
        if len(parts) != 4 or not BU.fullmatch(parts[2]) or not PERIOD.fullmatch(parts[3]):
            raise HttpError(404, "report tidak ditemukan")
        bu, period = parts[2], parts[3]
        if not access.can_see(self.user, bu):
            raise HttpError(403, "Tidak ada akses. Akun Anda belum diberi akses ke report perusahaan ini.")
        try:
            report = self.cfg.store.get_report(bu, period)
        except Exception:  # noqa: BLE001
            raise HttpError(503, "database marketing_reports tidak menjawab; muat ulang halaman ini")
        if report is None:
            raise HttpError(404, "report tidak ditemukan")
        view = report_view.extract_view(report["html"])
        job = self.jobs.get((bu, period))
        state = pages.analysis_state(report["has_analysis"], job)
        edited = 0
        analysis = None
        if view is not None:
            try:
                edits, edits_ok = self.cfg.store.latest_edits(report["run_id"]), True
            except Exception:  # noqa: BLE001 - without the edit table the AI text still shows, read-only
                edits, edits_ok = [], False
            analysis, edited = analysis_edits.effective(report, edits, report_view.analysis_keys(view), access.is_admin(self.user) and edits_ok, pages.dt_text)
        saved_actions, actions_block, form_html = None, None, ""
        if view is not None:
            try:
                saved_actions = self.cfg.store.latest_actions(bu, period)
                items = list(saved_actions["items"]) if saved_actions else []
                actions_block = {"items": items, "saved_by": saved_actions["saved_by"] if saved_actions else None,
                                 "saved_at": pages.dt_text(saved_actions["saved_at"]) if saved_actions else None, "can_edit": access.is_admin(self.user)}
            except Exception:  # noqa: BLE001 - without the table the report still shows; the Action section just stays out
                items, actions_block = [], None
            if access.is_admin(self.user):
                spend = self.report_budget(report, view)
                note = (f"Budget dan spend {spend['month_label']} ikut dikirim sebagai pertimbangan analisis." if spend.get("state") == "ok"
                        else f"Budget {spend['month_label']} belum diatur, jadi analisis berjalan tanpa data budget dan spend.")
                form_html = pages.action_form(view["label"], items, view.get("campaign_names", []), note)
        chrome = pages.report_chrome(report, state, (job or {}).get("error", ""), csrf, self.user, self.names().get(bu, bu), edited, form_html)
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
        document = report_view.render_document(view, targets.build_tg(view, rows), analysis, standalone=False, names=self.names(), budget=self.report_budget(report, view), actions=actions_block)
        self.send(200, pages.inject_chrome(document, chrome, nonce, csrf), nonce=nonce)
        return 200

    def report_pdf(self, path: str) -> int:
        """The report page as a PDF file: the same data, text and access rules as the page, without the buttons that only work on a screen."""
        parts = path.split("/")
        if len(parts) != 5 or not BU.fullmatch(parts[2]) or not PERIOD.fullmatch(parts[3]):
            raise HttpError(404, "report tidak ditemukan")
        bu, period = parts[2], parts[3]
        if not access.can_see(self.user, bu):
            raise HttpError(403, "Tidak ada akses. Akun Anda belum diberi akses ke report perusahaan ini.")
        try:
            report = self.cfg.store.get_report(bu, period)
        except Exception:  # noqa: BLE001
            raise HttpError(503, "database marketing_reports tidak menjawab; coba lagi")
        view = report_view.extract_view(report["html"]) if report else None
        if view is None:
            raise HttpError(404, "report tidak ditemukan atau dibuat oleh generator versi lama")
        try:
            edits = self.cfg.store.latest_edits(report["run_id"])
        except Exception:  # noqa: BLE001 - without the edit table the AI text still prints
            edits = []
        analysis, _ = analysis_edits.effective(report, edits, report_view.analysis_keys(view), False, pages.dt_text)
        analysis = {k: v for k, v in analysis.items() if not k.startswith("_")}  # plain text: no chips, no provenance, no controls
        try:
            rows = self.cfg.store.latest_targets(bu)
        except Exception:  # noqa: BLE001
            rows = None
        spend = self.report_budget(report, view)
        spend["admin"] = False
        try:
            saved = self.cfg.store.latest_actions(bu, period)
            block = {"items": list(saved["items"]) if saved else [], "saved_by": saved["saved_by"] if saved else None,
                     "saved_at": pages.dt_text(saved["saved_at"]) if saved else None, "can_edit": False}
        except Exception:  # noqa: BLE001
            block = None
        html_text = report_view.print_document(view, targets.build_tg(view, rows), analysis, self.names(), spend, block, pages.dt_text(report["generated_at"]))
        try:
            data = pdf.render_pdf(html_text)
        except pdf.PdfBusy as exc:
            self.json(429, {"error": str(exc)})
            return 429
        except pdf.PdfError as exc:
            self.json(503, {"error": str(exc)})
            return 503
        slug = re.sub(r"[^A-Za-z0-9._-]+", "-", f"{self.names().get(bu, bu)}-{period}").strip("-") or f"{bu}-{period}"
        self.send(200, data, "application/pdf", extra={"Content-Disposition": f'attachment; filename="report-{slug}.pdf"'})
        return 200

    def start_analysis(self, form: dict) -> int:
        bu, period = form.get("bu", ""), form.get("period", "")
        if not BU.fullmatch(bu) or not PERIOD.fullmatch(period):
            raise HttpError(400, "perusahaan atau period tidak valid")
        report = self.cfg.store.get_report(bu, period)
        if report is None:
            raise HttpError(404, "belum ada report numerik; jalankan Report Generate di n8n dahulu")
        items = None
        if "items" in form:  # the form sent the list: check it before anything starts, then keep it as the period's list
            try:
                items = actions.clean_items(form["items"])
            except ValueError as exc:
                raise HttpError(400, str(exc))
        if not self.jobs.start((bu, period)):
            raise HttpError(409, "analisis untuk report ini sedang berjalan")
        try:
            if items is not None:
                self.cfg.store.add_actions(bu, period, items, self.user["username"])
            else:
                saved = self.cfg.store.latest_actions(bu, period)
                items = list(saved["items"]) if saved else []
            view = report_view.extract_view(report["html"])
            budget_ctx = budget.analysis_context(self.report_budget(report, view or {}))
            context = targets.context_for_analysis(facts_of(report), self.cfg.store.latest_targets(bu))
        except Exception:  # noqa: BLE001 - release the job, otherwise this report could never be analysed again
            self.jobs.finish((bu, period), "Action atau data pendukung tidak bisa disimpan atau dimuat. Coba lagi.")
            raise HttpError(503, "Action tidak tersimpan. Database marketing_reports tidak menjawab. Coba lagi.")
        extra = {"actions": items, "budget": budget_ctx}
        threading.Thread(target=run_analysis, args=(self.cfg, self.jobs, bu, period, context, extra), daemon=True).start()
        self.json(202, {"state": "running"})
        return 202

    def save_actions(self, form: dict) -> int:
        bu, period = form.get("bu", ""), form.get("period", "")
        if not BU.fullmatch(bu) or not PERIOD.fullmatch(period):
            raise HttpError(400, "perusahaan atau period tidak valid")
        try:
            report = self.cfg.store.get_report(bu, period)
        except Exception:  # noqa: BLE001
            raise HttpError(503, "Action tidak tersimpan. Database marketing_reports tidak menjawab. Coba simpan lagi.")
        if report is None:
            raise HttpError(404, "report tidak ditemukan")
        try:
            items = actions.clean_items(form.get("items", "[]"))
        except ValueError as exc:
            raise HttpError(400, str(exc))
        try:
            self.cfg.store.add_actions(bu, period, items, self.user["username"])
        except Exception:  # noqa: BLE001
            raise HttpError(503, "Action tidak tersimpan. Database marketing_reports tidak menjawab. Coba simpan lagi.")
        self.json(200, {"ok": True})
        return 200

    def save_edit(self, form: dict) -> int:
        bu, period, key = form.get("bu", ""), form.get("period", ""), form.get("key", "")
        if not BU.fullmatch(bu) or not PERIOD.fullmatch(period):
            raise HttpError(400, "perusahaan atau period tidak valid")
        try:
            report = self.cfg.store.get_report(bu, period)
        except Exception:  # noqa: BLE001
            raise HttpError(503, "Database marketing_reports tidak menjawab. Coba simpan lagi.")
        view = report_view.extract_view(report["html"]) if report else None
        if view is None:
            raise HttpError(404, "report tidak ditemukan")
        if key not in report_view.analysis_keys(view):
            raise HttpError(400, "panel tidak dikenal")
        if form.get("restore") == "1":
            body = None
        else:
            try:
                body = analysis_edits.clean_text(form.get("text", ""))
            except ValueError as exc:
                raise HttpError(400, str(exc))
        try:
            self.cfg.store.add_edit(report["run_id"], key, body, self.user["username"])
        except Exception:  # noqa: BLE001
            raise HttpError(503, "Edit tidak tersimpan. Database marketing_reports tidak menjawab. Coba simpan lagi.")
        self.json(200, {"ok": True})
        return 200

    def analysis_status(self, query: dict) -> int:
        bu, period = query.get("bu", ""), query.get("period", "")
        if not BU.fullmatch(bu) or not PERIOD.fullmatch(period):
            raise HttpError(400, "perusahaan atau period tidak valid")
        if not access.can_see(self.user, bu):
            raise HttpError(403, "Tidak ada akses")
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
        body = pages.targets_page(bu, UNITS[bu], products, ctx["months"], ctx["month"], current, ctx["year"], ctx["years"], semesters, history, csrf, nonce, self.user, {b: n for b, n in self.names().items() if b in UNITS}, notice, failed, errors)
        self.send(status, body, nonce=nonce)
        return status

    def targets_page(self, query: dict, csrf: str, nonce: str) -> int:
        bu = query.get("bu", "bu1")
        if bu not in UNITS:
            raise HttpError(404, "Perusahaan tidak dikenal")
        notice = NOTICES.get(query.get("saved", ""), "").format(label=self.names().get(bu, bu))
        return self.render_targets(bu, self.targets_context(bu, query), csrf, nonce, notice)

    def save_targets(self, kind: str, form: dict, csrf: str, nonce: str) -> int:
        bu = form.get("bu", "")
        if bu not in UNITS:
            raise HttpError(400, "Perusahaan tidak dikenal")
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
                raise HttpError(400, "Perusahaan ini tidak memakai target bulanan")
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

    # ---- performance
    def performance_page(self, query: dict, csrf: str, nonce: str) -> int:
        names = self.names()
        choices = [b for b in names if access.can_see(self.user, b)]
        if not choices:
            raise HttpError(403, "Tidak ada akses. Akun Anda belum diberi akses ke perusahaan mana pun.")
        bu = query.get("bu") or choices[0]
        if bu not in names:
            raise HttpError(404, "perusahaan tidak dikenal")
        if bu not in choices:
            raise HttpError(403, "Tidak ada akses. Akun Anda belum diberi akses ke perusahaan ini.")
        today = self.now().date()

        def render(status: int, params, state: str, snapshot=None, points=None, totals=None, matrix=None, option_lists=None, relations=None) -> int:
            self.send(status, performance_pages.performance_page(names=names, bu=bu, choices=choices, params=params, state=state, snapshot=snapshot, points=points or [], totals=totals,
                                                                 matrix=matrix, option_lists=option_lists, relations=relations, csrf=csrf, nonce=nonce, me=self.user), nonce=nonce)
            return status

        try:
            snapshot = self.cfg.store.latest_performance(bu)
        except Exception:  # noqa: BLE001
            return render(503, performance.parse_params(query, today, self.query_lists), "gagal")
        data = performance.load(snapshot) if snapshot else None
        params = performance.parse_params(query, snapshot["as_of"] if snapshot else today, self.query_lists)
        if snapshot is None:
            return render(200, params, "belum")
        if data is None:
            return render(200, params, "lama", snapshot=snapshot)
        option_lists = performance.options(data, params)
        rel = performance.relations(data)
        if params.error:
            return render(200, params, "error", snapshot=snapshot, option_lists=option_lists, relations=rel)
        leads = performance.filter_leads(data, params)
        points = performance.series(leads, params)
        if not performance.has_activity(points):
            unfiltered = params.active and performance.has_activity(performance.series(data.leads, params))
            return render(200, params, "kosong_filter" if unfiltered else "kosong", snapshot=snapshot, option_lists=option_lists, relations=rel)
        return render(200, params, "ok", snapshot=snapshot, points=points, totals=performance.summary(points), matrix=performance.matrix(leads, params), option_lists=option_lists, relations=rel)

    # ---- budget
    def report_budget(self, report: dict, view: dict) -> dict:
        kind, start, bu = report["period_kind"], report["period_start"], report["bu"]
        month = budget.month_of_period(kind, start)
        try:
            snaps = self.cfg.store.budget_snapshots(bu, budget.months_needed(kind, start))
            result = budget.report_budget(kind, start, report["period_end"], report["period"], snaps)
        except Exception:  # noqa: BLE001 - a budget problem must not hide the report
            result = {"state": "gagal", "month_label": budget.month_label(month), "kind": kind}
        result.update(bu=bu, month=month, admin=access.is_admin(self.user), prev_week_label=view.get("prev_label", ""))
        return result

    def budget_months(self) -> list[tuple[str, str]]:
        current = budget.month_of_date(self.now().date())
        return [(m, budget.month_label(m)) for m in (budget.shift_month(current, d) for d in range(-2, 4))]

    def budget_page(self, query: dict, csrf: str, nonce: str, posted: dict | None = None, errors: dict | None = None, failed: str = "", status: int = 200) -> int:
        names = access.names_with_defaults(self.safe_names())
        bu = posted.get("bu") if posted else query.get("bu", "")
        bu = bu if bu in names else next(iter(names))
        options = self.budget_months()
        wanted = posted.get("month") if posted else query.get("month", "")
        month = wanted if wanted in dict(options) else budget.month_of_date(self.now().date())
        store = self.cfg.store
        try:
            snaps = store.budget_snapshots(bu, [month])[month]
            history = store.budget_history(bu)
            html_text = store.latest_view_html(bu)
        except Exception:  # noqa: BLE001
            raise HttpError(503, "Budget tidak bisa dimuat. Database marketing_reports tidak menjawab; muat ulang halaman ini.")
        current = budget.newest(snaps)
        weeks = budget.weeks_of_month(month)
        today = self.now().date()
        digits = lambda v: "" if v in (None, "") else f"{int(v):,}".replace(",", ".")
        rows: list[dict] = []
        tracker = list((report_view.extract_view(html_text) or {}).get("campaign_names", []) if html_text else [])
        try:  # the Performa snapshot is refreshed on its own, so it can know campaigns the newest report was built before
            snapshot = store.latest_performance(bu)
        except Exception:  # noqa: BLE001 - the report's own list is still offered
            snapshot = None
        rel = None
        if snapshot and isinstance(snapshot.get("data"), dict):
            tracker += [n for n in (snapshot["data"].get("dims") or {}).get("campaign", []) if isinstance(n, str) and n.strip()]
            try:
                loaded = performance.load(snapshot)
                rel = performance.relations(loaded) if loaded else None
            except Exception:  # noqa: BLE001 - the picker still works, only without the parent filters
                rel = None
        if posted is not None:
            for index in budget.row_indexes(posted):
                rows.append({"idx": index, "name": " ".join(posted[f"n_{index}"].split()), "budget": posted.get(f"b_{index}", ""), "month": posted.get(f"m_{index}", ""),
                             "weeks": {k: posted.get(f"w_{index}_{k}", "") for k, _, _ in weeks}})
            total_text, as_of_text = posted.get("total", ""), posted.get("as_of", "")
        else:
            saved = budget.campaigns_of(current)
            for index, name in enumerate(sorted(saved, key=str.casefold)):  # only campaigns that already have figures; the rest are added by hand
                c = saved[name]
                rows.append({"idx": index, "name": name, "budget": digits(c.get("budget")), "month": digits(c.get("month_spend")),
                             "weeks": {k: digits((c.get("weeks") or {}).get(k)) for k, _, _ in weeks}})
            total_text = digits(current["total_budget"]) if current else ""
            as_of_text = current["spend_as_of"].isoformat() if current and current["spend_as_of"] else ""
        grouped = performance.nurturing_groups(rel)
        universe = {n.casefold(): n for n in tracker}
        universe.update({r["name"].casefold(): r["name"] for r in rows if r["name"]})  # a saved name missing from the tracker can still be added back
        picker = sorted(universe.values(), key=str.casefold)
        base_id = str(current["snapshot_id"]) if current else ""
        notice = ""
        if query.get("saved"):
            notice = f"Budget dan spend {names[bu]} {budget.month_label(month)} tersimpan."
        self.send(status, pages.budget_page(bu, names, month, options, rows, picker, weeks, total_text, as_of_text, base_id, today, errors or {}, history, csrf, nonce, self.user, notice, failed, rel=rel, grouped=grouped), nonce=nonce)
        return status

    def safe_names(self) -> dict[str, str]:
        try:
            return self.cfg.store.company_names()
        except Exception:  # noqa: BLE001
            return {}

    def save_budget(self, form: dict, csrf: str, nonce: str) -> int:
        names = access.names_with_defaults(self.safe_names())
        bu, month = form.get("bu", ""), form.get("month", "")
        if bu not in names or month not in dict(self.budget_months()):
            raise HttpError(400, "perusahaan atau bulan tidak valid")
        today = self.now().date()
        try:
            parsed = budget.parse_form(form, month, today)
        except budget.FormError as exc:
            return self.budget_page({}, csrf, nonce, posted=form, errors=exc.errors, failed="Periksa isian yang ditandai. Belum ada yang disimpan.", status=422)
        data = {"campaigns": parsed["campaigns"]}
        try:
            saved = self.cfg.store.add_budget_snapshot(bu, month, form.get("base", ""), parsed["total"], parsed["as_of"], data, self.user["username"])
        except Exception:  # noqa: BLE001
            return self.budget_page({}, csrf, nonce, posted=form, failed="Budget tidak tersimpan. Database marketing_reports tidak menjawab. Coba simpan lagi.", status=503)
        if not saved:
            raise HttpError(409, "Budget bulan ini sudah diubah orang lain sejak halaman dibuka. Muat ulang halaman Budget, lalu isi lagi.")
        self.redirect(f"/budget?bu={bu}&month={month}&saved=1")
        return 303

    # ---- users and company names (admin)
    def users_pages(self, path: str, query: dict, csrf: str, nonce: str) -> int:
        names = self.names()
        if path == "/users":
            try:
                users = self.cfg.store.list_users()
            except Exception:  # noqa: BLE001
                raise HttpError(503, "Daftar pengguna tidak bisa dimuat. Database marketing_reports tidak menjawab.")
            saved = query.get("u", "") if query.get("saved") and USERNAME.fullmatch(query.get("u", "")) else ""
            self.send(200, pages.users_page(users, names, csrf, nonce, self.user, f"Pengguna {saved} tersimpan." if saved else ""), nonce=nonce)
            return 200
        if path == "/users/new":
            values = {"username": "", "role": "user", "all_companies": False, "companies": [], "active": True}
            self.send(200, pages.user_form_page("new", values, {}, names, csrf, nonce, self.user), nonce=nonce)
            return 200
        username = query.get("u", "")
        try:
            row = self.cfg.store.get_user(username) if USERNAME.fullmatch(username) else None
        except Exception:  # noqa: BLE001
            raise HttpError(503, "database marketing_reports tidak menjawab; muat ulang halaman ini")
        if row is None:
            raise HttpError(404, "pengguna tidak ditemukan")
        self.send(200, pages.user_form_page("edit", row, {}, names, csrf, nonce, self.user), nonce=nonce)
        return 200

    def save_user(self, form: dict, csrf: str, nonce: str) -> int:
        mode = form.get("mode", "")
        if mode not in ("new", "edit"):
            raise HttpError(400, "permintaan tidak valid")
        username = form.get("username", "").strip().lower()
        role = form.get("role", "")
        if role not in ("admin", "user"):
            raise HttpError(400, "peran tidak valid")
        errors: dict[str, str] = {}
        known = access.company_ids()
        picked = [c for c in self.form_lists.get("company", []) if c in known]
        everyone = role == "admin" or form.get("scope") == "all"
        if role == "user" and not everyone and not picked:
            errors["scope"] = "Pilih minimal satu perusahaan, atau pilih Semua perusahaan."
        if mode == "new" and not USERNAME.fullmatch(username):
            errors["username"] = "Username harus 3 sampai 32 karakter: huruf kecil, angka, titik, garis bawah, dan strip."
        password = form.get("password", "")
        password_hash = None
        if password or mode == "new":
            try:
                auth.check_password_strength(password)
            except ValueError as exc:
                errors["password"] = str(exc).capitalize() + "."
        values = {"username": username, "role": role, "all_companies": everyone, "companies": [] if everyone else picked, "active": form.get("active", "1") != "0"}
        names = self.names()

        def again(message: str = "", status: int = 422) -> int:
            self.send(status, pages.user_form_page(mode, values, errors, names, csrf, nonce, self.user, message), nonce=nonce)
            return status

        if errors:
            return again()
        if password:
            password_hash = auth.hash_password(password)
        store = self.cfg.store
        try:
            if mode == "new":
                store.create_user(username, password_hash, role, values["all_companies"], values["companies"], values["active"])
            else:
                if not USERNAME.fullmatch(username):
                    raise HttpError(400, "username tidak valid")
                store.update_user(username, password_hash, role, values["all_companies"], values["companies"], values["active"])
        except UserError as exc:
            errors["username" if "Username" in exc.args[0] else "active"] = exc.args[0]
            return again()
        except HttpError:
            raise
        except Exception:  # noqa: BLE001
            return again("Pengguna tidak tersimpan. Database marketing_reports tidak menjawab. Coba simpan lagi.", 503)
        self.redirect(f"/users?saved=1&u={username}")
        return 303

    def companies_page(self, query: dict, csrf: str, nonce: str) -> int:
        ids = access.company_ids()
        names = self.names()
        notice = "Nama perusahaan tersimpan. Berlaku di semua halaman." if query.get("saved") else ""
        self.send(200, pages.companies_page(ids, names, {b: access.default_name(b) for b in ids}, {}, csrf, nonce, self.user, notice), nonce=nonce)
        return 200

    def save_companies(self, form: dict, csrf: str, nonce: str) -> int:
        ids = access.company_ids()
        errors: dict[str, str] = {}
        cleaned: dict[str, str] = {}
        for bu in ids:
            raw = form.get(f"name_{bu}", "")
            try:
                cleaned[bu] = access.validate_name(raw)
            except ValueError as exc:
                errors[bu], errors[f"_v_{bu}"] = str(exc), raw
        seen: dict[str, str] = {}
        for bu, name in cleaned.items():
            if name.lower() in seen:
                errors[bu], errors[f"_v_{bu}"] = "Kedua perusahaan tidak boleh memakai nama yang sama.", name
            seen[name.lower()] = bu
        defaults = {b: access.default_name(b) for b in ids}

        def again(message: str, status: int) -> int:
            shown = {**self.names(), **{b: errors.get(f"_v_{b}", cleaned.get(b, "")) for b in ids}}
            self.send(status, pages.companies_page(ids, shown, defaults, errors, csrf, nonce, self.user, "", message), nonce=nonce)
            return status

        if errors:
            return again("Periksa isian yang ditandai. Belum ada yang disimpan.", 422)
        try:
            self.cfg.store.save_company_names(cleaned)
        except UserError as exc:
            for bu in ids[1:]:
                errors[bu], errors[f"_v_{bu}"] = exc.args[0], cleaned[bu]
            return again("Nama tidak tersimpan.", 422)
        except Exception:  # noqa: BLE001
            return again("Nama tidak tersimpan. Database marketing_reports tidak menjawab. Coba simpan lagi.", 503)
        self.redirect("/companies?saved=1")
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
    try:
        if config.store.ensure_bootstrap_admin(config.password_hash):
            print("admin pertama dibuat dari VIEWER_PASSWORD_HASH (username: admin)", flush=True)
    except Exception as exc:  # noqa: BLE001 - the service starts anyway; login reports the database state
        print(f"peringatan: tabel pengguna belum bisa dipakai ({type(exc).__name__}); jalankan database/004_users_and_company_names.sql", flush=True)
    server = make_server(config, port=int(os.environ.get("PORT", 8090)))
    print(f"report-viewer listening on :{server.server_address[1]}", flush=True)
    server.serve_forever()
