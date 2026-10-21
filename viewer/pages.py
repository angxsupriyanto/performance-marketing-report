"""HTML for the viewer's own pages: login, report list, target settings, and the bar placed above a report."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from html import escape

from bs4 import BeautifulSoup

WIB = timezone(timedelta(hours=7))
MONTHS = ("Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des")
TITLE = "Digital Marketing Report"
FONT = '<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&amp;display=swap" rel="stylesheet">'

BASE_CSS = """
*{box-sizing:border-box}
body{margin:0;background:#f4f7fb;color:#394d65;font:14px/1.5 Inter,Arial,sans-serif}
a{color:#2159a9}a:hover{color:#17283e}
a:focus-visible,button:focus-visible,input:focus-visible,select:focus-visible{outline:2px solid #2159a9;outline-offset:2px}
.vw-top{background:#fff;border-bottom:1px solid #dfe7f0;padding:0 32px;height:56px;display:flex;align-items:center;justify-content:space-between}
.vw-brand{font-weight:600;color:#17283e}
.vw-menu{display:flex;align-items:center;gap:24px}
.vw-menu a,.vw-link{display:inline-flex;align-items:center;min-height:44px}
.vw-menu button{background:none;border:0;padding:0;color:#2159a9;font:inherit;cursor:pointer;min-height:44px}
.vw-menu button:hover{color:#17283e}
.vw-main{width:100%;max-width:1040px;margin:0 auto;padding:24px 32px 64px}
.vw-h1{margin:0 0 8px;font:600 22px/1.3 Inter,Arial,sans-serif;color:#17283e}
.vw-h2{margin:0 0 4px;font:600 16px/1.4 Inter,Arial,sans-serif;color:#17283e}
.vw-lead{margin:0 0 24px}
.vw-crumbs{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-bottom:8px}
.vw-crumbs span.sep{color:#607188}
.vw-box{background:#fff;border:1px solid #dfe7f0;border-radius:6px}
.vw-pad{padding:20px 24px}
.vw-btn{height:44px;padding:0 20px;border:0;border-radius:6px;background:#2159a9;color:#fff;font:600 14px Inter,Arial,sans-serif;cursor:pointer}
.vw-btn.alt{border:1px solid #2159a9;background:#fff;color:#2159a9}
.vw-btn:disabled{background:#e3e9f1;color:#4a5b70;border:0;cursor:default}
.vw-field{display:flex;flex-direction:column}
.vw-field label{font-weight:500;color:#17283e;margin-bottom:6px}
.vw-field input,.vw-field select{height:44px;padding:0 12px;border:1px solid #6f8199;border-radius:6px;background:#fff;color:#17283e;font:14px Inter,Arial,sans-serif}
.vw-alert{margin:0 0 16px;padding:10px 12px;border-radius:6px;background:#fcecec;color:#ac3d3d}
.vw-ok{margin:20px 0 0;padding:10px 12px;border-radius:6px;background:#e6f5ed;color:#087450}
.vw-bar{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:16px}
.vw-dl{margin:0 0 24px;display:flex;flex-wrap:wrap;gap:4px 40px}.vw-dl dt{color:#607188}.vw-dl dd{margin:0;font-weight:600;color:#17283e}
.vw-table{width:100%;border-collapse:collapse}
.vw-table th{text-align:left;font-weight:500;color:#607188;padding:12px 16px;border-bottom:1px solid #dfe7f0}
.vw-table td{padding:14px 16px;border-top:1px solid #dfe7f0;vertical-align:top}
.vw-table tbody tr:first-child td{border-top:0}
.vw-table .num{text-align:right}
.vw-sr{position:absolute;left:-9999px}
.vw-tag{display:inline-block;padding:2px 8px;border-radius:4px;font-weight:500;font-size:12.5px}
.vw-tag.ok{background:#e6f5ed;color:#087450}.vw-tag.none{border:1px solid #6f8199;color:#394d65}
.vw-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:16px}
@media (max-width:680px){
  .vw-top{padding:0 16px}.vw-main{padding:16px 16px 48px}.vw-chrome{padding:16px 16px 0}
  .vw-table thead{position:absolute;left:-9999px}
  .vw-table tr{display:block;padding:8px 16px;border-top:1px solid #dfe7f0}
  .vw-table tbody tr:first-child{border-top:0}
  .vw-table td{display:flex;justify-content:space-between;gap:16px;padding:4px 0;border:0;text-align:left}
  .vw-table td::before{content:attr(data-label);color:#607188}
  .vw-table .num{text-align:left}
}
"""


def dt_text(value: datetime | None) -> str:
    if value is None:
        return ""
    local = value.astimezone(WIB)
    return f"{local.day} {MONTHS[local.month - 1]} {local.year}, {local:%H.%M} WIB"


def range_text(start, end) -> str:
    if start.month == end.month and start.year == end.year:
        return f"{start.day} sampai {end.day} {MONTHS[end.month - 1]} {end.year}"
    return f"{start.day} {MONTHS[start.month - 1]} {start.year} sampai {end.day} {MONTHS[end.month - 1]} {end.year}"


def page(title: str, body: str, nonce: str, csrf: str | None = None, nav: str = "", scripts: str = "") -> str:
    meta = f'<meta name="csrf" content="{escape(csrf)}">' if csrf else ""
    return (
        f'<!doctype html><html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<meta name="robots" content="noindex,nofollow">{meta}<title>{escape(title)}</title>{FONT}<style nonce="{nonce}">{BASE_CSS}</style></head>'
        f'<body><header class="vw-top"><span class="vw-brand">{TITLE}</span>{nav}</header>{body}{scripts}</body></html>'
    )


def menu(csrf: str, current: str = "") -> str:
    here = ' aria-current="page" style="color:#17283e;font-weight:600"' if current == "targets" else ""
    return (
        f'<nav class="vw-menu" aria-label="Menu"><a href="/targets"{here}>Pengaturan target</a>'
        f'<form method="post" action="/logout"><input type="hidden" name="csrf" value="{escape(csrf)}"><button type="submit">Keluar</button></form></nav>'
    )


def login(nonce: str, error: str = "", locked: bool = False) -> str:
    alert = f'<p role="alert" class="vw-alert">{escape(error)}</p>' if error else ""
    attrs = ' aria-invalid="true"' if error and not locked else ""
    disabled = " disabled" if locked else ""
    body = (
        '<main style="display:flex;justify-content:center;padding:96px 16px 48px"><form method="post" action="/login" style="width:100%;max-width:360px;display:flex;flex-direction:column">'
        '<h1 class="vw-h1">Masuk</h1><p class="vw-lead">Report ini hanya untuk tim internal.</p>'
        f'<div class="vw-field" style="margin-bottom:16px"><label for="password">Password</label><input id="password" name="password" type="password" autocomplete="current-password" required autofocus{attrs}{disabled}></div>'
        f'{alert}<button class="vw-btn" type="submit"{disabled}>Masuk</button></form></main>'
    )
    return page("Masuk", body, nonce)


def report_list(rows: list[dict], csrf: str, nonce: str, error: str = "") -> str:
    if error:
        content = (
            '<div role="alert" class="vw-box" style="padding:32px;background:#fcecec;border-color:#ac3d3d"><h2 class="vw-h2" style="color:#ac3d3d">Daftar report tidak bisa dimuat</h2>'
            '<p style="margin:0 0 4px;color:#17283e">Database marketing_reports tidak menjawab.</p>'
            '<p style="margin:0 0 16px;color:#17283e">Coba lagi. Jika tetap gagal, periksa apakah container n8n-postgres berjalan.</p><a class="vw-link" href="/" style="font-weight:600">Coba lagi</a></div>'
        )
    elif not rows:
        content = (
            '<div class="vw-box" style="padding:32px"><h2 class="vw-h2">Belum ada report</h2>'
            '<p style="margin:0 0 16px">Jalankan workflow Report Generate di n8n untuk periode yang ingin dilihat, lalu muat ulang halaman ini.</p>'
            '<a class="vw-link" href="/" style="font-weight:600">Muat ulang</a></div>'
        )
    else:
        trs = []
        for r in rows:
            bu = r["bu"].upper()
            analysis = (
                f'<span class="vw-tag ok">Sudah ada</span><br><span style="color:#607188">{escape(dt_text(r["analysis_created_at"]))}</span>'
                if r["has_analysis"] else '<span class="vw-tag none">Belum ada</span>'
            )
            trs.append(
                f'<tr><td data-label="Periode"><span style="font-weight:600;color:#17283e">{escape(r["period"])}</span><br><span style="color:#607188">{escape(range_text(r["period_start"], r["period_end"]))}</span></td>'
                f'<td data-label="BU">{escape(bu)}</td><td data-label="Dibuat">{escape(dt_text(r["generated_at"]))}</td><td data-label="Analisis">{analysis}</td>'
                f'<td data-label=""><a class="vw-link" style="font-weight:600" aria-label="Buka report {escape(bu)} {escape(r["period"])}" href="/report/{escape(r["bu"])}/{escape(r["period"])}">Buka</a></td></tr>'
            )
        content = (
            '<div class="vw-box"><table class="vw-table"><caption class="vw-sr">Report yang sudah dibuat</caption><thead><tr><th scope="col">Periode</th><th scope="col">BU</th><th scope="col">Dibuat</th><th scope="col">Analisis</th>'
            f'<th scope="col"><span class="vw-sr">Aksi</span></th></tr></thead><tbody>{"".join(trs)}</tbody></table></div>'
        )
    body = (
        f'<main class="vw-main"><h1 class="vw-h1">Daftar report</h1><p class="vw-lead">Dibuat dari tab NEW Customers List lewat n8n. Yang terbaru di atas.</p>{content}</main>'
    )
    return page("Daftar report", body, nonce, csrf, menu(csrf))


ANALYSIS_CSS = """
.vw-wrapper{background:#f4f7fb}
.vw-chrome{width:100%;max-width:1040px;margin:0 auto;padding:24px 32px 0}
.vw-chrome *{box-sizing:border-box}
.vw-chrome a{color:#2159a9}
"""

ANALYSIS_JS = """
(function(){
  var box=document.getElementById('vw-analysis');if(!box)return;
  var csrf=document.querySelector('meta[name=csrf]').content;
  var bu=box.dataset.bu,period=box.dataset.period,timer=null;
  var title=box.querySelector('[data-role=title]'),text=box.querySelector('[data-role=text]'),btn=box.querySelector('button');
  function show(kind,head,body,color){title.textContent=head;title.style.color=color||'#17283e';text.textContent=body;
    box.setAttribute('role',kind==='error'?'alert':'status');}
  function poll(){
    fetch('/api/analysis/status?bu='+encodeURIComponent(bu)+'&period='+encodeURIComponent(period),{credentials:'same-origin'})
      .then(function(r){return r.json();}).then(function(s){
        if(s.state==='running'){timer=setTimeout(poll,4000);return;}
        if(s.state==='done'){location.reload();return;}
        btn.disabled=false;btn.textContent='Coba lagi';
        show('error','Analisis gagal',s.error||'Analisis tidak selesai. Report numerik tidak berubah.','#ac3d3d');
      }).catch(function(){timer=setTimeout(poll,8000);});
  }
  btn.addEventListener('click',function(){
    btn.disabled=true;btn.textContent='Menganalisis';
    show('status','Menganalisis','Mengirim ringkasan angka ke Claude dan menyisipkan hasilnya ke report. Jangan tutup halaman ini.');
    fetch('/api/analysis',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({bu:bu,period:period})})
      .then(function(r){return r.json().then(function(j){return {ok:r.ok,body:j};});})
      .then(function(res){
        if(!res.ok){btn.disabled=false;btn.textContent='Coba lagi';show('error','Analisis gagal',res.body.error||'Permintaan ditolak.','#ac3d3d');return;}
        poll();
      }).catch(function(){btn.disabled=false;btn.textContent='Coba lagi';show('error','Analisis gagal','Tidak bisa menghubungi server. Coba lagi.','#ac3d3d');});
  });
  if(box.dataset.state==='running'){btn.disabled=true;btn.textContent='Menganalisis';poll();}
})();
"""


def analysis_state(has_analysis: bool, job: dict | None) -> str:
    if job and job["state"] == "running":
        return "running"
    if job and job["state"] == "failed":
        return "failed"
    return "done" if has_analysis else "none"


def report_chrome(report: dict, state: str, job_error: str, csrf: str) -> str:
    bu, period = report["bu"], report["period"]
    label = f"{bu.upper()} {period}"
    if state == "running":
        head, text, color, label_btn, alt = "Menganalisis", "Mengirim ringkasan angka ke Claude dan menyisipkan hasilnya ke report. Jangan tutup halaman ini.", "#17283e", "Menganalisis", False
    elif state == "failed":
        head, text, color, label_btn, alt = "Analisis gagal", (job_error or "Analisis tidak selesai.") + " Report numerik tidak berubah.", "#ac3d3d", "Coba lagi", False
    elif state == "done":
        head, text, color, label_btn, alt = "Analisis tersedia", f"Dibuat {dt_text(report['analysis_created_at'])}. Membuat ulang menambah versi baru, versi lama tetap tersimpan.", "#087450", "Buat ulang analisis", True
    else:
        head, text, color, label_btn, alt = "Belum ada analisis", "Hanya ringkasan angka yang dikirim ke Claude, tanpa nama perusahaan.", "#17283e", "Buat analisis", False
    disabled = " disabled" if state == "running" else ""
    role = "alert" if state == "failed" else "status"
    return (
        f'<style nonce="{{nonce}}">{BASE_CSS}{ANALYSIS_CSS}</style>'
        f'<header class="vw-top"><span class="vw-brand">{TITLE}</span>{menu(csrf)}</header>'
        '<div class="vw-chrome"><nav class="vw-crumbs" aria-label="Posisi halaman"><a class="vw-link" href="/">Daftar report</a><span class="sep" aria-hidden="true">/</span>'
        f'<span aria-current="page" style="color:#17283e">{escape(label)}</span></nav>'
        f'<h1 class="vw-h1" style="margin-bottom:12px">Report {escape(bu.upper())}</h1>'
        f'<dl class="vw-dl"><div><dt>Periode</dt><dd>{escape(period)}</dd></div><div><dt>Tanggal</dt><dd style="font-weight:400">{escape(range_text(report["period_start"], report["period_end"]))}</dd></div></dl>'
        f'<section id="vw-analysis" aria-label="Analisis" role="{role}" class="vw-box vw-pad" data-bu="{escape(bu)}" data-period="{escape(period)}" data-state="{escape(state)}" style="margin-bottom:24px">'
        f'<div class="vw-bar"><div style="flex:1 1 360px;min-width:0"><div data-role="title" style="font-weight:600;color:{color}">{escape(head)}</div><div data-role="text">{escape(text)}</div></div>'
        f'<div><button type="button" class="vw-btn{" alt" if alt else ""}"{disabled}>{escape(label_btn)}</button></div></div></section></div>'
    )


def inject_chrome(report_html: str, chrome: str, nonce: str, csrf: str) -> str:
    soup = BeautifulSoup(report_html, "html.parser")
    head, body = soup.head, soup.body
    meta = soup.new_tag("meta", attrs={"name": "csrf", "content": csrf})
    head.append(meta)
    robots = soup.new_tag("meta", attrs={"name": "robots", "content": "noindex,nofollow"})
    head.append(robots)
    font = BeautifulSoup(FONT, "html.parser")
    for tag in list(font.children):
        head.append(tag)
    chrome_soup = BeautifulSoup(chrome.replace("{nonce}", nonce), "html.parser")
    anchor = None
    for tag in list(chrome_soup.children):
        if anchor is None:
            body.insert(0, tag)
            anchor = tag
        else:
            anchor.insert_after(tag)
            anchor = tag
    script = soup.new_tag("script")
    script.string = ANALYSIS_JS
    body.append(script)
    for tag in soup.find_all(["script", "style"]):
        tag["nonce"] = nonce
    return str(soup)


def unit_text(unit: str) -> str:
    return "Rp" if unit == "idr" else "jumlah SQL Ecosystem"


def targets_page(bu: str, unit: str, products: list[str], months: list[tuple[str, str]], selected_month: str, current: dict, year: str, years: list[str],
                 semesters: dict, history: list[dict], csrf: str, nonce: str, notice: str = "", failed: str = "", errors: dict | None = None) -> str:
    errors = errors or {}
    label = bu.upper()
    is_idr = unit == "idr"
    placeholder = "Angka dalam Rupiah" if is_idr else "Angka dalam jumlah SQL"
    bu_options = "".join(f'<option value="{b}"{" selected" if b == bu else ""}>{b.upper()}</option>' for b in ("bu1", "bu2"))

    def amount_text(value) -> str:
        return "" if value is None else f"{int(value):,}".replace(",", ".")

    def field(field_id: str, name: str, caption: str, value: str) -> str:
        err = errors.get(name, "")
        invalid = ' aria-invalid="true"' if err else ""
        note = f'<span role="alert" style="color:#ac3d3d;margin-top:4px">{escape(err)}</span>' if err else ""
        shown = escape(value)
        return (
            f'<div class="vw-field"><label for="{field_id}">{escape(caption)}</label>'
            f'<input id="{field_id}" name="{escape(name)}" type="text" inputmode="numeric" placeholder="{placeholder}" value="{shown}"{invalid}>{note}</div>'
        )

    sem1, sem2 = semesters.get("S1"), semesters.get("S2")
    year_total = (sem1 + sem2) if sem1 is not None and sem2 is not None else None
    total_text = ("Rp " + amount_text(year_total) if is_idr else amount_text(year_total) + " SQL") if year_total is not None else "Belum lengkap"
    year_options = "".join(f'<option value="{y}"{" selected" if y == year else ""}>{y}</option>' for y in years)
    year_unit = unit_text(unit)
    year_form = (
        f'<section aria-label="Target semester dan 1 tahun" class="vw-box" style="padding:24px;margin-bottom:32px"><h2 class="vw-h2">Target {"SQL Value" if is_idr else "SQL Ecosystem"} semester dan 1 tahun {label}</h2>'
        '<p style="margin:0 0 16px;max-width:680px;color:#607188">'
        + ("Dipakai untuk dua progress di report: semester berjalan dan akumulasi 1 tahun." if is_idr else "Target BU2 berupa jumlah SQL dari campaign Ecosystem (existing user BU1), bukan Rupiah. Dipakai untuk progress semester berjalan dan akumulasi 1 tahun.")
        + ' Target 1 tahun adalah jumlah dua semester.</p>'
        f'<form method="post" action="/targets/year"><input type="hidden" name="csrf" value="{escape(csrf)}"><input type="hidden" name="bu" value="{bu}">'
        '<div style="display:flex;flex-wrap:wrap;gap:16px;align-items:flex-start">'
        f'<div class="vw-field" style="flex:0 1 140px"><label for="tahun">Tahun</label><select id="tahun" name="year" data-reload="year">{year_options}</select></div>'
        f'<div style="flex:1 1 220px">{field("sem1", "sem1", f"Target Semester 1, Januari sampai Juni ({year_unit})", errors.get("_v_sem1", amount_text(sem1)))}</div>'
        f'<div style="flex:1 1 220px">{field("sem2", "sem2", f"Target Semester 2, Juli sampai Desember ({year_unit})", errors.get("_v_sem2", amount_text(sem2)))}</div></div>'
        f'<div style="margin-top:20px;display:flex;flex-wrap:wrap;gap:4px 12px;align-items:baseline"><span style="color:#607188">Target 1 tahun {label}</span><span style="font-weight:600;color:#17283e">{escape(total_text)}</span></div>'
        + (f'<p role="status" class="vw-ok">{escape(notice)}</p>' if notice == f"Target semester dan 1 tahun {label} tersimpan." else "")
        + (f'<p role="alert" class="vw-alert" style="margin-top:20px">{escape(failed)}</p>' if failed and errors.get("_form") == "year" else "")
        + '<div style="margin-top:20px"><button class="vw-btn" type="submit">Simpan target tahunan</button></div></form></section>'
    )
    month_options = "".join(f'<option value="{k}"{" selected" if k == selected_month else ""}>{escape(t)}</option>' for k, t in months)
    month_total = sum((v for v in current.values() if v is not None), 0)
    fields = "".join(
        field(f"hw-{i}", f"hw_{i}", f"Target {name} (Rp)", errors.get(f"_v_hw_{i}", amount_text(current.get(name)))) for i, name in enumerate(products)
    )
    month_form = ""
    if is_idr:
        month_form = (
            f'<section aria-label="Atur target" class="vw-box" style="padding:24px;margin-bottom:32px"><h2 class="vw-h2">Target SQL Value bulanan per hardware {label}</h2>'
            '<p style="margin:0 0 16px;max-width:680px;color:#607188">Target yang disimpan berlaku mulai bulan yang dipilih dan seterusnya, sampai Anda menyimpan target baru. Tidak perlu mengisi ulang tiap bulan. Isi 0 untuk menghapus target sebuah hardware.</p>'
            f'<form method="post" action="/targets/month"><input type="hidden" name="csrf" value="{escape(csrf)}"><input type="hidden" name="bu" value="{bu}">'
            f'<div class="vw-field" style="flex:0 1 240px;margin-bottom:24px;max-width:240px"><label for="mulai">Berlaku mulai bulan</label><select id="mulai" name="month" data-reload="month">{month_options}</select></div>'
            f'<div class="vw-grid">{fields}</div>'
            f'<div style="margin-top:20px;display:flex;flex-wrap:wrap;gap:4px 12px;align-items:baseline"><span style="color:#607188">Total target {label}</span><span style="font-weight:600;color:#17283e">{"Rp " + amount_text(month_total) if month_total else "Belum diatur"}</span></div>'
            + (f'<p role="status" class="vw-ok">{escape(notice)}</p>' if notice == f"Target bulanan {label} tersimpan." else "")
            + (f'<p role="alert" class="vw-alert" style="margin-top:20px">{escape(failed)}</p>' if failed and errors.get("_form") == "month" else "")
            + '<div style="margin-top:20px"><button class="vw-btn" type="submit">Simpan target</button></div></form></section>'
        )
    else:
        month_form = '<p style="margin:0 0 32px;max-width:680px;color:#607188">BU2 tidak memakai target bulanan. Report BU2 hanya menampilkan progress semester dan 1 tahun.</p>'

    def entry_label(r: dict) -> str:
        if r["scope"] == "semester":
            year_part, sem = r["period_key"].split("-")
            return f"Semester {sem[1]} {year_part}"
        return f'{r["product"]}, mulai {r["period_key"]}'

    if history:
        rows = "".join(
            f'<tr><td data-label="Target">{escape(entry_label(r))}</td><td data-label="Nilai" class="num">{escape(("Rp " + amount_text(r["amount"])) if r["unit"] == "idr" else amount_text(r["amount"]) + " SQL")}{" (dihapus)" if r["amount"] == 0 else ""}</td><td data-label="Dicatat pada">{escape(dt_text(r["recorded_at"]))}</td></tr>'
            for r in history
        )
        hist = (
            f'<div class="vw-box"><table class="vw-table"><caption class="vw-sr">Riwayat target {label}</caption><thead><tr><th scope="col">Target</th><th scope="col" class="num">Nilai</th><th scope="col">Dicatat pada</th></tr></thead><tbody>{rows}</tbody></table></div>'
        )
    else:
        hist = (
            f'<div class="vw-box" style="padding:24px"><div style="font-weight:600;color:#17283e;margin-bottom:4px">Belum ada target tersimpan untuk {label}</div>'
            f'<div>Sampai target disimpan, report {label} menampilkan "Belum diatur" pada kolom Target dan Progress.</div></div>'
        )
    body = (
        '<main class="vw-main"><nav class="vw-crumbs" aria-label="Posisi halaman"><a class="vw-link" href="/">Daftar report</a><span class="sep" aria-hidden="true">/</span><span aria-current="page" style="color:#17283e">Pengaturan target</span></nav>'
        '<h1 class="vw-h1">Pengaturan target</h1>'
        '<p class="vw-lead" style="max-width:680px">Target SQL Value bulanan per hardware untuk BU1, serta target semester dan 1 tahun per BU. Riwayat target tidak pernah ditimpa; setiap penyimpanan menambah satu baris.</p>'
        f'<div class="vw-field" style="margin-bottom:24px;max-width:200px"><label for="bu">BU</label><select id="bu" data-reload="bu">{bu_options}</select></div>'
        f'{year_form}{month_form}<section aria-label="Riwayat target"><h2 class="vw-h2">Riwayat target {label}</h2><p style="margin:0 0 12px;color:#607188">Setiap penyimpanan menambah satu baris. Riwayat lama tidak ditimpa.</p>{hist}</section></main>'
    )
    script = (
        f'<script nonce="{nonce}">document.querySelectorAll("select[data-reload]").forEach(function(s){{s.addEventListener("change",function(){{'
        'var u=new URL(location.href);var bu=document.getElementById("bu").value;u.searchParams.set("bu",bu);'
        'var m=document.getElementById("mulai");if(m)u.searchParams.set("month",m.value);var y=document.getElementById("tahun");if(y)u.searchParams.set("year",y.value);'
        'location.href=u.toString();});});</script>'
    )
    return page("Pengaturan target", body, nonce, csrf, menu(csrf, "targets"), script)
