"""The report page, exactly as designed in the approved mockup (Laporan.dc.html / LaporanBU2.dc.html).

One renderer for two callers:
  * the generator stores `render_document(view)` as the numeric report (targets and analysis still empty);
  * the viewer renders the same `view` again with the current targets and the latest analysis.

`view` is plain JSON and is embedded in the stored HTML, so the viewer never has to parse the page.
Only what the mockup shows is rendered: nothing else from the old dashboard exists here.
"""
from __future__ import annotations

import json
import re
from decimal import ROUND_HALF_UP, Decimal
from html import escape

VIEW_ID = "report-view"
MONTHS = ("Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des")
NUMBER_WORDS = {1: "Satu", 2: "Dua", 3: "Tiga", 4: "Empat", 5: "Lima", 6: "Enam", 7: "Tujuh"}
ALL_OF = {1: "satunya", 2: "keduanya", 3: "ketiganya", 4: "keempatnya", 5: "kelimanya", 6: "keenamnya", 7: "ketujuhnya"}
EMPTY_ANALYSIS = "Kosong sampai analisis dibuat."

INK, TEXT, MUTED, LINE, BLUE = "#17283e", "#394d65", "#607188", "#dfe7f0", "#2159a9"

CSS = """
*{box-sizing:border-box}
body{margin:0;background:#f4f7fb;color:#394d65;font:14px/1.5 Inter,Arial,sans-serif}
a{color:#2159a9}a:hover{color:#17283e}
a:focus-visible,button:focus-visible{outline:2px solid #2159a9;outline-offset:2px}
.rp-main{width:100%;max-width:1040px;margin:0 auto;padding:0 32px 64px}
.cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}
.sr{position:absolute;left:-9999px}
.list{width:100%;border-collapse:collapse}
.list th{text-align:left;font-weight:500;color:#607188;padding:12px 16px;border-bottom:1px solid #dfe7f0}
.list td{padding:12px 16px;border-top:1px solid #dfe7f0;vertical-align:top}
.list tbody tr:first-child td{border-top:0}
.list .num{text-align:right}
.list tfoot td{font-weight:600;color:#17283e}
.split{display:flex;flex-wrap:wrap;gap:16px;align-items:flex-start}
.split-main{flex:1 1 560px;min-width:0}
.split-side{flex:1 1 260px;min-width:0}
.tablebox{border:1px solid #dfe7f0;border-radius:6px;overflow-x:auto}
.bars{display:grid;grid-template-columns:96px minmax(0,1fr) 40px;gap:8px 12px;align-items:center}
.track{height:16px;background:#edf4ff;border-radius:4px}
.fill{height:16px;background:#2159a9;border-radius:4px}
@media (max-width:680px){
  .rp-main{padding:0 16px 48px}
  .cards{grid-template-columns:minmax(0,1fr)}
  .list thead{position:absolute;left:-9999px}
  .list tr{display:block;padding:8px 16px;border-top:1px solid #dfe7f0}
  .list tbody tr:first-child{border-top:0}
  .list td{display:flex;justify-content:space-between;gap:16px;padding:4px 0;border:0;text-align:left}
  .list td::before{content:attr(data-label);color:#607188}
  .list .num{text-align:left}
}
@media print{body{background:#fff}}
"""


# ---- number formatting (display only; all arithmetic is done by the generator)
def dotted(n: int | Decimal) -> str:
    return f"{int(Decimal(n).quantize(Decimal(1), rounding=ROUND_HALF_UP)):,}".replace(",", ".")


def idr(n) -> str:
    return "Rp " + dotted(n)


def count_text(n) -> str:
    return f"{dotted(n)} SQL"


def pct_text(value: float | None) -> str:
    return "—" if value is None else f"{value:.1f}".replace(".", ",") + "%"


def percent(actual, target) -> float | None:
    return float(Decimal(actual) * 100 / Decimal(target)) if target else None


def value_text(value, unit: str) -> str:
    return idr(value) if unit == "idr" else count_text(value)


def width(value: float | None) -> str:
    return f"{max(0.0, min(100.0, value or 0.0)):.1f}%"


def e(value) -> str:
    return escape(str(value), quote=True)


# ---- small building blocks, copied from the mockup markup
def link_target() -> str:
    return '<a href="/targets" style="display: inline-flex; align-items: center; min-height: 44px; font-weight: 600">Atur target</a>'


def card(label: str, value: str, compare: str, share: str | None = None) -> str:
    extra = f'<div style="color: {TEXT}">{e(share)}</div>' if share else ""
    return (
        f'<div style="border: 1px solid {LINE}; border-radius: 6px; padding: 16px"><div style="color: {MUTED}">{e(label)}</div>'
        f'<div style="font: 600 22px/1.3 Inter, Arial, sans-serif; color: {INK}">{e(value)}</div><div style="color: {MUTED}">{e(compare)}</div>{extra}</div>'
    )


RATES = {"MQL": "Submission", "SQL": "MQL", "Deal Won": "SQL"}  # card -> the stage its rate divides by, see METRIC_RULES.md


def h3(text: str) -> str:
    return f'<h3 style="margin: 0 0 4px; font: 600 16px/1.4 Inter, Arial, sans-serif; color: {INK}">{e(text)}</h3>'


