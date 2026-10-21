"""Which text each analysis panel shows: the newest manual edit, or the newest AI analysis.

An edit counts only while it is newer than the run's newest AI analysis, so creating a new analysis replaces every
panel (the older edits stay in the database as history). An edit row whose body is None is a "restore the AI version"
marker. The result is the analysis mapping that report_view renders, plus reserved keys `_panels` (per-panel status
and wording) and `_can_edit`, which never collide with AI keys because the parser rejects unknown keys.
"""
from __future__ import annotations

MAX_TEXT_CHARS = 4000


def effective(report: dict, edits: list[dict], keys: list[str], can_edit: bool, fmt_time) -> tuple[dict, int]:
    """Returns (analysis mapping for report_view, number of panels currently showing an edit)."""
    ai = report.get("analysis") if isinstance(report.get("analysis"), dict) else None
    ai_at = report.get("analysis_created_at")
    model = (report.get("model") or "").strip()
    newest = {e["panel_key"]: e for e in edits}
    texts: dict[str, str] = {}
    panels: dict[str, dict] = {}
    edited = 0
    for key in keys:
        ai_text = (ai.get(key) or "").strip() if ai else ""
        edit = newest.get(key)
        if edit is not None and ai_at is not None and edit["created_at"] <= ai_at:
            edit = None  # superseded by a newer AI analysis
        if edit is not None and edit["body"] is not None:
            state, text = "edited", edit["body"].strip()
            edited += 1
            if ai is not None:
                meta = f"Diedit oleh {edit['edited_by']} · {fmt_time(edit['created_at'])} · model awal: {model or 'tidak tercatat'}"
            else:
                meta = f"Ditulis manual oleh {edit['edited_by']} · {fmt_time(edit['created_at'])} · belum ada analisis AI"
        elif ai_text:
            state, text = "ai", ai_text
            meta = f"Dibuat oleh model {model or 'tidak tercatat'} · {fmt_time(ai_at)}"
        else:
            state, text, meta = "none", "", ""
        if text:
            texts[key] = text
        panels[key] = {
            "state": state,
            "chip": f"AI · {model}" if state == "ai" and model else ("AI" if state == "ai" else ("Edited" if state == "edited" else "")),
            "meta": meta,
            "edit_label": "Edit" if text else "Tulis manual",
            "restore_label": ("Kembalikan ke versi AI" if ai is not None else "Hapus teks manual") if state == "edited" else "",
            "draft": text,
        }
    return {**texts, "_panels": panels, "_can_edit": can_edit}, edited


def clean_text(raw: str) -> str:
    """Plain text only: the page renders it escaped, so markup would show literally. Raises ValueError with the message to show."""
    text = raw.replace("\r\n", "\n").strip()
    if not text:
        raise ValueError("Teks tidak boleh kosong. Untuk membuangnya pakai tombol pengembalian.")
    if len(text) > MAX_TEXT_CHARS:
        raise ValueError(f"Teks melebihi {MAX_TEXT_CHARS} karakter.")
    return text
