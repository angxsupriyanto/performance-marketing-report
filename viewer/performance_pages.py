"""HTML of the Performa page, following the approved mockup (Performa.dc.html)."""
from __future__ import annotations

from decimal import Decimal
from html import escape
from urllib.parse import urlencode

from viewer import pages
from viewer.performance import ERR_DAYS, ERR_ORDER, HEAT, MATRIX_COLUMNS, MATRIX_KEYS, METRICS, UNITS, compact, nice_max

W, H, LEFT, RIGHT, TOP, BOTTOM = 640, 240, 48, 620, 16, 200
INK, MUTED, LINE, BLUE = "#17283e", "#607188", "#dfe7f0", "#2159a9"
SERIES_STYLE = {  # key: (label, colour, marker shape), the same four marks as the mockup
    "sub": ("Submission", "#6f8199", "circle"), "mql": ("MQL", BLUE, "square"), "sql": ("SQL", "#087450", "diamond"), "won": ("Deal Won", INK, "triangle"),
    "sqlv": ("SQL Value", "#087450", "diamond"), "wonv": ("Deal Won Value", INK, "triangle"),
}
TINTS = ("0.18", "0.14", "0.10", "0.07", "0.04")
CSS = f"""
.pf-seg{{display:inline-flex}}
.pf-seg a{{display:inline-flex;align-items:center;justify-content:center;height:44px;padding:0 16px;border:1px solid #6f8199;background:#fff;color:{INK};font:500 14px Inter,Arial,sans-serif;text-decoration:none}}
.pf-seg a+a{{margin-left:-1px}}
.pf-seg a:first-child{{border-radius:6px 0 0 6px}}.pf-seg a:last-child{{border-radius:0 6px 6px 0}}
.pf-seg a[aria-current=true]{{background:{BLUE};border-color:{BLUE};color:#fff;font-weight:600;position:relative}}
.pf-legend{{display:flex;flex-wrap:wrap;gap:8px 24px;margin-top:12px;color:#394d65}}
.pf-chart text{{font-family:Inter,Arial,sans-serif}}
.pf-heat th.num,.pf-heat td.num{{text-align:center;min-width:64px}}
@media (max-width:680px){{.pf-heat thead{{position:static}}.pf-heat tr{{display:table-row;padding:0}}.pf-heat td,.pf-heat th{{display:table-cell;padding:12px 16px}}.pf-heat td::before{{content:none}}}}
"""


def _shape(kind: str, x: float, y: float, colour: str, title: str) -> str:
    tip = f"<title>{escape(title)}</title>"
    if kind == "circle":
        return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="{colour}">{tip}</circle>'
    if kind == "square":
        return f'<rect x="{x - 3.5:.1f}" y="{y - 3.5:.1f}" width="7" height="7" fill="{colour}">{tip}</rect>'
    if kind == "diamond":
        return f'<polygon points="{x:.1f},{y - 4.5:.1f} {x + 4.5:.1f},{y:.1f} {x:.1f},{y + 4.5:.1f} {x - 4.5:.1f},{y:.1f}" fill="{colour}">{tip}</polygon>'
    return f'<polygon points="{x:.1f},{y - 4.5:.1f} {x + 4.5:.1f},{y + 4.5:.1f} {x - 4.5:.1f},{y + 4.5:.1f}" fill="{colour}">{tip}</polygon>'