def h4(text: str) -> str:
    return f'<h4 style="margin: 0 0 4px; font: 600 14px/1.4 Inter, Arial, sans-serif; color: {INK}">{e(text)}</h4>'


def muted_p(text_html: str, bottom: int = 12) -> str:
    return f'<p style="margin: 0 0 {bottom}px; color: {MUTED}">{text_html}</p>'


def th(label: str, num: bool = False, sort: bool = False) -> str:
    attrs = (' class="num"' if num else "") + (' aria-sort="descending"' if sort else "")
    return f'<th scope="col"{attrs}>{e(label)}</th>'


def td(label: str, value: str, num: bool = False, extra: str = "") -> str:
    cls = ' class="num"' if num else ""
    return f'<td data-label="{e(label)}"{cls}{extra}>{e(value)}</td>'


def box_table(caption: str, headers: list[str], body: str, foot: str) -> str:
    return (
        f'<div style="border: 1px solid {LINE}; border-radius: 6px"><table class="list"><caption class="sr">{e(caption)}</caption>'
        f'<thead><tr>{"".join(headers)}</tr></thead><tbody>{body}</tbody><tfoot>{foot}</tfoot></table></div>'
    )


def analysis_body(key: str, analysis: dict | None) -> str:
    text = (analysis or {}).get(key)
    if isinstance(text, str) and text.strip():
        return f'<div data-analysis="{e(key)}">{e(text.strip())}</div>'
    return f'<div data-analysis="{e(key)}" style="color: {MUTED}">{EMPTY_ANALYSIS}</div>'


def _link_button(act: str, key: str, label: str) -> str:
    return (f'<button type="button" data-act="{act}" data-key="{e(key)}" style="display: inline-flex; align-items: center; min-height: 44px; padding: 0; border: 0; background: none; '
            f'color: {BLUE}; font: 600 14px Inter, Arial, sans-serif; cursor: pointer">{e(label)}</button>')


def analysis_panel(title: str, key: str, analysis: dict | None, outer_style: str, outer_class: str = "") -> str:
    """One analysis panel. Plain (stored report, n8n output) unless the viewer passes `_panels`, which adds the status chip,
    the provenance line and, for admins, the edit controls of the approved mockup."""
    cls = f' class="{outer_class}"' if outer_class else ""
    panels = (analysis or {}).get("_panels")
    if panels is None or key not in panels:
        return f'<div{cls} style="{outer_style}"><div style="font-weight: 600; color: {INK}; margin-bottom: 4px">{e(title)}</div>{analysis_body(key, analysis)}</div>'
    info = panels[key]
    chip = ""
    if info["state"] == "ai":
        chip = f'<span style="display: inline-block; padding: 2px 8px; border: 1px solid #6f8199; border-radius: 4px; color: #394d65; font-weight: 500; font-size: 12.5px">{e(info["chip"])}</span>'
    elif info["state"] == "edited":
        chip = f'<span style="display: inline-block; padding: 2px 8px; border-radius: 4px; background: #edf4ff; color: {BLUE}; font-weight: 600; font-size: 12.5px">Edited</span>'
    head = (f'<div style="display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 4px 12px; margin-bottom: 4px">'
            f'<div style="font-weight: 600; color: {INK}">{e(title)}</div>{chip}</div>')
    meta = f'<div data-role="meta" style="margin-top: 8px; color: {MUTED}; font-size: 12.5px">{e(info["meta"])}</div>' if info["meta"] else ""
    editor = controls = ""
    if (analysis or {}).get("_can_edit"):
        editor = (
            f'<div data-editor="{e(key)}" hidden><label for="edit-{e(key)}" style="position: absolute; left: -9999px">Teks {e(title)}</label>'
            f'<textarea id="edit-{e(key)}" rows="6" maxlength="4000" style="width: 100%; box-sizing: border-box; padding: 10px 12px; border: 1px solid #6f8199; border-radius: 6px; background: #ffffff; color: {INK}; font: 14px/1.5 Inter, Arial, sans-serif; resize: vertical">{e(info["draft"])}</textarea>'
            f'<p data-role="error" role="alert" hidden style="margin: 8px 0 0; padding: 10px 12px; border-radius: 6px; background: #fcecec; color: #ac3d3d"></p>'
            f'<div style="display: flex; flex-wrap: wrap; align-items: center; gap: 4px 16px; margin-top: 8px">'
            f'<button type="button" data-act="save" data-key="{e(key)}" style="height: 44px; padding: 0 20px; border: 0; border-radius: 6px; background: {BLUE}; color: #ffffff; font: 600 14px Inter, Arial, sans-serif; cursor: pointer">Simpan edit</button>'
            f'{_link_button("cancel", key, "Batal")}</div></div>'
        )
        restore = _link_button("restore", key, info["restore_label"]) if info["restore_label"] else ""
        controls = f'<div data-role="controls" style="display: flex; flex-wrap: wrap; gap: 0 20px">{_link_button("edit", key, info["edit_label"])}{restore}</div>'
    return f'<div{cls} data-panel="{e(key)}" style="{outer_style}">{head}{analysis_body(key, analysis)}{editor}{meta}{controls}</div>'


