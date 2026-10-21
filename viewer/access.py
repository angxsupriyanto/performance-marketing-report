"""Who may see which company, and the display name of each company."""
from __future__ import annotations

import re

import generate_report

NAME_RULE = re.compile(r"[A-Za-z0-9][A-Za-z0-9 .\-]{0,31}")


def company_ids() -> list[str]:
    return sorted(p.stem for p in generate_report.PROFILE_DIR.glob("*.json"))


def default_name(bu: str) -> str:
    match = re.fullmatch(r"bu(\d+)", bu)
    return f"Perusahaan {match.group(1)}" if match else bu


def names_with_defaults(stored: dict[str, str] | None) -> dict[str, str]:
    stored = stored or {}
    return {bu: stored.get(bu) or default_name(bu) for bu in company_ids()}


def is_admin(user: dict) -> bool:
    return user["role"] == "admin"


def can_see(user: dict, bu: str) -> bool:
    return is_admin(user) or user["all_companies"] or bu in user["companies"]


def validate_name(raw: str) -> str:
    """Returns the cleaned name or raises ValueError with the text to show next to the field."""
    name = " ".join(raw.split())
    if not name:
        raise ValueError("Nama tidak boleh kosong.")
    if not NAME_RULE.fullmatch(name):
        raise ValueError("Pakai 1 sampai 32 karakter: huruf, angka, spasi, titik, dan strip.")
    return name
