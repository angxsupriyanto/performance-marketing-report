"""The list of actions the team took in a report period: what is accepted, and how it reaches the analysis.

An item is {"action", "campaign", "note"}: plain text only (the page renders it escaped). The action is required, the other two may be empty.
Rows with an empty action are dropped, so a half-filled form line never turns into a stored item.
"""
from __future__ import annotations

import json

MAX_ITEMS = 30
MAX_ACTION = 300
MAX_CAMPAIGN = 100
MAX_NOTE = 300
LIMITS = (("action", MAX_ACTION, "Action"), ("campaign", MAX_CAMPAIGN, "Campaign"), ("note", MAX_NOTE, "Catatan"))


def _text(value, limit: int, label: str, row: int) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"{label} baris {row} harus berupa teks.")
    text = " ".join(value.split())
    if len(text) > limit or not text.isprintable():
        raise ValueError(f"{label} baris {row} maksimal {limit} karakter dan tanpa karakter kontrol.")
    return text


def clean_items(raw) -> list[dict]:
    """Accepts a JSON string or an already parsed list. Raises ValueError with a message that is safe to show."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw) if raw.strip() else []
        except ValueError:
            raise ValueError("Daftar action tidak terbaca.")
    if not isinstance(raw, list):
        raise ValueError("Daftar action tidak terbaca.")
    items: list[dict] = []
    for number, entry in enumerate(raw, 1):
        if not isinstance(entry, dict):
            raise ValueError(f"Baris {number} tidak terbaca.")
        row = {key: _text(entry.get(key), limit, label, number) for key, limit, label in LIMITS}
        if not row["action"]:
            if row["campaign"] or row["note"]:
                raise ValueError(f"Isi action pada baris {number}, atau kosongkan barisnya.")
            continue
        items.append(row)
    if len(items) > MAX_ITEMS:
        raise ValueError(f"Maksimal {MAX_ITEMS} action.")
    return items