def analysis_box(title: str, key: str, analysis: dict | None, top: int = 16) -> str:
    return analysis_panel(title, key, analysis, f"margin-top: {top}px; border: 1px solid {LINE}; border-radius: 6px; padding: 16px")


# ---- targets: `tg` is None (not set) or a dict built by the viewer
#   {"error": bool, "semester": amount|None, "year": amount|None, "hardware": {product: amount|None}}
def _tg(tg: dict | None) -> dict:
    return tg or {"error": False, "semester": None, "year": None, "hardware": {}}


def error_note(top: int) -> str:
    return (
        f'<p role="alert" style="margin: {top}px 0 0; padding: 10px 12px; border-radius: 6px; background: #fcecec; color: #ac3d3d">'
        "Target tidak bisa dimuat. Database marketing_reports tidak menjawab. Muat ulang halaman ini.</p>"
    )


def progress_card(title: str, actual, target, unit: str, aria_noun: str, short_noun: str) -> str:
    value = percent(actual, target)
    done = value_text(actual, unit)
    if target:
        tail = f"Tercapai {done} dari target {value_text(target, unit)}" if unit == "idr" else f"{done} dari target {value_text(target, unit)}"
        label, caption = f"Progress {aria_noun}, {pct_text(value)} dari target", f"{pct_text(value)} dari target {short_noun}"
    else:
        tail = f"Tercapai {done} · target belum diatur" if unit == "idr" else f"{done} · target belum diatur"
        label, caption = f"Progress {aria_noun}, target belum diatur", "Target belum diatur"
    return (
        f'<div style="background: #ffffff; border: 1px solid {LINE}; border-radius: 6px; padding: 16px">'
        f'<div style="font-weight: 600; color: {INK}; margin-bottom: 4px">{e(title)}</div><div style="color: {MUTED}; margin-bottom: 8px">{e(tail)}</div>'
        f'<div role="img" aria-label="{e(label)}" style="height: 16px; background: #edf4ff; border: 1px solid #6f8199; box-sizing: border-box"><div style="width: {width(value)}; height: 100%; background: {BLUE}"></div></div>'
        f'<div style="margin-top: 8px; font-weight: 600; color: {INK}">{e(caption)}</div></div>'
    )


def eco_section(view: dict) -> str:
    focus = view["focus"]
    rows = focus["rows"]
    heading = f"Daftar SQL {focus['product']} {view['label']}"
    intro = (
        f"{h4(heading)}"
        + muted_p(f"Hanya SQL {e(focus['product'])} pada periode report ini ({e(view['label'])} untuk report mingguan, bulan itu untuk report bulanan), diurutkan dari SQL Value terbesar.")
    )
    if not rows:
        return f'<div style="margin-top: 24px">{intro}<div style="background: #ffffff; border: 1px solid {LINE}; border-radius: 6px; padding: 20px 24px; color: {MUTED}">Tidak ada SQL {e(focus["product"])} di {e(view["label"])}.</div></div>'
    body = "".join(
        f"<tr>{td('Company', r['company'])}{td('Industry', r['industry'])}{td('Tanggal SQL', r['date'])}{td('SQL Value', idr(r['value']), True)}</tr>" for r in rows
    )
    foot = f'<tr><td colspan="3" data-label="">TOTAL {dotted(focus["count"])} SQL</td>{td("SQL Value", idr(focus["value"]), True)}</tr>'
    table = box_table(f"Daftar SQL {focus['product']} {view['label']}, diurutkan dari SQL Value terbesar", [th("Company"), th("Industry"), th("Tanggal SQL"), th("SQL Value", True, True)], body, foot)
    return f'<div style="margin-top: 24px">{intro}{table}</div>'


def company_name(bu: str, names: dict | None) -> str:
    """Display name of an internal company id such as BU1; falls back to 'Perusahaan 1' until an admin sets one."""
    key = bu.lower()
    if names and names.get(key):
        return names[key]
    digits = re.fullmatch(r"bu(\d+)", key)
    return f"Perusahaan {digits.group(1)}" if digits else bu


def progress_section(view: dict, tg: dict | None, names: dict | None = None) -> str:
    t = _tg(tg)
    p = view["progress"]
    unit = p["unit"]
    focus = view.get("focus")
    year = p["year"]
    title = f"Progress target SQL {focus['product']} {year['year']}" if focus else f"Progress target SQL Value {year['year']}"
    if focus:
        parent = f" (existing user {e(company_name(focus['parent'], names))})" if focus.get("parent") else " (existing user)"
        sub = f"Target {e(company_name(view['bu'], names))} adalah jumlah SQL dari campaign {e(focus['product'])}{parent}, dihitung sampai {e(view['label'])}. "
    else:
        sub = f"SQL Value yang sudah masuk sampai {e(view['label'])} terhadap target semester ini dan target 1 tahun. "
    parts = [f'<section aria-label="{e(title)}" style="margin-top: 24px">{h3(title)}{muted_p(sub + link_target())}']
    if t["error"]:
        parts.append(error_note(0))
    elif t["semester"] is None and t["year"] is None:
        parts.append(f'<p style="margin: 0; color: {MUTED}">Target {e(year["year"])} belum diatur. Atur di halaman Pengaturan target untuk melihat progress.</p>')
    else:
        sem = p["semester"]
        sem_title = f"{sem['label']} ({'Januari sampai Juni' if sem['key'].endswith('S1') else 'Juli sampai Desember'})"
        parts.append(
            '<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 16px">'
            + progress_card(sem_title, sem["actual"], t["semester"], unit, "semester ini", "semester")
            + progress_card(f"Akumulasi 1 tahun {year['year']} (Januari sampai Desember)", year["actual"], t["year"], unit, "akumulasi 1 tahun", "tahun")
            + "</div>"
        )
    if focus:
        parts.append(eco_section(view))
    parts.append("</section>")
    return "".join(parts)


