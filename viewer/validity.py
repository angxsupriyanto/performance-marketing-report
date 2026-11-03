"""How long a lead's MQL, SQL and Deal Won stay valid after its Inbound Date: the settings form and the text that describes them.

The settings are stored per company as {"defaults": {stage: null|months}, "remarks": [{"remark", stage: "default"|null|months}]}
(null = no limit, "default" = follow the general limit). The generator checks the same shape again and applies it; this module only turns
the admin's form into that shape, with messages that say which field is wrong, and writes the summary sentences.
"""
from __future__ import annotations

import generate_report

STAGES = generate_report.EXPIRY_STAGES
KEYS = {"MQL": "mql", "SQL": "sql", "Deal Won": "won"}
MAX_MONTHS = generate_report.MAX_EXPIRY_MONTHS
MAX_RULES = generate_report.MAX_EXPIRY_RULES


def profile_config(bu: str) -> dict:
    """What is in force for a company that has not saved anything yet: the limits written in its profile."""
    return generate_report.profile_validity(generate_report.load_profile(bu))


def _months(text: str, label: str) -> int:
    cleaned = (text or "").strip()
    if not cleaned.isascii() or not cleaned.isdigit() or not 1 <= int(cleaned) <= MAX_MONTHS:
        raise ValueError(f"{label}: isi bulan bulat 1 sampai {MAX_MONTHS}.")
    return int(cleaned)


def parse_form(form: dict, allowed_remarks: list[str]) -> tuple[dict | None, dict]:
    """Returns (config, errors). errors maps a field name to its message; config is None when anything is wrong. allowed_remarks are the texts the picker offered."""
    errors: dict = {}
    defaults: dict = {}
    for stage in STAGES:
        key = KEYS[stage]
        mode = form.get(f"g_{key}_mode", "none")
        if mode == "none":
            defaults[stage] = None
        elif mode == "bulan":
            try:
                defaults[stage] = _months(form.get(f"g_{key}_n", ""), f"Batas umum {stage}")
            except ValueError as exc:
                errors[f"g_{key}_n"] = str(exc)
        else:
            errors[f"g_{key}_mode"] = f"Batas umum {stage}: pilihan tidak dikenal."
    try:
        count = int(form.get("rule_count", "0") or 0)
    except ValueError:
        count = -1
    if not 0 <= count <= MAX_RULES + 20:
        errors["_rules"] = "Daftar aturan Remark tidak terbaca."
        count = 0
    rules, seen = [], set()
    for i in range(count):
        remark = " ".join((form.get(f"r{i}_remark", "") or "").split())
        if not remark:
            continue  # a blank row the admin never filled
        label = f"Aturan Remark {remark}"
        if remark not in allowed_remarks:
            errors[f"r{i}_remark"] = f"{label}: pilih Remark dari daftar."
            continue
        if remark.casefold() in seen:
            errors[f"r{i}_remark"] = f"Remark {remark} hanya boleh punya satu aturan."
            continue
        seen.add(remark.casefold())
        rule = {"remark": remark}
        for stage in STAGES:
            key = KEYS[stage]
            mode = form.get(f"r{i}_{key}_mode", "default")
            if mode == "default":
                rule[stage] = "default"
            elif mode == "none":
                rule[stage] = None
            elif mode == "bulan":
                try:
                    rule[stage] = _months(form.get(f"r{i}_{key}_n", ""), f"{label}, {stage}")
                except ValueError as exc:
                    errors[f"r{i}_{key}_n"] = str(exc)
            else:
                errors[f"r{i}_{key}_mode"] = f"{label}, {stage}: pilihan tidak dikenal."
        rules.append(rule)
    if len(rules) > MAX_RULES:
        errors["_rules"] = f"Maksimal {MAX_RULES} aturan Remark."
    if errors:
        return None, errors
    return {"defaults": defaults, "remarks": rules}, {}


def limit_text(value) -> str:
    return "tanpa batas" if value is None else f"{value} bulan"


def summary(config: dict) -> list[str]:
    """The sentences shown under the form. The report carries the same facts (generator side), so what the admin reads here is what the report says."""
    lines = ["Acuan tanggal: Inbound Date."]
    defaults = config["defaults"]
    lines.append("Umum: " + "; ".join(f"{stage} {limit_text(defaults[stage])}" for stage in STAGES) + ".")
    for rule in config["remarks"]:
        parts = []
        for stage in STAGES:
            value = rule[stage]
            parts.append(f"{stage} {'ikut batas umum' if value == 'default' else limit_text(value)}")
        lines.append(f"Remark {rule['remark']}: " + "; ".join(parts) + ".")
    return lines


def form_values(config: dict) -> dict:
    """The saved config as the form's field values, so the page and a re-shown failed form use the same names."""
    values: dict = {}
    for stage in STAGES:
        key, value = KEYS[stage], config["defaults"][stage]
        values[f"g_{key}_mode"] = "none" if value is None else "bulan"
        values[f"g_{key}_n"] = "" if value is None else str(value)
    values["rule_count"] = str(len(config["remarks"]))
    for i, rule in enumerate(config["remarks"]):
        values[f"r{i}_remark"] = rule["remark"]
        for stage in STAGES:
            key, value = KEYS[stage], rule[stage]
            values[f"r{i}_{key}_mode"] = "default" if value == "default" else ("none" if value is None else "bulan")
            values[f"r{i}_{key}_n"] = "" if value in ("default", None) else str(value)
    return values
