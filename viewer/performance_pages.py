"""HTML of the Performa page, following the approved mockup (Performa.dc.html): a sticky sidebar with the display settings and the six
filters, a "Menampilkan" box with the active filters, the charts, the range summary and the cohort matrices."""
from __future__ import annotations

from decimal import Decimal
from html import escape
from urllib.parse import urlencode

from viewer import cascade, pages
from viewer.performance import DIMENSIONS, ERR_DAYS, ERR_ORDER, HEAT, MATRIX_COLUMNS, MATRIX_KEYS, UNITS, compact, nice_max

W, H, LEFT, RIGHT, TOP, BOTTOM = 640, 240, 48, 620, 16, 200
INK, MUTED, LINE, BLUE = "#17283e", "#607188", "#dfe7f0", "#2159a9"
SERIES_STYLE = {  # key: (label, colour, marker shape), the same four marks as the mockup
    "sub": ("Submission", "#6f8199", "circle"), "mql": ("MQL", BLUE, "square"), "sql": ("SQL", "#087450", "diamond"), "won": ("Deal Won", INK, "triangle"),
    "sqlv": ("SQL Value", "#087450", "diamond"), "wonv": ("Deal Won Value", INK, "triangle"),
}
CSS = f"""
.pf-layout{{display:grid;grid-template-columns:288px minmax(0,1fr);gap:24px;align-items:start}}
.pf-side{{position:sticky;top:16px;max-height:calc(100vh - 32px);overflow-y:auto;padding:20px;box-sizing:border-box}}
.pf-content{{min-width:0}}
.pf-actions{{display:flex;flex-direction:column;gap:4px;margin-top:16px;position:sticky;bottom:-20px;padding:12px 0 4px;background:#fff}}
.pf-seg{{display:flex}}
.pf-seg label{{flex:1;position:relative;display:block}}
.pf-seg input{{position:absolute;opacity:0;inset:0;width:100%;height:100%;margin:0;cursor:pointer}}
.pf-seg span{{display:flex;align-items:center;justify-content:center;height:44px;padding:0 8px;border:1px solid #6f8199;background:#fff;color:{INK};font:500 14px Inter,Arial,sans-serif}}
.pf-seg label+label span{{margin-left:-1px}}
.pf-seg label:first-child span{{border-radius:6px 0 0 6px}}.pf-seg label:last-child span{{border-radius:0 6px 6px 0}}
.pf-seg input:checked+span{{background:{BLUE};border-color:{BLUE};color:#fff;font-weight:600}}
.pf-seg input:focus-visible+span{{outline:2px solid {BLUE};outline-offset:2px}}
.pf-dd summary{{display:flex;align-items:center;justify-content:space-between;gap:8px;min-height:44px;box-sizing:border-box;padding:0 12px;border:1px solid #6f8199;border-radius:6px;background:#fff;color:{INK};cursor:pointer;list-style:none}}
.pf-dd summary::-webkit-details-marker{{display:none}}
.pf-dd summary::after{{content:"";width:8px;height:8px;border-right:2px solid {MUTED};border-bottom:2px solid {MUTED};transform:rotate(45deg);margin:-4px 0 0 4px;flex:none}}
.pf-dd[open] summary::after{{transform:rotate(-135deg);margin-top:4px}}
.pf-dd .fl{{font-weight:500;flex:1}}.pf-dd .fv{{color:{MUTED}}}
.pf-panel{{margin-top:6px;border:1px solid {LINE};border-radius:6px;background:#fff;padding:4px 12px;max-height:260px;overflow-y:auto}}
.pf-panel.s{{padding-top:0;max-height:none;overflow:visible}}
.pf-find{{padding:8px 0 4px;background:#fff}}
.pf-find input{{width:100%;height:44px;box-sizing:border-box;padding:0 12px;border:1px solid #6f8199;border-radius:6px;background:#fff;color:{INK};font:14px Inter,Arial,sans-serif}}
.pf-note{{margin:4px 0;color:{MUTED}}}
.pf-scroll{{max-height:220px;overflow-y:auto}}
.pf-grp{{margin-top:6px;padding-top:6px;border-top:1px solid {LINE};color:{MUTED};font-weight:600}}.pf-grp:first-child{{border-top:0;margin-top:0}}
.pf-empty{{margin:8px 0;color:#394d65}}
.pf-opt{{display:flex;align-items:center;gap:10px;min-height:44px;color:{INK};cursor:pointer}}
.pf-opt input{{width:20px;height:20px;margin:0;flex:none}}
.pf-opt .t{{flex:1;min-width:0;overflow-wrap:anywhere}}.pf-opt .n{{color:{MUTED}}}
.pf-chips{{display:flex;flex-wrap:wrap;gap:8px;list-style:none;margin:0;padding:0}}
.pf-chip{{display:inline-flex;align-items:center;min-height:32px;padding:0 4px 0 12px;border:1px solid #6f8199;border-radius:16px;background:#edf4ff;color:{INK};font-weight:500}}
.pf-chip a{{display:inline-flex;align-items:center;justify-content:center;width:32px;height:32px;border-radius:16px;color:{INK};text-decoration:none;font:600 18px/1 Inter,Arial,sans-serif}}
.pf-legend{{display:flex;flex-wrap:wrap;gap:8px 24px;margin-top:12px;color:#394d65}}
.pf-chart text{{font-family:Inter,Arial,sans-serif}}
.pf-heat th.num,.pf-heat td.num{{text-align:center;min-width:64px}}
.pf-heat thead th{{background:#fff}}
.pf-heat .older{{min-width:88px;white-space:nowrap}}
.pf-heat .stick-l{{position:sticky;left:0;z-index:2;background:#fff;min-width:104px;white-space:nowrap}}
.pf-heat .stick-r{{position:sticky;right:0;z-index:2;background:#fff;box-shadow:-1px 0 0 {LINE}}}
.pf-heat .grp-th{{background:#edf4ff!important;text-align:left}}
.pf-heat .grp{{position:sticky;left:120px;display:inline-block;color:{INK};font-weight:600}}
@media (max-width:1000px){{.pf-layout{{grid-template-columns:1fr}}.pf-side{{position:static;max-height:none}}.pf-actions{{position:static}}}}
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


def query_for(bu: str, params, drop: tuple[str, str] | None = None, keep_filters: bool = True) -> str:
    """The address of this page for the current choices; `drop` removes one chosen filter value (a chip), keep_filters=False removes all."""
    pairs = [("bu", bu), ("from", params.start.isoformat()), ("to", params.end.isoformat()), ("per", params.per), ("matriks", params.matriks)]
    if keep_filters:
        for key, _ in DIMENSIONS:
            pairs += [(key, v) for v in params.filters.get(key, []) if drop != (key, v)]
    return "/performa?" + urlencode(pairs)


def _date_text(day) -> str:
    return f"{day.day} {pages.MONTHS[day.month - 1]} {day.year}"


def matrix_section(params, matrix: dict | None, unit: str) -> str:
    """The "Matriks cohort" block: leads counted by the period a stage happened (rows) and the period they came from (columns)."""
    _, row_what, col_what = MATRIX_KEYS[params.matriks]
    options = "".join(f'<option value="{k}"{" selected" if k == params.matriks else ""}>{escape(v[0])}</option>' for k, v in MATRIX_KEYS.items())
    head = (f'<section aria-label="Matriks cohort"><h2 class="vw-h2" style="margin-bottom:16px">Matriks cohort</h2>'
            f'<div class="vw-field" style="max-width:280px;margin-bottom:16px"><label for="matriks">Matriks yang ditampilkan</label><select id="matriks" name="matriks" form="perf-form" data-auto>{options}</select></div>')
    if matrix is None:
        return head + ('<div class="vw-box" style="padding:24px"><div style="font-weight:600;color:#17283e;margin-bottom:4px">Matriks tersedia per Minggu atau Bulan</div>'
                       '<div>Pilih Minggu atau Bulan pada Tampilan di sebelah kiri. Per hari, kolomnya terlalu banyak untuk dibaca.</div></div></section>')
    prefix = "Bulan " if params.per == "bulan" else "Minggu "
    col_ths = "".join(f'<th scope="col" class="num">{escape(c)}</th>' for c in matrix["columns"]) + '<th scope="col" class="num older">Lebih lama</th><th scope="col" class="num stick-r">Total baris</th>'
    body = ""
    for row in matrix["rows"]:
        cells = "".join(
            f'<td data-label="{escape(col)}" class="num"' + (f' style="background:{c["bg"]};color:#17283e;font-weight:500"' if c["n"] else "") + f'>{c["n"] if c["n"] else ""}</td>'
            for col, c in zip(matrix["columns"], row["cells"])
        )
        body += (f'<tr><th scope="row" class="stick-l" style="font-weight:400;color:#17283e;text-align:left;padding:12px 16px;border-top:1px solid {LINE}">{escape(row["label"])}</th>{cells}'
                 f'<td class="num older">{row["older"] if row["older"] else ""}</td><td class="num stick-r" style="font-weight:600;color:#17283e">{row["total"]}</td></tr>')
    labels = ("1 lead", "2", "3", "4 sampai 5", "6 atau lebih")
    swatches = [(HEAT[4][1], labels[0]), (HEAT[3][1], labels[1]), (HEAT[2][1], labels[2]), (HEAT[1][1], labels[3]), (HEAT[0][1], labels[4])]
    legend = "".join(f'<span><span style="display:inline-block;width:14px;height:14px;border:1px solid #6f8199;border-radius:3px;margin-right:6px;vertical-align:-2px;background:{c}"></span>{escape(t)}</span>' for c, t in swatches)
    cut = f'<p style="margin:12px 0 0;color:{MUTED}">Menampilkan 60 baris terbaru. Persempit rentang untuk melihat yang lebih lama.</p>' if matrix["truncated"] else ""
    caption = f'Matriks cohort {"Submission" if col_what == "submission" else "MQL"} ke {row_what} per {unit}'
    return (head + f'<div class="vw-box" style="overflow-x:auto"><table class="vw-table pf-heat"><caption class="vw-sr">{escape(caption)}</caption><thead>'
            f'<tr><th scope="col" rowspan="2" class="stick-l" style="vertical-align:bottom">{escape(prefix + row_what)}</th><th scope="colgroup" colspan="{MATRIX_COLUMNS + 2}" class="grp-th"><span class="grp">{escape(prefix + col_what)}</span></th></tr>'
            f'<tr>{col_ths}</tr></thead><tbody>{body}</tbody></table></div><div class="pf-legend" style="color:#394d65">{legend}</div>'
            f'<p style="margin:12px 0 0;color:{MUTED}">Sel kosong berarti tidak ada lead. Warna hanya membantu membaca; angka tetap tertulis di tiap sel. Kolom paling kanan adalah total baris: jumlah semua kolom di baris itu, termasuk Lebih lama.</p>{cut}</section>')


SIDEBAR_JS = r"""
(function(){
  var f=document.getElementById('perf-form'),note=document.getElementById('pf-dirty'),dropBox=document.getElementById('pf-drop'),relEl=document.getElementById('pf-rel');
  __CASCADE__
  var casc=relEl?makeCascade(JSON.parse(relEl.textContent)):null;
  var opts=[].slice.call(f.querySelectorAll('[data-opt]')).filter(function(o){return ['channel','source','medium','campaign'].indexOf(o.dataset.key)>=0;}),find=f.querySelector('[data-find]');
  function norm(t){return t.toLowerCase().replace(/\s+/g,' ').trim();}
  function count(d){var n=d.querySelectorAll('input[type=checkbox]:checked').length;d.querySelector('.fv').textContent=n?n+' dipilih':'Semua';}
  function refresh(){
    var r=casc?casc(opts):{dropped:0,hints:{}};
    f.querySelectorAll('[data-hint]').forEach(function(h){var t=r.hints[h.dataset.hint]||'';h.textContent=t;h.hidden=!t;});
    var q=find?find.querySelector('input[type=search]'):null,v=q?norm(q.value):'',shown=0,hit=0,total=0;
    opts.forEach(function(o){
      var cut=o.dataset.cut==='1',on=o.querySelector('input').checked;
      if(o.dataset.key!=='campaign'){o.hidden=cut;return;}
      var m=!v||norm(o.querySelector('.t').textContent).indexOf(v)>=0;
      o.hidden=cut||!(on||m);if(!cut){total++;if(m&&!on)hit++;}if(!o.hidden)shown++;
    });
    if(find){
      var k=find.querySelectorAll('.pf-opt input:checked').length;
      find.querySelector('.pf-note').textContent=v?hit+' campaign cocok dari '+total+(k?'. '+k+' dipilih tetap tampil.':'.'):total+' campaign';
      find.querySelector('.pf-empty').hidden=!v||hit>0;
    }
    f.querySelectorAll('details').forEach(count);
    if(dropBox){dropBox.hidden=!r.dropped;dropBox.textContent=r.dropped?r.dropped+' pilihan dilepas karena tidak cocok dengan Channel, Source, atau Medium yang dipilih.':'';}
    return r;
  }
  f.addEventListener('change',function(e){if(e.target.closest('details')&&note)note.hidden=false;refresh();});
  if(find){var q0=find.querySelector('input[type=search]');q0.addEventListener('input',refresh);q0.addEventListener('keydown',function(e){if(e.key==='Enter')e.preventDefault();});}
  if(refresh().dropped&&note)note.hidden=false;
  document.querySelectorAll('[data-auto]').forEach(function(el){el.addEventListener('change',function(){f.requestSubmit();});});
})();
"""


def sidebar(*, names: dict, bu: str, choices: list[str], params, state: str, option_lists: dict | None) -> str:
    label = names.get(bu, bu)
    if len(choices) > 1:
        company = ('<div class="vw-field"><label for="bu">Perusahaan</label><select id="bu" name="bu">'
                   + "".join(f'<option value="{escape(b)}"{" selected" if b == bu else ""}>{escape(names.get(b, b))}</option>' for b in choices) + "</select></div>")
    else:
        company = (f'<div class="vw-field"><span style="color:{INK};font-weight:500;margin-bottom:6px">Perusahaan</span>'
                   f'<span style="display:flex;align-items:center;height:44px;font-weight:600;color:{INK}">{escape(label)}</span><input type="hidden" name="bu" value="{escape(bu)}"></div>')
    invalid = ' aria-invalid="true"' if params.error == ERR_ORDER else ""
    seg = "".join(f'<label><input type="radio" name="per" value="{p}"' + (" checked" if p == params.per else "") + f"><span>{p.capitalize()}</span></label>" for p in UNITS)
    can_filter = option_lists is not None
    hint = lambda k: f'<div class="pf-note" data-hint="{k}" hidden></div>' if k in ("source", "medium", "campaign") else ""
    dropdowns = ""
    for key, title in DIMENSIONS:
        rows = (option_lists or {}).get(key, [])
        chosen = len(params.filters.get(key, []))
        items = "".join(
            f'<label class="pf-opt" data-opt data-key="{key}" data-label="{escape(r["value"])}"><input type="checkbox" name="{key}" value="{escape(r["value"])}"' + (" checked" if r["selected"] else "") + f'><span class="t">{escape(r["value"])}</span><span class="n">{_n(r["count"])} lead</span></label>'
            for r in rows
        ) or f'<div style="padding:12px 0;color:{MUTED}">Tidak ada nilai.</div>'
        if key == "campaign" and rows:
            picked = [r for r in rows if r["selected"]]
            rest = [r for r in rows if not r["selected"]]
            opt = lambda r: (f'<label class="pf-opt" data-opt data-key="{key}" data-label="{escape(r["value"])}"><input type="checkbox" name="{key}" value="{escape(r["value"])}"' + (" checked" if r["selected"] else "")
                             + f'><span class="t">{escape(r["value"])}</span><span class="n">{_n(r["count"])} lead</span></label>')
            groups = ((f'<div class="pf-grp">Dipilih</div>{"".join(opt(r) for r in picked)}<div class="pf-grp">Lainnya</div>' if picked else "") + "".join(opt(r) for r in rest))
            dropdowns += (f'<details class="pf-dd"><summary><span class="fl">{escape(title)}</span><span class="fv">{f"{chosen} dipilih" if chosen else "Semua"}</span></summary>'
                          f'<div class="pf-panel s" data-find><div class="pf-find"><label class="vw-sr" for="cari-campaign">Cari campaign</label>'
                          f'<input id="cari-campaign" type="search" placeholder="Cari campaign" autocomplete="off"><div class="pf-note" role="status" aria-live="polite">{len(rows)} campaign</div>{hint(key)}</div>'
                          f'<div class="pf-scroll">{groups}<p class="pf-empty" hidden>Tidak ada campaign yang cocok dengan kata kunci ini.</p></div></div></details>')
            continue
        dropdowns += (f'<details class="pf-dd"><summary><span class="fl">{escape(title)}</span><span class="fv">{f"{chosen} dipilih" if chosen else "Semua"}</span></summary>'
                      f'<div class="pf-panel">{hint(key)}{items}</div></details>')
    note = ""
    if not can_filter:
        note = (f'<div role="status" style="padding:10px 12px;border-radius:6px;background:#edf4ff;color:{INK};margin-bottom:12px">Filter belum tersedia di data ini. '
                "Jalankan workflow Performa Generate di n8n lagi, lalu muat ulang halaman ini.</div>")
    clear = f'<a class="vw-link" href="{escape(query_for(bu, params, keep_filters=False))}" style="font-weight:600">Hapus semua filter</a>' if params.active else ""
    return (
        '<aside aria-label="Tampilan dan filter" class="vw-box pf-side">'
        f'<form id="perf-form" method="get" action="/performa"><h2 class="vw-h2" style="margin-bottom:12px">Tampilan</h2>'
        f'<div style="display:flex;flex-direction:column;gap:12px">{company}'
        f'<div class="vw-field"><label for="dari">Dari</label><input id="dari" name="from" type="date" value="{params.start.isoformat()}"{invalid}></div>'
        f'<div class="vw-field"><label for="sampai">Sampai</label><input id="sampai" name="to" type="date" value="{params.end.isoformat()}"{invalid}></div>'
        f'<div><div id="gran-label" style="font-weight:500;color:{INK};margin-bottom:6px">Per</div><div class="pf-seg" role="radiogroup" aria-labelledby="gran-label">{seg}</div></div></div>'
        + (f'<p role="alert" class="vw-alert" style="margin:12px 0 0">{escape(params.error)}</p>' if params.error else "")
        + f'<h2 class="vw-h2" style="margin:24px 0 12px;padding-top:20px;border-top:1px solid {LINE}">Filter</h2>{note}<div id="pf-drop" role="status" aria-live="polite" hidden style="padding:10px 12px;border-radius:6px;background:#edf4ff;color:{INK};margin-bottom:12px"></div>'
        f'<fieldset style="border:0;margin:0;padding:0;min-width:0"{"" if can_filter else " disabled"}><legend class="vw-sr">Pilih nilai untuk tiap filter</legend>'
        f'<div style="display:flex;flex-direction:column;gap:8px">{dropdowns}</div></fieldset>'
        + ("" if state == "ok" else f'<input type="hidden" name="matriks" value="{params.matriks}">') +
        '<div class="pf-actions"><button class="vw-btn" type="submit" style="width:100%">Terapkan</button>'
        f'<div style="display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:0 12px">{clear}<span id="pf-dirty" role="status" hidden style="color:{MUTED}">Belum diterapkan.</span></div></div></form></aside>'
    )


def context_box(*, names: dict, bu: str, params) -> str:
    unit = params.per
    line = f"{names.get(bu, bu)} · {_date_text(params.start)} sampai {_date_text(params.end)} · per {unit}"
    chips = ""
    if params.active:
        items = "".join(
            f'<li><span class="pf-chip">{escape(title)}: {escape(v)}<a href="{escape(query_for(bu, params, drop=(key, v)))}" aria-label="Hapus filter {escape(title)}: {escape(v)}">&times;</a></span></li>'
            for key, title in DIMENSIONS for v in params.filters.get(key, [])
        )
        chips = f'<div style="margin-top:10px"><div id="aktif-label" style="font-weight:500;color:{INK};margin-bottom:6px">Filter aktif</div><ul class="pf-chips" aria-labelledby="aktif-label">{items}</ul></div>'
    return (f'<div class="vw-box" aria-label="Data yang sedang ditampilkan" style="padding:14px 20px;margin-bottom:24px"><div style="color:{MUTED}">Menampilkan</div>'
            f'<div style="font-weight:600;color:{INK}">{escape(line)}</div>{chips}</div>')


def performance_page(*, names: dict, bu: str, choices: list[str], params, state: str, snapshot: dict | None, points: list[dict], totals: dict | None,
                     matrix: dict | None, option_lists: dict | None, relations: dict | None = None, csrf: str, nonce: str, me: dict) -> str:
    """state: ok, belum (no snapshot yet), lama (snapshot without lead rows), kosong (nothing in the range), kosong_filter (nothing matches the
    filters), error (date problem) or gagal (database did not answer)."""
    label = names.get(bu, bu)
    unit = params.per
    head = (
        '<main class="vw-main" style="max-width:1320px"><nav class="vw-crumbs" aria-label="Posisi halaman"><a class="vw-link" href="/">Daftar report</a><span class="sep" aria-hidden="true">/</span><span aria-current="page" style="color:#17283e">Performa</span></nav>'
        '<h1 class="vw-h1">Performa</h1><p class="vw-lead" style="max-width:680px">Submission, MQL, SQL, dan Deal Won beserta nilainya pada rentang tanggal yang Anda pilih, per hari, minggu, atau bulan. '
        'Matriks cohort di bawahnya menunjukkan dari periode mana lead yang menjadi MQL dan SQL berasal.</p>'
    )
    freshness = ""
    if snapshot:
        day = snapshot["as_of"]
        freshness = (f'<p style="margin:0 0 16px;color:{MUTED}">Data per {day.day} {pages.MONTHS[day.month - 1]} {day.year}, dihitung {escape(pages.dt_text(snapshot["generated_at"]))}. '
                     "Memperbarui: jalankan workflow Performa Generate di n8n.</p>")
    if state == "gagal":
        body = (f'<div role="alert" style="background:#fcecec;border:1px solid #ac3d3d;border-radius:6px;padding:32px"><h2 class="vw-h2" style="color:#ac3d3d;margin-bottom:8px">Data performa tidak bisa dimuat</h2>'
                '<p style="margin:0 0 16px;color:#17283e">Database marketing_reports tidak menjawab. Coba lagi.</p><a class="vw-link" href="/performa" style="font-weight:600">Coba lagi</a></div>')
    elif state in ("belum", "lama"):
        hint = "Jalankan workflow Performa Generate di n8n, lalu muat ulang halaman ini." if me["role"] == "admin" else "Hubungi admin untuk menjalankannya."
        title = f"Belum ada data performa untuk {label}" if state == "belum" else f"Data performa {label} dibuat dengan versi lama"
        body = f'<div class="vw-box" style="padding:32px"><h2 class="vw-h2" style="margin-bottom:8px">{escape(title)}</h2><p style="margin:0">{escape(hint)}</p></div>'
    elif state == "error":
        body = ""
    elif state == "kosong_filter":
        body = (f'<div class="vw-box" style="padding:32px"><h2 class="vw-h2" style="margin-bottom:8px">Tidak ada lead yang cocok dengan filter ini</h2>'
                '<p style="margin:0 0 8px">Pada rentang tanggal ini tidak ada lead dengan kombinasi filter yang dipilih. Hapus sebagian filter atau ubah rentang tanggal.</p>'
                f'<a class="vw-link" href="{escape(query_for(bu, params, keep_filters=False))}" style="font-weight:600">Hapus semua filter</a></div>')
    elif state == "kosong":
        body = '<div class="vw-box" style="padding:32px"><h2 class="vw-h2" style="margin-bottom:8px">Tidak ada data pada rentang ini</h2><p style="margin:0">Ubah rentang tanggal atau pilih perusahaan lain.</p></div>'
    else:
        volume_keys, value_keys = ("sub", "mql", "sql", "won"), ("sqlv", "wonv")
        summary_rows = (
            ("Submission", _n(totals["sub"]), ""), ("MQL", _n(totals["mql"]), f'MQL Rate {_pct(totals["mql_rate"])}'), ("SQL", _n(totals["sql"]), f'SQL Rate {_pct(totals["sql_rate"])}'),
            ("SQL Value", _rp(totals["sqlv"]), ""), ("Deal Won", _n(totals["won"]), f'Deal Won Rate {_pct(totals["won_rate"])}'), ("Deal Won Value", _rp(totals["wonv"]), ""),
        )
        srows = "".join(f'<tr><td data-label="Metrik">{m}</td><td data-label="Total" class="num">{t}</td><td data-label="Rate">{escape(r)}</td></tr>' for m, t, r in summary_rows)
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
            + matrix_section(params, matrix, unit)
        )
    layout = (f'<div class="pf-layout">{sidebar(names=names, bu=bu, choices=choices, params=params, state=state, option_lists=option_lists)}'
              f'<div class="pf-content">{context_box(names=names, bu=bu, params=params)}{freshness}{body}</div></div>')
    rel_block = f'<script type="application/json" id="pf-rel">{cascade.rel_json(relations)}</script>' if relations else ""
    script = rel_block + f'<script nonce="{nonce}">{SIDEBAR_JS.replace("__CASCADE__", cascade.CASCADE_JS)}</script>'
    return pages.page("Performa", f"<style nonce=\"{nonce}\">{CSS}</style>" + head + layout + "</main>", nonce, csrf, pages.menu(csrf, me, "performa"), script)