COHORT_JS = (
    "(function(){document.querySelectorAll('[data-cohort-group]').forEach(function(g){var t=g.querySelector('[data-cohort-toggle]');"
    "function sync(){var on=t.checked;g.querySelectorAll('[data-cohort-view]').forEach(function(v){v.hidden=(v.dataset.cohortView==='same')!==on;});"
    "g.querySelectorAll('[data-cohort-note]').forEach(function(n){n.hidden=!on;});}t.addEventListener('change',sync);sync();});})();"
)


def cohort_toggle(label: str, what: str, own: str) -> str:
    """The switch above a list: off shows everything in the period, on only leads whose Inbound Date is also in the period."""
    return (
        '<div style="margin: 0 0 12px"><label style="display: inline-flex; align-items: center; gap: 10px; min-height: 44px; color: #17283e; font-weight: 500; cursor: pointer">'
        f'<input type="checkbox" role="switch" data-cohort-toggle style="width: 20px; height: 20px; margin: 0">Hanya yang submission-nya di {e(label)}</label></div>'
    )


def cohort_lists(label: str, what: str, own: str, all_html: str, same_html: str, shown: int, total: int, unit: str) -> str:
    return (
        f'<div data-cohort-group>{cohort_toggle(label, what, own)}<div data-cohort-view="all">{all_html}</div>'
        f'<div data-cohort-view="same" hidden><p style="margin: 0 0 12px; color: {TEXT}">Menampilkan {dotted(shown)} dari {dotted(total)} {e(unit)} yang submission-nya di {e(label)}.</p>{same_html}</div></div>'
    )


def sql_table(view: dict, rows: list[dict], total_value) -> str:
    label = view["label"]
    body = "".join(
        f"<tr>{td('Company', r['company'])}{td('Industry', r['industry'])}{td('Campaign', r['campaign'])}{td('SQL Value', idr(r['value']), True)}{td('Inbound ke SQL', r['timing'])}</tr>" for r in rows
    ) or f'<tr><td colspan="5" data-label="" style="color: {MUTED}">Tidak ada SQL di {e(label)}.</td></tr>'
    foot = f'<tr><td colspan="3" data-label="">TOTAL {dotted(len(rows))} SQL</td>{td("SQL Value", idr(total_value), True)}<td data-label=""></td></tr>'
    return box_table(f"Daftar SQL {label}, diurutkan dari SQL Value terbesar", [th("Company"), th("Industry"), th("Campaign"), th("SQL Value", True, True), th("Inbound ke SQL")], body, foot)


def sql_section(view: dict) -> str:
    rows = view["sql_list"]["rows"]
    label = view["label"]
    note = "Diurutkan dari SQL Value terbesar."
    if view.get("sql_note"):
        note += " " + view["sql_note"]
    table = sql_table(view, rows, view["sql_list"]["value"])
    if rows and "same" in rows[0]:
        same_rows = [r for r in rows if r["same"]]
        table = cohort_lists(label, "SQL", "SQL", table, sql_table(view, same_rows, sum(r["value"] for r in same_rows)), len(same_rows), len(rows), "SQL")
    return f'<div style="margin-top: 24px">{h3("Daftar SQL " + label)}{muted_p(e(note))}{table}</div>'


def won_table(view: dict, rows: list[dict], total_value) -> str:
    label = view["label"]
    body = "".join(
        f"<tr>{td('Company', r['company'])}{td('Industry', r['industry'])}{td('Campaign', r['campaign'])}{td('Deal Value', idr(r['value']), True)}{td('Inbound ke Deal Won', r['timing'])}</tr>" for r in rows
    ) or f'<tr><td colspan="5" data-label="" style="color: {MUTED}">Tidak ada Deal Won di {e(label)}.</td></tr>'
    foot = f'<tr><td colspan="3" data-label="">TOTAL {dotted(len(rows))} DEAL WON</td>{td("Deal Value", idr(total_value), True)}<td data-label=""></td></tr>'
    return box_table(f"Daftar Deal Won {view['bu']} {label}, diurutkan dari Deal Value terbesar", [th("Company"), th("Industry"), th("Campaign"), th("Deal Value", True, True), th("Inbound ke Deal Won")], body, foot)


