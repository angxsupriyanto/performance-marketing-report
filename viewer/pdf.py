"""Turns a finished report page into a PDF with headless Chromium.

The page is written to a private temporary folder and printed by one short-lived `chromium --headless --print-to-pdf` process: no network,
no profile kept, nothing left behind. Only one PDF is made at a time, because a browser process is heavy; a second request is told to retry
instead of piling up. The binary comes from VIEWER_CHROMIUM (default: chromium).
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import threading
from pathlib import Path

TIMEOUT_SECONDS = 45
MAX_PDF_BYTES = 25 * 1024 * 1024
_gate = threading.Semaphore(1)


class PdfError(Exception):
    """The PDF could not be made. The text is safe to show to the person who asked."""


class PdfBusy(PdfError):
    pass


def chromium_path() -> str:
    return os.environ.get("VIEWER_CHROMIUM", "chromium")


def render_pdf(html: str) -> bytes:
    if not _gate.acquire(blocking=False):
        raise PdfBusy("PDF lain sedang dibuat. Coba lagi beberapa detik lagi.")
    try:
        with tempfile.TemporaryDirectory(prefix="report-pdf-") as tmp:
            source, target, profile = Path(tmp, "report.html"), Path(tmp, "report.pdf"), Path(tmp, "profile")
            source.write_text(html, encoding="utf-8")
            command = [
                chromium_path(), "--headless", "--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage", "--disable-extensions", "--disable-crash-reporter",
                "--no-first-run", "--hide-scrollbars", "--no-pdf-header-footer", "--host-resolver-rules=MAP * ~NOTFOUND", f"--user-data-dir={profile}", f"--print-to-pdf={target}", source.as_uri(),
            ]
            env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": tmp, "LANG": "C.UTF-8"}
            try:
                subprocess.run(command, env=env, cwd=tmp, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=TIMEOUT_SECONDS, check=False)
            except FileNotFoundError:
                raise PdfError("PDF belum bisa dibuat: Chromium tidak terpasang di layanan viewer.")
            except subprocess.TimeoutExpired:
                raise PdfError("PDF terlalu lama dibuat dan dihentikan. Coba lagi.")
            if not target.exists():
                raise PdfError("PDF tidak berhasil dibuat. Coba lagi.")
            data = target.read_bytes()
            if not data.startswith(b"%PDF") or len(data) > MAX_PDF_BYTES:
                raise PdfError("PDF tidak berhasil dibuat. Coba lagi.")
            return data
    finally:
        _gate.release()