def line_chart(points: list[dict], keys: tuple[str, ...], aria: str, money: bool) -> str:
    """Server-drawn SVG line chart: one polyline with a distinct marker shape per series, gridlines at round numbers, a tooltip per point."""
    top = nice_max(max((p[k] for p in points for k in keys), default=Decimal(0)))
    n = len(points)
    xs = [(LEFT + RIGHT) / 2] if n == 1 else [LEFT + i * (RIGHT - LEFT) / (n - 1) for i in range(n)]
    y = lambda v: BOTTOM - float(v / top) * (BOTTOM - TOP)
    grid = ""
    for i in range(5):
        value = top * i / 4
        gy = BOTTOM - i * (BOTTOM - TOP) / 4
        grid += f'<line x1="{LEFT}" y1="{gy:.1f}" x2="{RIGHT}" y2="{gy:.1f}" stroke="{LINE}" stroke-width="1"/><text x="{LEFT - 6}" y="{gy + 4:.1f}" text-anchor="end" font-size="11" fill="{MUTED}">{escape(compact(value))}</text>'
    body = ""
    for key in keys:
        label, colour, shape = SERIES_STYLE[key]
        coords = " ".join(f"{x:.1f},{y(p[key]):.1f}" for x, p in zip(xs, points))
        if n > 1:
            body += f'<polyline points="{coords}" fill="none" stroke="{colour}" stroke-width="2"/>'
        for x, p in zip(xs, points):
            amount = f"Rp {int(p[key]):,}".replace(",", ".") if money else f"{int(p[key]):,}".replace(",", ".")
            body += _shape(shape, x, y(p[key]), colour, f"{label}, {p['full']}: {amount}")
    step = max(1, -(-n // 8))
    labels = "".join(
        f'<text x="{x:.1f}" y="{BOTTOM + 22}" text-anchor="middle" font-size="11" fill="{MUTED}">{escape(p["label"])}</text>'
        for i, (x, p) in enumerate(zip(xs, points)) if i % step == 0 or i == n - 1 and (n - 1) % step >= step // 2 + 1
    )
    legend = "".join(
        f'<span style="display:inline-flex;align-items:center;gap:8px"><svg width="28" height="12" viewBox="0 0 28 12" aria-hidden="true"><line x1="0" y1="6" x2="28" y2="6" stroke="{SERIES_STYLE[k][1]}" stroke-width="2"/>'
        f'{_shape(SERIES_STYLE[k][2], 14, 6, SERIES_STYLE[k][1], "")}</svg>{escape(SERIES_STYLE[k][0])}</span>' for k in keys
    )
    return (
        f'<svg class="pf-chart" viewBox="0 0 {W} {H}" role="img" aria-label="{escape(aria)}" style="width:100%;height:auto;display:block">{grid}{body}<g aria-hidden="true">{labels}</g></svg><div class="pf-legend">{legend}</div>'
    )


def data_table(points: list[dict], keys: tuple[str, ...], money: bool, caption: str) -> str:
    fmt = (lambda v: "Rp " + f"{int(v):,}".replace(",", ".")) if money else (lambda v: f"{int(v):,}".replace(",", "."))
    heads = "".join(f'<th scope="col" class="num">{escape(SERIES_STYLE[k][0])}</th>' for k in keys)
    rows = "".join(f'<tr><td data-label="Periode">{escape(p["full"])}</td>' + "".join(f'<td data-label="{escape(SERIES_STYLE[k][0])}" class="num">{escape(fmt(p[k]))}</td>' for k in keys) + "</tr>" for p in points)
    return (f'<details style="margin-top:12px"><summary style="cursor:pointer;min-height:44px;display:flex;align-items:center;color:{BLUE};font-weight:600">Lihat angka dalam tabel</summary>'
            f'<div class="vw-box" style="overflow-x:auto;margin-top:8px"><table class="vw-table"><caption class="vw-sr">{escape(caption)}</caption><thead><tr><th scope="col">Periode</th>{heads}</tr></thead><tbody>{rows}</tbody></table></div></details>')


def _rp(v) -> str:
    return "Rp " + f"{int(v):,}".replace(",", ".")


def _n(v) -> str:
    return f"{int(v):,}".replace(",", ".")


def _pct(v) -> str:
    return "N/A" if v is None else f"{v:.1f}".replace(".", ",") + "%"


def matrix_section(params, matrix: dict | None, unit: str) -> str:
    """The "Matriks cohort" block: leads counted by the period a stage happened (rows) and the period they came from (columns)."""
    _, row_what, col_what = MATRIX_KEYS[params.matriks]
    col_date = "Inbound Date" if col_what == "submission" else "MQL Date"
    note = (f"Setiap baris adalah {unit} terjadinya {row_what}. Setiap kolom adalah {unit} asal lead itu menurut {col_date}. Isi sel adalah jumlah lead. "
            f"Kolom menampilkan {MATRIX_COLUMNS} {unit} terakhir pada rentang yang dipilih; yang lebih lama digabung di kolom Lebih lama. Kolom paling kanan adalah total tiap baris.")
    options = "".join(f'<option value="{k}"{" selected" if k == params.matriks else ""}>{escape(v[0])}</option>' for k, v in MATRIX_KEYS.items())
    head = (f'<section aria-label="Matriks cohort" style="margin-top:32px"><h2 class="vw-h2">Matriks cohort</h2><p style="margin:0 0 16px;max-width:760px;color:{MUTED}">{escape(note)}</p>'
            f'<div class="vw-field" style="max-width:280px;margin-bottom:16px"><label for="matriks">Matriks yang ditampilkan</label><select id="matriks" name="matriks" form="perf-form" data-auto>{options}</select></div>')
    if matrix is None:
        return head + ('<div class="vw-box" style="padding:24px"><div style="font-weight:600;color:#17283e;margin-bottom:4px">Matriks tersedia per Minggu atau Bulan</div>'
                       '<div>Pilih Minggu atau Bulan pada Pengaturan tampilan di atas. Per hari, kolomnya terlalu banyak untuk dibaca.</div></div></section>')
    if matrix["missing"]:
        return head + ('<div class="vw-box" style="padding:24px"><div style="font-weight:600;color:#17283e;margin-bottom:4px">Matriks belum ada di data ini</div>'
                       '<div>Data Performa ini dibuat sebelum matriks tersedia. Jalankan workflow Performa Generate di n8n lagi, lalu muat ulang halaman ini.</div></div></section>')
    row_head = ("Bulan " if params.per == "bulan" else "Minggu ") + row_what
    col_head = ("Bulan " if params.per == "bulan" else "Minggu ") + col_what
    col_ths = "".join(f'<th scope="col" class="num">{escape(c)}</th>' for c in matrix["columns"]) + '<th scope="col" class="num">Lebih lama</th><th scope="col" class="num">Total baris</th>'
    body = ""
    for row in matrix["rows"]:
        cells = "".join(
            f'<td data-label="{escape(col)}" class="num"' + (f' style="background:{c["bg"]};color:#17283e;font-weight:500"' if c["n"] else "") + f'>{c["n"] if c["n"] else ""}</td>'
            for col, c in zip(matrix["columns"], row["cells"])
        )
        body += (f'<tr><th scope="row" style="font-weight:400;color:#17283e;text-align:left;padding:12px 16px;border-top:1px solid {LINE};white-space:nowrap">{escape(row["label"])}</th>{cells}'
                 f'<td class="num">{row["older"] if row["older"] else ""}</td><td class="num" style="font-weight:600;color:#17283e">{row["total"]}</td></tr>')
    labels = ("1 lead", "2", "3", "4 sampai 5", "6 atau lebih")
    swatches = [(HEAT[4][1], labels[0]), (HEAT[3][1], labels[1]), (HEAT[2][1], labels[2]), (HEAT[1][1], labels[3]), (HEAT[0][1], labels[4])]
    legend = "".join(f'<span><span style="display:inline-block;width:14px;height:14px;border:1px solid #6f8199;border-radius:3px;margin-right:6px;vertical-align:-2px;background:{c}"></span>{escape(t)}</span>' for c, t in swatches)
    cut = f'<p style="margin:12px 0 0;color:{MUTED}">Menampilkan 60 baris terbaru. Persempit rentang untuk melihat yang lebih lama.</p>' if matrix["truncated"] else ""
    caption = f'Matriks cohort {"Submission" if col_what == "submission" else "MQL"} ke {row_what} per {unit}'
    return (head + f'<div class="vw-box" style="overflow-x:auto"><table class="vw-table pf-heat"><caption class="vw-sr">{escape(caption)}</caption><thead>'
            f'<tr><th scope="col" rowspan="2" style="vertical-align:bottom">{escape(row_head)}</th><th scope="colgroup" colspan="{MATRIX_COLUMNS + 2}" style="text-align:right;background:#edf4ff;color:#17283e;font-weight:600">{escape(col_head)}</th></tr>'
            f'<tr>{col_ths}</tr></thead><tbody>{body}</tbody></table></div><div class="pf-legend" style="color:#394d65">{legend}</div>'
            f'<p style="margin:12px 0 0;color:{MUTED}">Sel kosong berarti tidak ada lead. Warna hanya membantu membaca; angka tetap tertulis di tiap sel. Kolom paling kanan adalah total baris: jumlah semua kolom di baris itu, termasuk Lebih lama.</p>{cut}</section>')


def performance_page(*, names: dict, bu: str, choices: list[str], params, state: str, snapshot: dict | None, points: list[dict], totals: dict | None, cohort: list[dict],
                     csrf: str, nonce: str, me: dict, matrix: dict | None = None) -> str:
    """state: ok, belum (no snapshot yet), kosong (nothing in the range), error (date or database problem), gagal (database did not answer)."""
    label = names.get(bu, bu)
    unit = {"hari": "hari", "minggu": "minggu", "bulan": "bulan"}[params.per]

    def link(per: str) -> str:
        q = {"bu": bu, "per": per, "metrik": params.metrik, "matriks": params.matriks}
        return "/performa?" + urlencode(q)

    seg = "".join(f'<a href="{escape(link(p))}"' + (' aria-current="true"' if p == params.per else "") + f">{p.capitalize()}</a>" for p in UNITS)
    if len(choices) > 1:
        company = ('<div class="vw-field" style="flex:0 1 200px"><label for="bu">Perusahaan</label><select id="bu" name="bu" form="perf-form" data-auto>'
                   + "".join(f'<option value="{escape(b)}"{" selected" if b == bu else ""}>{escape(names.get(b, b))}</option>' for b in choices) + "</select></div>")
    else:
        company = (f'<div class="vw-field" style="flex:0 1 200px"><span style="color:{INK};font-weight:500;margin-bottom:6px">Perusahaan</span>'
                   f'<span style="display:flex;align-items:center;height:44px;font-weight:600;color:{INK}">{escape(label)}</span><input type="hidden" name="bu" value="{escape(bu)}" form="perf-form"></div>')
    err = params.error
    invalid = ' aria-invalid="true"' if err == ERR_ORDER else ""
    settings = (
        '<section aria-label="Pengaturan tampilan" class="vw-box" style="padding:20px 24px;margin-bottom:24px">'
        f'<form id="perf-form" method="get" action="/performa" style="display:flex;flex-wrap:wrap;gap:16px;align-items:flex-end">{company}'
        f'<div class="vw-field" style="flex:0 1 180px"><label for="dari">Dari</label><input id="dari" name="from" type="date" value="{params.start.isoformat()}" data-auto{invalid}></div>'
        f'<div class="vw-field" style="flex:0 1 180px"><label for="sampai">Sampai</label><input id="sampai" name="to" type="date" value="{params.end.isoformat()}" data-auto{invalid}></div>'
        f'<input type="hidden" name="per" value="{params.per}">' + ("" if state == "ok" else f'<input type="hidden" name="metrik" value="{params.metrik}"><input type="hidden" name="matriks" value="{params.matriks}">') +
        '<noscript><button class="vw-btn" type="submit">Terapkan</button></noscript>'
        f'<div><div class="vw-field"><span id="gran-label" style="font-weight:500;color:{INK};margin-bottom:6px">Per</span></div><div class="pf-seg" role="group" aria-labelledby="gran-label">{seg}</div></div></form>'
        + (f'<p role="alert" class="vw-alert" style="margin:16px 0 0">{escape(err)}</p>' if err else "") + "</section>"
    )
    head = (
        '<main class="vw-main"><nav class="vw-crumbs" aria-label="Posisi halaman"><a class="vw-link" href="/">Daftar report</a><span class="sep" aria-hidden="true">/</span><span aria-current="page" style="color:#17283e">Performa</span></nav>'
        '<h1 class="vw-h1">Performa</h1><p class="vw-lead" style="max-width:680px">Submission, MQL, SQL, dan Deal Won beserta nilainya pada rentang tanggal yang Anda pilih, per hari, minggu, atau bulan. '
        'Cohort di bawahnya menunjukkan seberapa cepat lead dari satu periode submission menjadi MQL dan SQL.</p>'
    )
    freshness = ""
    if snapshot:
        day = snapshot["as_of"]
        freshness = (f'<p style="margin:0 0 16px;color:{MUTED}">Data per {day.day} {pages.MONTHS[day.month - 1]} {day.year}, dihitung {escape(pages.dt_text(snapshot["generated_at"]))}. '
                     "Memperbarui: jalankan workflow Performa Generate di n8n.</p>")
    if state == "gagal":
        body = (f'<div role="alert" style="background:#fcecec;border:1px solid #ac3d3d;border-radius:6px;padding:32px"><h2 class="vw-h2" style="color:#ac3d3d;margin-bottom:8px">Data performa tidak bisa dimuat</h2>'
                '<p style="margin:0 0 16px;color:#17283e">Database marketing_reports tidak menjawab. Coba lagi.</p><a class="vw-link" href="/performa" style="font-weight:600">Coba lagi</a></div>')
    elif state == "belum":
        hint = "Jalankan workflow Performa Generate di n8n, lalu muat ulang halaman ini." if me["role"] == "admin" else "Hubungi admin untuk menjalankannya."
        body = f'<div class="vw-box" style="padding:32px"><h2 class="vw-h2" style="margin-bottom:8px">Belum ada data performa untuk {escape(label)}</h2><p style="margin:0">{escape(hint)}</p></div>'
    elif state == "error":
        body = ""
    elif state == "kosong":
        body = '<div class="vw-box" style="padding:32px"><h2 class="vw-h2" style="margin-bottom:8px">Tidak ada data pada rentang ini</h2><p style="margin:0">Ubah rentang tanggal atau pilih perusahaan lain.</p></div>'
    else:
        volume_keys, value_keys = ("sub", "mql", "sql", "won"), ("sqlv", "wonv")
        summary_rows = (
            ("Submission", _n(totals["sub"]), ""), ("MQL", _n(totals["mql"]), f'MQL Rate {_pct(totals["mql_rate"])}'), ("SQL", _n(totals["sql"]), f'SQL Rate {_pct(totals["sql_rate"])}'),
            ("SQL Value", _rp(totals["sqlv"]), ""), ("Deal Won", _n(totals["won"]), f'Deal Won Rate {_pct(totals["won_rate"])}'), ("Deal Won Value", _rp(totals["wonv"]), ""),
        )
        srows = "".join(f'<tr><td data-label="Metrik">{m}</td><td data-label="Total" class="num">{t}</td><td data-label="Rate">{escape(r)}</td></tr>' for m, t, r in summary_rows)
        _, base_label, target_label = METRICS[params.metrik]
        cohort_note = (f"Setiap baris adalah lead yang submission-nya jatuh pada {unit} itu. Kolom menunjukkan berapa persen dari {base_label} cohort tersebut yang sudah menjadi {target_label} "
                       f"pada {unit} yang sama, lalu 1, 2, 3, dan 4 {unit} kemudian.")
        crows = ""
        for row in cohort:
            cells = "".join(
                f'<td data-label="{"Periode yang sama" if k == 0 else f"+{k} {unit}"}" class="num"' + (f' style="background:rgba(33,89,169,{TINTS[k]})"' if v is not None else "") + f'>{"-" if v is None else escape(_pct(v))}</td>'
                for k, v in enumerate(row["cells"])
            )
            crows += f'<tr><td data-label="Cohort submission">{escape(row["label"])}</td><td data-label="{escape(base_label)}" class="num">{_n(row["base"])}</td>{cells}</tr>'
        metric_options = "".join(f'<option value="{k}"{" selected" if k == params.metrik else ""}>{escape(v[0])}</option>' for k, v in METRICS.items())
        cohort_html = (
            f'<section aria-label="Cohort"><h2 class="vw-h2">Cohort konversi</h2><p style="margin:0 0 16px;max-width:760px;color:{MUTED}">{escape(cohort_note)}</p>'
            f'<div class="vw-field" style="max-width:280px;margin-bottom:16px"><label for="metrik">Konversi yang dinilai</label><select id="metrik" name="metrik" form="perf-form" data-auto>{metric_options}</select></div>'
            + (f'<div class="vw-box" style="overflow-x:auto"><table class="vw-table"><caption class="vw-sr">Cohort {escape(base_label)} ke {escape(target_label)} per {unit}</caption><thead><tr><th scope="col">Cohort submission</th>'
               f'<th scope="col" class="num">{escape(base_label)}</th><th scope="col" class="num">Periode yang sama</th>' + "".join(f'<th scope="col" class="num">+{k} {unit}</th>' for k in range(1, 5))
               + f"</tr></thead><tbody>{crows}</tbody></table></div>" if cohort else f'<div class="vw-box" style="padding:24px">Belum ada cohort yang periodenya dimulai di rentang ini.</div>')
            + f'<p style="margin:12px 0 0;color:{MUTED}">Tanda "-" berarti periode itu belum berjalan, jadi belum bisa dinilai. Persen bersifat kumulatif: lead yang sudah menjadi MQL atau SQL pada periode itu atau sebelumnya. '
            "Cohort memuat periode yang tanggal awalnya ada di rentang.</p></section>"
        )
        body = (
            f'<section aria-label="Volume" class="vw-box" style="padding:24px;margin-bottom:24px"><h2 class="vw-h2" style="margin-bottom:12px">Volume per {unit}</h2>'
            + line_chart(points, volume_keys, f"Grafik garis jumlah Submission, MQL, SQL, dan Deal Won per {unit}", False)
            + data_table(points, volume_keys, False, f"Jumlah per {unit}") + "</section>"
            f'<section aria-label="Nilai" class="vw-box" style="padding:24px;margin-bottom:24px"><h2 class="vw-h2" style="margin-bottom:12px">Nilai per {unit}</h2>'
            + line_chart(points, value_keys, f"Grafik garis SQL Value dan Deal Won Value per {unit}", True)
            + data_table(points, value_keys, True, f"Nilai per {unit}") + "</section>"
            f'<section aria-label="Ringkasan periode" style="margin-bottom:32px"><h2 class="vw-h2">Ringkasan rentang</h2><p style="margin:0 0 12px;color:{MUTED}">Total seluruh rentang yang dipilih, sebagai pendamping grafik. '
            "Minggu atau bulan di tepi rentang hanya menghitung hari di dalam rentang.</p>"
            f'<div class="vw-box"><table class="vw-table"><caption class="vw-sr">Ringkasan performa pada rentang yang dipilih</caption><thead><tr><th scope="col">Metrik</th><th scope="col" class="num">Total</th><th scope="col">Rate</th></tr></thead><tbody>{srows}</tbody></table></div></section>'
            + cohort_html + matrix_section(params, matrix, unit)
        )
    script = (f'<script nonce="{nonce}">document.querySelectorAll("[data-auto]").forEach(function(e){{e.addEventListener("change",function(){{'
              'document.getElementById("perf-form").requestSubmit();});});</script>')
    return pages.page("Performa", f"<style nonce=\"{nonce}\">{CSS}</style>" + head + settings + freshness + body + "</main>", nonce, csrf, pages.menu(csrf, me, "performa"), script)