def won_section(view: dict) -> str:
    won = view["won_list"]
    label = view["label"]
    head = h3("Daftar Deal Won " + label) + muted_p(e(f"Diurutkan dari Deal Value terbesar. Nilai mengikuti kolom {won['column']} di Campaign Tracker."))
    if not won["rows"]:
        return f'<div style="margin-top: 24px">{head}<div style="background: #ffffff; border: 1px solid {LINE}; border-radius: 6px; padding: 20px 24px; color: {MUTED}">Tidak ada Deal Won di {e(label)}.</div></div>'
    rows = won["rows"]
    table = won_table(view, rows, won["value"])
    if "same" in rows[0]:
        same_rows = [r for r in rows if r["same"]]
        table = cohort_lists(label, "Deal Won", "Deal Won", table, won_table(view, same_rows, sum(r["value"] for r in same_rows)), len(same_rows), len(rows), "Deal Won")
    return f'<div style="margin-top: 24px">{head}{table}</div>'


def hardware_section(view: dict, tg: dict | None, analysis: dict | None, names: dict | None = None) -> str:
    t = _tg(tg)
    hw = view["hardware"]
    month = view["month"]
    label = view["label"]
    word = "minggu" if view["kind"] == "week" else "bulan"
    count = NUMBER_WORDS.get(len(hw), str(len(hw)))
    targets = t["hardware"]
    total_target = sum((Decimal(v) for v in targets.values() if v), Decimal(0))
    mtd_total = sum(h["month_to_date"] for h in hw)
    week_total = sum(h["week"] for h in hw)
    panel = [
        f'<div style="border: 1px solid {LINE}; border-radius: 6px; padding: 20px 24px; margin-bottom: 16px">{h4("Target SQL Value " + month["label"])}'
        + muted_p(f"Menampilkan SQL Value {word} ini dan akumulasinya di bulan berjalan. Satu target per hardware; target total adalah jumlah {ALL_OF.get(len(hw), "semuanya")}.", 16)
        + link_target()
    ]
    if t["error"]:
        panel.append(error_note(16))
    elif total_target <= 0:
        panel.append(f'<p style="margin: 16px 0 0; color: {MUTED}">Target {e(month["label"])} belum diatur. Atur target di halaman Pengaturan target untuk melihat progress.</p>')
    else:
        done = percent(mtd_total, total_target)
        items = (
            (f"SQL Value {label}", idr(week_total)),
            (f"SQL Value {month['label']} sampai {label}", idr(mtd_total)),
            (f"Total target {month['label']}", idr(total_target)),
            ("Sisa target", idr(max(total_target - mtd_total, 0))),
        )
        dl = "".join(f'<div><dt style="color: {MUTED}">{e(a)}</dt><dd style="margin: 0; font-weight: 600; color: {INK}">{e(b)}</dd></div>' for a, b in items)
        panel.append(
            f'<div><dl style="margin: 20px 0 0; display: flex; flex-wrap: wrap; gap: 12px 40px">{dl}</dl>'
            f'<div style="margin-top: 16px"><div style="display: flex; justify-content: space-between; gap: 16px; margin-bottom: 6px"><span>Progress total bulan ini</span>'
            f'<span style="font-weight: 600; color: {INK}">{e(pct_text(done))} dari target</span></div><div class="track" aria-hidden="true"><div class="fill" style="width: {width(done)}"></div></div></div></div>'
        )
    panel.append("</div>")
    def hw_table(same: bool) -> str:
        mql, sql, value = ("same_mql", "same_sql", "same_value") if same else ("mql", "sql", "week")
        body = ""
        for h in hw:
            target = targets.get(h["name"])
            body += (
                f"<tr>{td('Produk', h['name'])}{td('Submission', dotted(h['submission']), True)}{td('MQL', dotted(h[mql]), True)}{td('SQL', dotted(h[sql]), True)}"
                f"{td('SQL Value', idr(h[value]), True)}{td('Target', idr(target) if target else 'Belum diatur', True)}"
                f"{td('Progress', pct_text(percent(h['month_to_date'], target)) if target else '-', True)}</tr>"
            )
        total = {k: sum(h[k] for h in hw) for k in ("submission", mql, sql)}
        shown_value = sum(h[value] for h in hw)
        foot = (
            f"<tr>{td('Produk', f'TOTAL {len(hw)} PRODUK')}{td('Submission', dotted(total['submission']), True)}{td('MQL', dotted(total[mql]), True)}{td('SQL', dotted(total[sql]), True)}"
            f"{td('SQL Value', idr(shown_value), True)}{td('Target', idr(total_target) if total_target > 0 else 'Belum diatur', True)}"
            f"{td('Progress', pct_text(percent(mtd_total, total_target)) if total_target > 0 else '-', True)}</tr>"
        )
        headers = [th("Produk"), th("Submission", True), th("MQL", True), th("SQL", True), th("SQL Value", True), th("Target", True), th("Progress", True)]
        return (
            f'<div><div class="tablebox"><table class="list"><caption class="sr">Campaign Hardware {e(label)} per produk</caption><thead><tr>{"".join(headers)}</tr></thead>'
            f"<tbody>{body}</tbody><tfoot>{foot}</tfoot></table></div></div>"
        )

    has_cohort = "same_mql" in hw[0]
    if has_cohort:
        table_html = f'<div data-cohort-view="all">{hw_table(False)}</div><div data-cohort-view="same" hidden>{hw_table(True)}</div>'
    else:
        table_html = hw_table(False)
    table = f"<div>{table_html}{analysis_box('Analysis', 'hardware_summary', analysis)}</div>"
    blocks = []
    for h in hw:
        target = targets.get(h["name"])
        top = max(h["submission"], 1)
        bars = "".join(
            f'<span>{name}</span><div class="track" aria-hidden="true"><div class="fill" style="width: {width(value / top * 100)}"></div></div><span>{dotted(value)}</span>'
            for name, value in (("Submission", h["submission"]), ("MQL", h["mql"]), ("SQL", h["sql"]), ("Deal Won", h["deal_won"]))
        )
        if target:
            before_w = max(0.0, min(100.0, percent(h["before"], target) or 0.0))
            week_w = max(0.0, min(100.0 - before_w, percent(h["week"], target) or 0.0))
            swatch = lambda style: f'<span aria-hidden="true" style="display: inline-block; width: 10px; height: 10px; {style} margin-right: 6px"></span>'
            stack = (
                f'<div><div style="display: flex; height: 16px; border-radius: 4px; overflow: hidden; background: #edf4ff" aria-hidden="true"><div style="width: {before_w:.1f}%; background: #6f8199"></div><div style="width: {week_w:.1f}%; background: {BLUE}"></div></div>'
                f'<div style="display: flex; flex-wrap: wrap; gap: 4px 20px; margin-top: 8px"><span>{swatch("background: #6f8199;")}Sebelum {e(label)} {e(idr(h["before"]))}</span>'
                f'<span>{swatch("background: " + BLUE + ";")}{e(label)} {e(idr(h["week"]))}</span>'
                f'<span>{swatch("background: #edf4ff; border: 1px solid #6f8199; box-sizing: border-box;")}Sisa target {e(idr(max(Decimal(target) - h["month_to_date"], 0)))}</span></div>'
                f'<div style="margin-top: 8px; font-weight: 600; color: {INK}">{e(pct_text(percent(h["month_to_date"], target)))} dari target {e(idr(target))}</div></div>'
            )
        else:
            stack = f'<div style="color: {MUTED}">Target {e(h["name"])} belum diatur.</div>'
        blocks.append(
            f'<div class="split" style="padding: 20px 0; border-top: 1px solid {LINE}"><div class="split-main">'
            f'<h4 style="margin: 0 0 12px; font: 600 14px/1.4 Inter, Arial, sans-serif; color: {INK}">{e(h["name"])}</h4><div class="bars">{bars}</div>'
            f'<div style="margin-top: 20px"><div style="font-weight: 600; color: {INK}; margin-bottom: 8px">SQL Value {e(month["label"])} terhadap target</div>{stack}</div></div>'
            f'{analysis_panel("Analysis " + h["name"], "hardware_" + h["slug"], analysis, f"border: 1px solid {LINE}; border-radius: 6px; padding: 16px", "split-side")}</div>'
        )
    toggle = note = ""
    if has_cohort:
        toggle = cohort_toggle(label, "MQL, SQL, dan SQL Value", "lead")
        note = (f'<p data-cohort-note hidden style="margin: 0 0 12px; color: {TEXT}">Kolom MQL, SQL, dan SQL Value hanya menghitung lead yang submission-nya di {e(label)}. '
                f'Kolom Target dan Progress tetap memakai semua SQL bulan berjalan.</p>')
    group = ("<div data-cohort-group>", "</div>") if has_cohort else ("", "")
    return (
        f'<div style="margin-top: 32px">{h3("Campaign Hardware")}{muted_p(f"{count} produk hardware di {e(company_name(view["bu"], names))}. Produk lain dan tag kosong tidak dihitung.")}'
        f'{group[0]}{toggle}{note}{"".join(panel)}{table}{group[1]}</div>'
        f'<div style="margin-top: 32px">{h3("Funnel per hardware")}'
        f'{muted_p(f"Submission, MQL, SQL, dan Deal Won {e(label)} untuk tiap produk, ditambah progress SQL Value bulan ini terhadap target produk itu.", 8)}{"".join(blocks)}</div>'
    )


def _rp(value, empty: str = "Belum diisi") -> str:
    return empty if value is None else idr(value)


def _left(value, empty: str = "Belum diisi") -> str:
    if value is None:
        return empty
    return idr(value) if value >= 0 else f"Melebihi {idr(-value)}"


def _pct(value) -> str:
    return "-" if value is None else pct_text(value)


def budget_card(label: str, value: str, compare: str) -> str:
    return (f'<div style="border: 1px solid {LINE}; border-radius: 6px; padding: 16px"><div style="color: {MUTED}">{e(label)}</div>'
            f'<div style="font: 600 22px/1.3 Inter, Arial, sans-serif; color: {INK}">{e(value)}</div><div style="color: {MUTED}">{e(compare)}</div></div>')


def budget_section(b: dict, label: str) -> str:
    """The budget block at the very top of a report. `b` comes from viewer.budget.report_budget; state is belum, gagal or ok."""
    title = f'Budget dan spend {b["month_label"]}'
    admin_link = (f'<p style="margin: 0 0 8px"><a href="/budget?bu={e(b["bu"])}&month={e(b["month"])}" style="display: inline-flex; align-items: center; min-height: 44px; font-weight: 600">Atur budget</a></p>'
                  if b.get("admin") else "")
    head = f'<h3 style="margin: 0 0 4px; font: 600 16px/1.4 Inter, Arial, sans-serif; color: {INK}">{e(title)}</h3>'
    if b["state"] == "gagal":
        return (f'<section aria-label="{e(title)}" style="margin-bottom: 24px">{head}<p role="alert" style="margin: 0; padding: 10px 12px; border-radius: 6px; background: #fcecec; color: #ac3d3d">'
                'Budget tidak bisa dimuat. Database marketing_reports tidak menjawab. Muat ulang halaman ini.</p></section>')
    if b["state"] == "belum":
        hint = "Atur di halaman Budget untuk melihat pemakaian." if b.get("admin") else "Hubungi admin untuk mengatur budget."
        return f'<section aria-label="{e(title)}" style="margin-bottom: 24px">{head}<p style="margin: 0; color: {MUTED}">Budget {e(b["month_label"])} belum diatur. {e(hint)}</p>{admin_link}</section>'
    weekly = b["kind"] == "week"
    prev, pl = b["prev"], b["prev_label"]
    cards = [budget_card("Total budget", _rp(b["total"]), f"{pl}: {_rp(prev['total'], 'Belum ada data')}")]
    if weekly:
        cards.append(budget_card(f"Spend {label}", _rp(b["week"]), f"{b['prev_week_label']}: {_rp(b['prev_week'], 'Belum diisi')}"))
    cards += [budget_card(f"Spend {b['month_label']}", _rp(b["spent"]), f"{pl}: {_rp(prev['spent'], 'Belum ada data')}"),
              budget_card("Sisa budget", _left(b["left"]), f"{pl}: {_left(prev['left'], 'Belum ada data')}")]
    used = b["used"]
    bar = (
        f'<div style="border: 1px solid {LINE}; border-radius: 6px; padding: 16px; margin-bottom: 16px"><div style="display: flex; flex-wrap: wrap; justify-content: space-between; gap: 4px 16px; margin-bottom: 8px">'
        f'<span style="color: {MUTED}">Pemakaian budget</span><span style="font: 600 18px/1.3 Inter, Arial, sans-serif; color: {INK}">{e(_pct(used))}</span></div>'
        f'<div role="progressbar" aria-label="Pemakaian budget {e(b["month_label"])}" aria-valuemin="0" aria-valuemax="100" aria-valuenow="{0 if used is None else min(100, round(used))}" '
        f'aria-valuetext="{e(_pct(used))} dari total budget terpakai" style="height: 12px; border-radius: 6px; background: {LINE}; overflow: hidden">'
        f'<div style="width: {width(used)}; height: 100%; background: {BLUE if used is None or used <= 100 else "#ac3d3d"}"></div></div>'
        f'<div style="color: {MUTED}; margin-top: 8px">{e(pl)}: {e(_pct(prev["used"]) if prev["used"] is not None else "Belum ada data")}</div></div>'
    )
    heads = [th("Campaign"), th("Budget", True)] + ([th(f"Spend {label}", True)] if weekly else []) + [th(f"Spend {b['month_label']}", True), th("Sisa", True), th("Pemakaian", True)]

    def line(name, budget, week, spent, left, pct, bold=False):
        cells = [td("Campaign", name), td("Budget", _rp(budget, "-"), True)] + ([td(f"Spend {label}", _rp(week, "-"), True)] if weekly else []) + \
                [td(f"Spend {b['month_label']}", _rp(spent, "-"), True), td("Sisa", _left(left, "-"), True), td("Pemakaian", _pct(pct), True)]
        return f"<tr>{''.join(cells)}</tr>"

    body = "".join(line(r["name"], r["budget"], r["week"], r["spent"], r["left"], r["used"]) for r in b["rows"])
    span = len(heads)
    rest = b.get("rest")
    if rest:
        body += (f'<tr>{td("Campaign", f"{dotted(rest["count"])} campaign lainnya")}{td("Budget", _rp(rest["budget"], "-"), True)}'
                 + (f'{td(f"Spend {label}", _rp(rest["week"], "-"), True)}' if weekly else "")
                 + f'{td(f"Spend {b["month_label"]}", _rp(rest["spent"], "-"), True)}<td data-label="Sisa" class="num">-</td><td data-label="Pemakaian" class="num">-</td></tr>')
    if b.get("unallocated"):
        body += f'<tr>{td("Campaign", "Belum dialokasikan ke campaign")}{td("Budget", idr(b["unallocated"]), True)}<td colspan="{span - 2}" data-label="" style="color: {MUTED}"></td></tr>'
    if not body:
        body = f'<tr><td colspan="{span}" data-label="" style="color: {MUTED}">Belum ada campaign dengan budget atau spend di {e(b["month_label"])}.</td></tr>'
    foot = line("TOTAL", b["total"], b.get("week"), b["spent"], b["left"], b["used"])
    table = box_table(f"Budget dan spend per campaign {b['month_label']}", heads, body, foot)
    note = (f'<p style="margin: 0 0 12px; color: {MUTED}; font-size: 12.5px">{e(b["month_label"])} bulan berjalan, belum penuh. Pembanding {e(pl)} adalah bulan penuh.</p>' if weekly else "")
    as_of = (f'<p style="margin: 0 0 12px; color: {MUTED}; font-size: 12.5px">Spend bulanan diisi sampai {e(b["as_of"].strftime("%d-%m-%Y"))}.</p>' if b.get("as_of") else "")
    return (f'<section aria-label="{e(title)}" style="margin-bottom: 24px">{head}{note}{as_of}{admin_link}'
            f'<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 16px; margin-bottom: 16px">{"".join(cards)}</div>{bar}{table}</section>')


def render_body(view: dict, tg: dict | None = None, analysis: dict | None = None, company: dict | None = None, budget: dict | None = None) -> str:
    m, prev = view["metrics"], view["metrics_prev"]
    pl, same_word = view["prev_label"], view["same_word"]
    names = ("Submission", "MQL", "SQL", "SQL Value", "Deal Won", "Deal Won Value")
    def rate_card(n: str) -> str:
        value, compare = idr(m[n]) if "Value" in n else dotted(m[n]), f"{pl}: " + (idr(prev[n]) if "Value" in n else dotted(prev[n]))
        base = RATES.get(n)
        if base is None:
            return card(n, value, compare)
        now_rate, prev_rate = percent(m[n], m[base]), percent(prev[n], prev[base])
        return card(n, value, compare, f"{n} Rate {pct_text(now_rate)} · {pl}: {pct_text(prev_rate)}")

    cards = "".join(rate_card(n) for n in names)
    same, same_prev = view["same"], view["same_prev"]
    totals = {"MQL": (m["MQL"], f"MQL {view['label']}"), "SQL": (m["SQL"], f"SQL {view['label']}"), "SQL Value": (m["SQL Value"], f"SQL Value {view['label']}")}
    same_cards = ""
    for name in ("MQL", "SQL", "SQL Value"):
        money = name == "SQL Value"
        total, tail = totals[name]
        share = percent(same[name], total)
        same_cards += card(f"{same_word} {name}", idr(same[name]) if money else dotted(same[name]), f"{pl}: " + (idr(same_prev[name]) if money else dotted(same_prev[name])),
                           f"{pct_text(share) if share is not None else 'N/A'} dari total {idr(total) if money else dotted(total)} {tail}")
    sections = [
        f'<div style="margin-bottom: 20px"><div style="font: 600 18px/1.3 Inter, Arial, sans-serif; color: {INK}">Performance Marketing Report</div>'
        f'<div style="color: {MUTED}">{e(view["label"])} ({e(view["range"])}) vs {e(pl)} ({e(view["prev_range"])})</div></div>',
        *([budget_section(budget, view["label"])] if budget is not None else []),
        f'<div class="cards">{cards}</div>',
        f'<div class="cards" style="margin-top: 16px">{same_cards}</div>',
        analysis_panel("Executive Summary", "executive_summary", analysis, f"margin-top: 16px; border: 1px solid {LINE}; border-radius: 6px; padding: 16px"),
        progress_section(view, tg, company),
        sql_section(view),
    ]
    if view.get("won_list"):
        sections.append(won_section(view))
    if view.get("hardware"):
        sections.append(hardware_section(view, tg, analysis, company))
    return (
        f'<section aria-label="Report"><h2 style="margin: 0 0 16px; font: 600 16px/1.4 Inter, Arial, sans-serif; color: {INK}">Report</h2>'
        f'<div style="background: #ffffff; border: 1px solid {LINE}; border-radius: 6px; padding: 24px">{"".join(sections)}</div></section>'
    )


def render_document(view: dict, tg: dict | None = None, analysis: dict | None = None, standalone: bool = True, names: dict | None = None, budget: dict | None = None) -> str:
    data = json.dumps(view, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    title = f"{company_name(view['bu'], names)} Performance Marketing Report — {view['label']} vs {view['prev_label']}"
    main_style = ' style="padding-top: 24px"' if standalone else ""
    return (
        '<!doctype html><html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{e(title)}</title><style>{CSS}</style></head><body>"
        f'<main class="rp-main"{main_style}>{render_body(view, tg, analysis, names, budget)}</main>'
        f'<script type="application/json" id="{VIEW_ID}">{data}</script><script>{COHORT_JS}</script></body></html>'
    )


_VIEW = re.compile(r'<script type="application/json" id="' + VIEW_ID + r'"[^>]*>(.*?)</script>', re.S)


def extract_view(html: str) -> dict | None:
    """The view embedded in a stored report, or None for reports made by the old generator."""
    found = _VIEW.search(html)
    if not found:
        return None
    try:
        view = json.loads(found.group(1).replace("<\\/", "</"))
    except ValueError:
        return None
    return view if isinstance(view, dict) and view.get("v") == 1 else None


def analysis_keys(view: dict) -> list[str]:
    keys = ["executive_summary"]
    if view.get("hardware"):
        keys.append("hardware_summary")
        keys.extend("hardware_" + h["slug"] for h in view["hardware"])
    return keys
