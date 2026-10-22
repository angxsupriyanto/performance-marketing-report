"""HTML for the viewer's own pages: login, report list, target settings, and the bar placed above a report."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from html import escape

from bs4 import BeautifulSoup

from viewer import cascade
from viewer.performance import EMPTY_LABEL

WIB = timezone(timedelta(hours=7))
MONTHS = ("Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des")
TITLE = "Digital Marketing Report"
FONT = '<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&amp;display=swap" rel="stylesheet">'

BASE_CSS = """
*{box-sizing:border-box}
[hidden]{display:none!important}
body{margin:0;background:#f4f7fb;color:#394d65;font:14px/1.5 Inter,Arial,sans-serif}
a{color:#2159a9}a:hover{color:#17283e}
a:focus-visible,button:focus-visible,input:focus-visible,select:focus-visible{outline:2px solid #2159a9;outline-offset:2px}
.vw-top{background:#fff;border-bottom:1px solid #dfe7f0;padding:0 32px;min-height:56px;display:flex;align-items:center;justify-content:space-between}
.vw-brand{font-weight:600;color:#17283e}
.vw-menu{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:0 32px;flex:1;margin-left:32px}
.vw-menu-main,.vw-menu-user{display:flex;flex-wrap:wrap;align-items:center;gap:0 20px}
.vw-mn{display:inline-flex;align-items:center;min-height:44px;padding:0 2px;box-sizing:border-box;border-bottom:2px solid transparent;text-decoration:none}
.vw-mn:hover{color:#17283e}
.vw-mn[aria-current=page]{color:#17283e;font-weight:600;border-bottom-color:#2159a9}
.vw-sep{width:1px;height:20px;background:#dfe7f0}
.vw-menu-user form{display:flex;margin:0}
.vw-link{display:inline-flex;align-items:center;min-height:44px}
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


ROLE_TEXT = {"admin": "Admin", "user": "Pengguna"}


def menu(csrf: str, user: dict | None, current: str = "") -> str:
    """Daftar report and Performa for everyone, then admin-only groups (budget and targets, users and company names), as in the mockup."""
    def link(key: str, href: str, text: str) -> str:
        here = ' aria-current="page"' if current == key else ""
        return f'<a class="vw-mn" href="{href}"{here}>{text}</a>'

    sep = '<span class="vw-sep" aria-hidden="true"></span>'
    main = ""
    who = ""
    if user is not None:
        main = link("daftar", "/", "Daftar report") + link("performa", "/performa", "Performa")
        if user["role"] == "admin":
            main += (sep + link("budget", "/budget", "Budget") + link("targets", "/targets", "Pengaturan target")
                     + sep + link("users", "/users", "Pengguna") + link("companies", "/companies", "Nama perusahaan"))
        who = f'<span style="color:#607188">{escape(user["username"])} ({ROLE_TEXT.get(user["role"], "")})</span>{sep}'
    return (
        f'<nav class="vw-menu" aria-label="Menu"><div class="vw-menu-main">{main}</div>'
        f'<div class="vw-menu-user">{who}<form method="post" action="/logout"><input type="hidden" name="csrf" value="{escape(csrf)}"><button type="submit">Keluar</button></form></div></nav>'
    )


def login(nonce: str, error: str = "", locked: bool = False) -> str:
    alert = f'<p role="alert" class="vw-alert">{escape(error)}</p>' if error else ""
    attrs = ' aria-invalid="true"' if error and not locked else ""
    disabled = " disabled" if locked else ""
    body = (
        '<main style="display:flex;justify-content:center;padding:96px 16px 48px"><form method="post" action="/login" style="width:100%;max-width:360px;display:flex;flex-direction:column">'
        '<h1 class="vw-h1">Masuk</h1><p class="vw-lead">Report ini hanya untuk tim internal.</p>'
        f'<div class="vw-field" style="margin-bottom:16px"><label for="username">Username</label><input id="username" name="username" type="text" autocomplete="username" autocapitalize="none" spellcheck="false" required autofocus{attrs}{disabled}></div>'
        f'<div class="vw-field" style="margin-bottom:16px"><label for="password">Password</label><input id="password" name="password" type="password" autocomplete="current-password" required{attrs}{disabled}></div>'
        f'{alert}<button class="vw-btn" type="submit"{disabled}>Masuk</button></form></main>'
    )
    return page("Masuk", body, nonce)


def report_list(rows: list[dict], csrf: str, nonce: str, user: dict | None, names: dict, error: str = "") -> str:
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
            bu = names.get(r["bu"], r["bu"])
            analysis = (
                f'<span class="vw-tag ok">Sudah ada</span><br><span style="color:#607188">{escape(dt_text(r["analysis_created_at"]))}</span>'
                if r["has_analysis"] else '<span class="vw-tag none">Belum ada</span>'
            )
            trs.append(
                f'<tr><td data-label="Periode"><span style="font-weight:600;color:#17283e">{escape(r["period"])}</span><br><span style="color:#607188">{escape(range_text(r["period_start"], r["period_end"]))}</span></td>'
                f'<td data-label="Perusahaan">{escape(bu)}</td><td data-label="Dibuat">{escape(dt_text(r["generated_at"]))}</td><td data-label="Analisis">{analysis}</td>'
                f'<td data-label=""><a class="vw-link" style="font-weight:600" aria-label="Buka report {escape(bu)} {escape(r["period"])}" href="/report/{escape(r["bu"])}/{escape(r["period"])}">Buka</a></td></tr>'
            )
        content = (
            '<div class="vw-box"><table class="vw-table"><caption class="vw-sr">Report yang sudah dibuat</caption><thead><tr><th scope="col">Periode</th><th scope="col">Perusahaan</th><th scope="col">Dibuat</th><th scope="col">Analisis</th>'
            f'<th scope="col"><span class="vw-sr">Aksi</span></th></tr></thead><tbody>{"".join(trs)}</tbody></table></div>'
        )
    body = (
        f'<main class="vw-main"><h1 class="vw-h1">Daftar report</h1><p class="vw-lead">Dibuat dari tab NEW Customers List lewat n8n. Yang terbaru di atas.</p>{content}</main>'
    )
    return page("Daftar report", body, nonce, csrf, menu(csrf, user, "daftar"))


ANALYSIS_CSS = """
.vw-wrapper{background:#f4f7fb}
.vw-chrome{width:100%;max-width:1040px;margin:0 auto;padding:24px 32px 0}
.vw-chrome *{box-sizing:border-box}
.vw-chrome a{color:#2159a9}
.vw-arow{display:grid;grid-template-columns:minmax(0,2fr) minmax(0,1.4fr) minmax(0,2fr) 72px;gap:8px;align-items:center;margin-bottom:8px}
.vw-arow-head{color:#607188}
.vw-in{width:100%;height:44px;padding:0 12px;border:1px solid #6f8199;border-radius:6px;background:#fff;color:#17283e;font:14px Inter,Arial,sans-serif}
.vw-linkbtn{display:inline-flex;align-items:center;justify-content:center;min-height:44px;padding:0;border:0;background:none;color:#2159a9;font:600 14px Inter,Arial,sans-serif;cursor:pointer}
@media (max-width:760px){.vw-arow{grid-template-columns:1fr}.vw-arow-head{display:none}}
"""

ANALYSIS_JS = """
(function(){
  var box=document.getElementById('vw-analysis');if(!box)return;
  var csrf=document.querySelector('meta[name=csrf]').content;
  var bu=box.dataset.bu,period=box.dataset.period,timer=null;
  var title=box.querySelector('[data-role=title]'),text=box.querySelector('[data-role=text]'),btn=box.querySelector('button');
  var form=document.getElementById('vw-form'),mode='generate';
  function show(kind,head,body,color){title.textContent=head;title.style.color=color||'#17283e';text.textContent=body;
    box.setAttribute('role',kind==='error'?'alert':'status');}
  function post(url,payload){
    return fetch(url,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(payload)})
      .then(function(r){return r.json().then(function(j){return {ok:r.ok,body:j};});});
  }
  function poll(){
    fetch('/api/analysis/status?bu='+encodeURIComponent(bu)+'&period='+encodeURIComponent(period),{credentials:'same-origin'})
      .then(function(r){return r.json();}).then(function(s){
        if(s.state==='running'){timer=setTimeout(poll,4000);return;}
        if(s.state==='done'){location.reload();return;}
        btn.disabled=false;btn.textContent='Coba lagi';
        show('error','Analisis gagal',s.error||'Analisis tidak selesai. Report numerik tidak berubah.','#ac3d3d');
      }).catch(function(){timer=setTimeout(poll,8000);});
  }
  function start(items){
    if(form)form.hidden=true;
    btn.disabled=true;btn.textContent='Menganalisis';
    show('status','Menganalisis','Mengirim ringkasan angka ke Claude dan menyisipkan hasilnya ke report. Jangan tutup halaman ini.');
    post('/api/analysis',{bu:bu,period:period,items:JSON.stringify(items)}).then(function(res){
        if(!res.ok){btn.disabled=false;btn.textContent='Coba lagi';show('error','Analisis gagal',res.body.error||'Permintaan ditolak.','#ac3d3d');return;}
        poll();
      }).catch(function(){btn.disabled=false;btn.textContent='Coba lagi';show('error','Analisis gagal','Tidak bisa menghubungi server. Coba lagi.','#ac3d3d');});
  }
  /* the report as a PDF: fetched in the page so that a wait and a failure can be shown, then saved from memory */
  var pdfBtn=document.getElementById('vw-pdf'),pdfMsg=document.getElementById('vw-pdf-msg');
  if(pdfBtn){pdfBtn.addEventListener('click',function(){
    pdfMsg.hidden=true;pdfBtn.disabled=true;pdfBtn.textContent='Membuat PDF...';
    function done(){pdfBtn.disabled=false;pdfBtn.textContent='Simpan sebagai PDF';}
    function fail(m){done();pdfMsg.textContent=m;pdfMsg.hidden=false;}
    fetch(pdfBtn.dataset.href,{credentials:'same-origin'}).then(function(r){
      if(!r.ok){return r.json().catch(function(){return {};}).then(function(j){fail(j.error||(r.status===403?'Tidak ada akses ke report ini.':'PDF tidak berhasil dibuat. Coba lagi.'));});}
      var name=((r.headers.get('Content-Disposition')||'').match(/filename="([^"]+)"/)||[])[1]||'report.pdf';
      return r.blob().then(function(b){var url=URL.createObjectURL(b),a=document.createElement('a');a.href=url;a.download=name;document.body.appendChild(a);a.click();a.remove();
        setTimeout(function(){URL.revokeObjectURL(url);},4000);done();});
    }).catch(function(){fail('Tidak bisa menghubungi server. Coba lagi.');});
  });}
  /* the list of actions: one form for both "create analysis" and "change actions" */
  var rowsBox=form?form.querySelector('[data-role=rows]'):null,tpl=document.getElementById('vw-row-tpl'),formError=form?form.querySelector('[data-role=form-error]'):null;
  function renumber(){rowsBox.querySelectorAll('[data-row]').forEach(function(r,i){var n=i+1;
    r.querySelector('input[data-f=action]').setAttribute('aria-label','Action '+n);r.querySelector('select').setAttribute('aria-label','Campaign untuk action '+n);
    r.querySelector('input[data-f=note]').setAttribute('aria-label','Catatan untuk action '+n);r.querySelector('[data-act=row-remove]').setAttribute('aria-label','Hapus action '+n);});}
  function addRow(){rowsBox.appendChild(tpl.content.cloneNode(true));renumber();}
  function items(){return [].slice.call(rowsBox.querySelectorAll('[data-row]')).map(function(r){return {action:r.querySelector('input[data-f=action]').value,campaign:r.querySelector('select').value,note:r.querySelector('input[data-f=note]').value};});}
  function openForm(kind){
    mode=kind;formError.hidden=true;
    form.querySelector('[data-act=form-submit]').textContent=kind==='edit'?'Simpan action':(box.dataset.state==='done'?'Buat ulang analisis':'Buat analisis');
    form.querySelector('[data-role=warn]').hidden=!(kind==='generate'&&Number(box.dataset.edited)>0);
    if(!rowsBox.querySelector('[data-row]'))addRow();
    form.hidden=false;form.querySelector('input[data-f=action]').focus();
    if(kind==='edit')form.scrollIntoView({block:'center'});
  }
  function closeForm(){form.hidden=true;}
  if(form){
    form.addEventListener('click',function(ev){
      var el=ev.target.closest('[data-act]');if(!el)return;var act=el.dataset.act;
      if(act==='row-add'){addRow();rowsBox.lastElementChild.querySelector('input').focus();return;}
      if(act==='row-remove'){var row=el.closest('[data-row]');row.remove();if(!rowsBox.querySelector('[data-row]'))addRow();renumber();return;}
      if(act==='form-cancel'){closeForm();if(btn)btn.focus();return;}
      if(act==='form-submit'){
        if(mode==='generate'){start(items());return;}
        el.disabled=true;
        post('/api/actions',{bu:bu,period:period,items:JSON.stringify(items())}).then(function(res){
          if(res.ok){location.reload();return;}
          el.disabled=false;formError.textContent=res.body.error||'Tidak tersimpan.';formError.hidden=false;
        }).catch(function(){el.disabled=false;formError.textContent='Tidak bisa menghubungi server. Coba lagi.';formError.hidden=false;});
      }
    });
    document.addEventListener('click',function(ev){if(ev.target.closest('[data-act=actions-open]'))openForm('edit');});
  }
  if(btn){
    btn.addEventListener('click',function(){if(form)openForm('generate');else start([]);});
    if(box.dataset.state==='running'){btn.disabled=true;btn.textContent='Menganalisis';poll();}
  }
  function parts(el){var panel=el.closest('[data-panel]');return {panel:panel,key:el.dataset.key,
    editor:panel.querySelector('[data-editor]'),text:panel.querySelector('[data-analysis]'),meta:panel.querySelector('[data-role=meta]'),controls:panel.querySelector('[data-role=controls]')};}
  function editing(p,on){p.editor.hidden=!on;[p.text,p.meta,p.controls].forEach(function(x){if(x)x.hidden=on;});}
  document.addEventListener('click',function(ev){
    var el=ev.target.closest('[data-act][data-key]');if(!el||!el.closest('[data-panel]'))return;
    var act=el.dataset.act,p=parts(el),area=p.editor?p.editor.querySelector('textarea'):null,err=p.editor?p.editor.querySelector('[data-role=error]'):null;
    if(act==='edit'){editing(p,true);area.focus();return;}
    if(act==='cancel'){area.value=area.defaultValue;err.hidden=true;editing(p,false);return;}
    var payload=act==='save'?{bu:bu,period:period,key:p.key,text:area.value}:{bu:bu,period:period,key:p.key,restore:'1'};
    el.disabled=true;
    post('/api/analysis/edit',payload).then(function(res){
      if(res.ok){location.reload();return;}
      el.disabled=false;
      if(err&&act==='save'){err.textContent=res.body.error||'Tidak tersimpan.';err.hidden=false;}else{window.alert(res.body.error||'Tidak tersimpan.');}
    }).catch(function(){el.disabled=false;var m='Tidak bisa menghubungi server. Coba lagi.';if(err&&act==='save'){err.textContent=m;err.hidden=false;}else{window.alert(m);}});
  });
})();
"""


def analysis_state(has_analysis: bool, job: dict | None) -> str:
    if job and job["state"] == "running":
        return "running"
    if job and job["state"] == "failed":
        return "failed"
    return "done" if has_analysis else "none"


def action_form(label: str, items: list[dict], campaigns: list[str], budget_note: str) -> str:
    """The admin-only form for the actions of the period; the viewer's script opens it from the analysis button or from the Action section."""
    names = list(dict.fromkeys(c for c in campaigns if c))
    for item in items:
        if item.get("campaign") and item["campaign"] not in names:
            names.append(item["campaign"])  # a saved name that left the tracker must not silently vanish from its row

    def row(item: dict) -> str:
        options = '<option value="">Tidak spesifik</option>' + "".join(f'<option value="{escape(c)}"{" selected" if c == item.get("campaign") else ""}>{escape(c)}</option>' for c in names)
        return (f'<div class="vw-arow" data-row><input class="vw-in" data-f="action" type="text" maxlength="300" aria-label="Action" placeholder="Contoh: naikkan bid kata kunci brand" value="{escape(item.get("action", ""))}">'
                f'<select class="vw-in" aria-label="Campaign">{options}</select>'
                f'<input class="vw-in" data-f="note" type="text" maxlength="300" aria-label="Catatan" placeholder="Catatan singkat" value="{escape(item.get("note", ""))}">'
                '<button type="button" class="vw-linkbtn" data-act="row-remove" style="width:72px">Hapus</button></div>')

    rows = "".join(row(i) for i in items) or row({})
    return (
        '<div id="vw-form" hidden role="group" aria-labelledby="vw-form-title" class="vw-box vw-pad" style="margin-top:16px;border-color:#6f8199">'
        f'<h2 id="vw-form-title" class="vw-h2" style="margin-bottom:4px">Action yang sudah dilakukan di {escape(label)}</h2>'
        '<p style="margin:0 0 12px;color:#607188">Tulis action yang dijalankan pada periode ini, misalnya menaikkan bid atau mengganti materi iklan. Isian ini tersimpan di report dan ikut menjadi pertimbangan analisis. Boleh dikosongkan.</p>'
        '<div data-role="warn" role="alert" hidden style="margin-bottom:12px;padding:10px 12px;border:1px solid #6f8199;border-radius:6px;color:#17283e">Ada panel yang sudah diedit. Membuat ulang analisis menggantikan teks yang tampil dengan versi AI baru, termasuk panel yang sudah diedit. Versi hasil edit tetap tersimpan di riwayat.</div>'
        '<div class="vw-arow vw-arow-head" aria-hidden="true"><span>Action</span><span>Campaign (opsional)</span><span>Catatan (opsional)</span><span></span></div>'
        f'<div data-role="rows">{rows}</div><template id="vw-row-tpl">{row({})}</template>'
        '<button type="button" class="vw-linkbtn" data-act="row-add" style="justify-content:flex-start">+ Tambah action</button>'
        f'<p style="margin:8px 0 12px;color:#607188">{escape(budget_note)}</p>'
        '<p data-role="form-error" role="alert" hidden class="vw-alert" style="margin:0 0 12px"></p>'
        '<div style="display:flex;flex-wrap:wrap;align-items:center;gap:4px 16px"><button type="button" class="vw-btn" data-act="form-submit">Buat analisis</button>'
        '<button type="button" class="vw-linkbtn" data-act="form-cancel">Batal</button></div></div>'
    )


def report_chrome(report: dict, state: str, job_error: str, csrf: str, user: dict, name: str, edited: int = 0, form_html: str = "") -> str:
    bu, period = report["bu"], report["period"]
    label = f"{name} {period}"
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
        f'<header class="vw-top"><span class="vw-brand">{TITLE}</span>{menu(csrf, user, "daftar")}</header>'
        '<div class="vw-chrome"><nav class="vw-crumbs" aria-label="Posisi halaman"><a class="vw-link" href="/">Daftar report</a><span class="sep" aria-hidden="true">/</span>'
        f'<span aria-current="page" style="color:#17283e">{escape(label)}</span></nav>'
        f'<h1 class="vw-h1" style="margin-bottom:12px">Report {escape(name)}</h1>'
        '<div style="display:flex;flex-wrap:wrap;align-items:flex-start;justify-content:space-between;gap:8px 24px">'
        f'<dl class="vw-dl"><div><dt>Periode</dt><dd>{escape(period)}</dd></div><div><dt>Tanggal</dt><dd style="font-weight:400">{escape(range_text(report["period_start"], report["period_end"]))}</dd></div></dl>'
        f'<div style="margin-bottom:24px"><button type="button" id="vw-pdf" class="vw-btn alt" data-href="/report/{escape(bu)}/{escape(period)}/pdf">Simpan sebagai PDF</button>'
        '<p id="vw-pdf-msg" role="alert" hidden class="vw-alert" style="margin:8px 0 0;max-width:320px"></p></div></div>'
        + (f'<section id="vw-analysis" aria-label="Analisis" role="{role}" class="vw-box vw-pad" data-bu="{escape(bu)}" data-period="{escape(period)}" data-state="{escape(state)}" data-edited="{edited}" style="margin-bottom:24px">'
        f'<div class="vw-bar"><div style="flex:1 1 360px;min-width:0"><div data-role="title" style="font-weight:600;color:{color}">{escape(head)}</div><div data-role="text">{escape(text)}</div></div>'
        + (f'<div><button type="button" class="vw-btn{" alt" if alt else ""}"{disabled}>{escape(label_btn)}</button></div>' if user["role"] == "admin"
           else '<div style="color:#607188">Hanya admin yang bisa membuat atau membuat ulang analisis.</div>')
        + '</div>'
        + (form_html if user["role"] == "admin" else "")
        + '</section>')
        + '</div>'
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
                 semesters: dict, history: list[dict], csrf: str, nonce: str, user: dict, names: dict, notice: str = "", failed: str = "", errors: dict | None = None) -> str:
    errors = errors or {}
    label = names.get(bu, bu)
    is_idr = unit == "idr"
    placeholder = "Angka dalam Rupiah" if is_idr else "Angka dalam jumlah SQL"
    bu_options = "".join(f'<option value="{escape(b)}"{" selected" if b == bu else ""}>{escape(n)}</option>' for b, n in names.items())

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
        + ("Dipakai untuk dua progress di report: semester berjalan dan akumulasi 1 tahun." if is_idr else f"Target {label} berupa jumlah SQL dari campaign Ecosystem (existing user), bukan Rupiah. Dipakai untuk progress semester berjalan dan akumulasi 1 tahun.")
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
        month_form = f'<p style="margin:0 0 32px;max-width:680px;color:#607188">{escape(label)} tidak memakai target bulanan. Report {escape(label)} hanya menampilkan progress semester dan 1 tahun.</p>'

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
        '<p class="vw-lead" style="max-width:680px">Target SQL Value bulanan per hardware, serta target semester dan 1 tahun per perusahaan. Riwayat target tidak pernah ditimpa; setiap penyimpanan menambah satu baris.</p>'
        f'<div class="vw-field" style="margin-bottom:24px;max-width:200px"><label for="bu">Perusahaan</label><select id="bu" data-reload="bu">{bu_options}</select></div>'
        f'{year_form}{month_form}<section aria-label="Riwayat target"><h2 class="vw-h2">Riwayat target {label}</h2><p style="margin:0 0 12px;color:#607188">Setiap penyimpanan menambah satu baris. Riwayat lama tidak ditimpa.</p>{hist}</section></main>'
    )
    script = (
        f'<script nonce="{nonce}">document.querySelectorAll("select[data-reload]").forEach(function(s){{s.addEventListener("change",function(){{'
        'var u=new URL(location.href);var bu=document.getElementById("bu").value;u.searchParams.set("bu",bu);'
        'var m=document.getElementById("mulai");if(m)u.searchParams.set("month",m.value);var y=document.getElementById("tahun");if(y)u.searchParams.set("year",y.value);'
        'location.href=u.toString();});});</script>'
    )
    return page("Pengaturan target", body, nonce, csrf, menu(csrf, user, "targets"), script)


def access_text(user: dict, names: dict) -> str:
    if user["all_companies"]:
        return "Semua perusahaan"
    return ", ".join(names.get(b, b) for b in user["companies"])


def users_page(users: list[dict], names: dict, csrf: str, nonce: str, me: dict, notice: str = "") -> str:
    rows = "".join(
        f'<tr><td data-label="Username" style="font-weight:600;color:#17283e">{escape(u["username"])}</td><td data-label="Peran">{ROLE_TEXT[u["role"]]}</td>'
        f'<td data-label="Akses perusahaan">{escape(access_text(u, names))}</td>'
        f'<td data-label="Status"><span class="vw-tag {"ok" if u["active"] else "none"}">{"Aktif" if u["active"] else "Nonaktif"}</span></td>'
        f'<td data-label="Terakhir masuk">{escape(dt_text(u["last_login_at"])) if u["last_login_at"] else "Belum pernah masuk"}</td>'
        f'<td data-label=""><a class="vw-link" style="font-weight:600" aria-label="Ubah {escape(u["username"])}" href="/users/edit?u={escape(u["username"])}">Ubah</a></td></tr>'
        for u in users
    )
    flash = f'<p role="status" class="vw-ok" style="margin:0 0 16px">{escape(notice)}</p>' if notice else ""
    body = (
        '<main class="vw-main"><nav class="vw-crumbs" aria-label="Posisi halaman"><a class="vw-link" href="/">Daftar report</a><span class="sep" aria-hidden="true">/</span><span aria-current="page" style="color:#17283e">Pengguna</span></nav>'
        '<h1 class="vw-h1">Pengguna</h1>'
        '<p class="vw-lead" style="max-width:680px">Atur siapa yang bisa masuk dan perusahaan mana yang boleh dilihat. Pengguna biasa hanya bisa melihat report. Membuat analisis, mengatur target, dan mengatur pengguna hanya untuk admin.</p>'
        f'<div style="margin-bottom:16px"><a class="vw-btn" href="/users/new" style="display:inline-flex;align-items:center;text-decoration:none">Tambah pengguna</a></div>{flash}'
        '<h2 class="vw-h2" style="margin-bottom:12px">Daftar pengguna</h2>'
        f'<div class="vw-box"><table class="vw-table"><caption class="vw-sr">Daftar pengguna</caption><thead><tr><th scope="col">Username</th><th scope="col">Peran</th><th scope="col">Akses perusahaan</th><th scope="col">Status</th><th scope="col">Terakhir masuk</th><th scope="col"><span class="vw-sr">Aksi</span></th></tr></thead><tbody>{rows}</tbody></table></div>'
        '<p style="margin:12px 0 0;color:#607188">Selalu harus ada minimal satu admin aktif. Pengguna tidak dihapus; nonaktifkan agar tidak bisa masuk dan riwayatnya tetap ada.</p></main>'
    )
    return page("Pengguna", body, nonce, csrf, menu(csrf, me, "users"))


def user_form_page(mode: str, values: dict, errors: dict, names: dict, csrf: str, nonce: str, me: dict, failed: str = "") -> str:
    new = mode == "new"
    title = "Tambah pengguna" if new else f"Ubah pengguna {values['username']}"
    lead = "Pengguna baru bisa masuk setelah disimpan, memakai username dan password yang Anda isi di sini." if new else "Ubah peran, akses, status, atau atur password baru. Kosongkan password jika tidak ingin mengubahnya."

    def err(name: str) -> str:
        return f'<span role="alert" style="color:#ac3d3d;margin-top:4px">{escape(errors[name])}</span>' if name in errors else ""

    def bad(name: str) -> str:
        return ' aria-invalid="true"' if name in errors else ""

    checks = "".join(
        f'<label style="display:flex;align-items:center;gap:8px;min-height:44px"><input type="checkbox" name="company" value="{escape(b)}"{" checked" if b in values["companies"] else ""}> {escape(n)}</label>'
        for b, n in names.items()
    )
    username = (
        f'<input id="username" type="text" value="{escape(values["username"])}" readonly><input type="hidden" name="username" value="{escape(values["username"])}">' if not new else
        f'<input id="username" name="username" type="text" value="{escape(values["username"])}" autocomplete="off" autocapitalize="none" spellcheck="false" required{bad("username")}>'
    )
    role = values["role"]
    all_c = values["all_companies"]
    sel = lambda cond: " selected" if cond else ""
    body = (
        f'<main class="vw-main"><nav class="vw-crumbs" aria-label="Posisi halaman"><a class="vw-link" href="/">Daftar report</a><span class="sep" aria-hidden="true">/</span><a class="vw-link" href="/users">Pengguna</a><span class="sep" aria-hidden="true">/</span><span aria-current="page" style="color:#17283e">{escape(title)}</span></nav>'
        f'<h1 class="vw-h1">{escape(title)}</h1><p class="vw-lead" style="max-width:680px">{escape(lead)}</p>'
        f'<form method="post" action="/users/save" class="vw-box vw-pad" style="max-width:560px"><input type="hidden" name="csrf" value="{escape(csrf)}"><input type="hidden" name="mode" value="{mode}">'
        f'<div class="vw-field" style="margin-bottom:16px"><label for="username">Username</label>{username}<span style="color:#607188;margin-top:4px">3 sampai 32 karakter: huruf kecil, angka, titik, garis bawah, dan strip. Tidak bisa diubah setelah dibuat.</span>{err("username")}</div>'
        f'<div class="vw-field" style="margin-bottom:16px"><label for="password">{"Password" if new else "Password baru (opsional)"}</label><input id="password" name="password" type="password" autocomplete="new-password"{" required" if new else ""}{bad("password")}>'
        f'<span style="color:#607188;margin-top:4px">Password minimal 12 karakter. Pengguna tidak bisa mengubahnya sendiri.</span>{err("password")}</div>'
        f'<div class="vw-field" style="margin-bottom:16px"><label for="role">Peran</label><select id="role" name="role"><option value="user"{sel(role == "user")}>Pengguna (hanya melihat report)</option><option value="admin"{sel(role == "admin")}>Admin (akses penuh)</option></select></div>'
        '<fieldset id="access" style="border:0;padding:0;margin:0 0 16px"><legend style="font-weight:500;color:#17283e;margin-bottom:6px;padding:0">Akses perusahaan</legend>'
        f'<label style="display:flex;align-items:center;gap:8px;min-height:44px"><input type="radio" name="scope" value="all"{" checked" if all_c else ""}> Semua perusahaan <span style="color:#607188">(termasuk perusahaan yang ditambahkan nanti)</span></label>'
        f'<label style="display:flex;align-items:center;gap:8px;min-height:44px"><input type="radio" name="scope" value="pick"{"" if all_c else " checked"}> Pilih perusahaan</label>'
        f'<div id="pick" style="padding-left:28px">{checks}</div>{err("scope")}'
        '<p style="margin:8px 0 0;color:#607188">Pengguna hanya melihat report dan analisis perusahaan yang dipilih. Tombol analisis dan pengaturan target tidak tampil untuknya.</p></fieldset>'
        '<p id="adminNote" style="margin:0 0 16px;color:#607188" hidden>Admin selalu punya akses ke semua perusahaan, termasuk membuat analisis, mengatur target, dan mengatur pengguna.</p>'
        f'<div class="vw-field" style="margin-bottom:16px"><label for="active">Status</label><select id="active" name="active"><option value="1"{sel(values["active"])}>Aktif</option><option value="0"{sel(not values["active"])}>Nonaktif (tidak bisa masuk)</option></select>{err("active")}</div>'
        + (f'<p role="alert" class="vw-alert">{escape(failed)}</p>' if failed else "")
        + '<div style="display:flex;flex-wrap:wrap;align-items:center;gap:4px 16px"><button class="vw-btn" type="submit">Simpan</button><a class="vw-link" href="/users" style="font-weight:600">Batal</a></div></form></main>'
    )
    script = (
        f'<script nonce="{nonce}">(function(){{var r=document.getElementById("role"),a=document.getElementById("access"),n=document.getElementById("adminNote");'
        'function sync(){var admin=r.value==="admin";a.hidden=admin;n.hidden=!admin;}r.addEventListener("change",sync);sync();})();</script>'
    )
    return page(title, body, nonce, csrf, menu(csrf, me, "users"), script)


def companies_page(ids: list[str], names: dict, defaults: dict, errors: dict, csrf: str, nonce: str, me: dict, notice: str = "", failed: str = "") -> str:
    fields = ""
    for i, bu in enumerate(ids):
        err = errors.get(bu, "")
        fields += (
            f'<div class="vw-box vw-pad" style="margin-bottom:16px"><div style="color:#607188">Identitas</div><div style="font-weight:600;color:#17283e;margin-bottom:12px">{escape(defaults[bu])}</div>'
            f'<div class="vw-field" style="max-width:360px"><label for="n-{i}">Nama tampil</label><input id="n-{i}" name="name_{escape(bu)}" type="text" maxlength="32" value="{escape(errors.get("_v_" + bu, names.get(bu, "")))}" required{" aria-invalid=\"true\"" if err else ""}>'
            f'{f"<span role=\"alert\" style=\"color:#ac3d3d;margin-top:4px\">{escape(err)}</span>" if err else ""}</div></div>'
        )
    shown = [names.get(b, "") for b in ids]
    body = (
        '<main class="vw-main"><nav class="vw-crumbs" aria-label="Posisi halaman"><a class="vw-link" href="/">Daftar report</a><span class="sep" aria-hidden="true">/</span><span aria-current="page" style="color:#17283e">Nama perusahaan</span></nav>'
        '<h1 class="vw-h1">Nama perusahaan</h1>'
        '<p class="vw-lead" style="max-width:680px">Nama yang tampil di daftar report, halaman report, pengaturan target, dan pengaturan pengguna. Identitas internal tetap sama, jadi data, tautan, dan akses pengguna yang sudah ada tetap berlaku.</p>'
        f'<form method="post" action="/companies"><input type="hidden" name="csrf" value="{escape(csrf)}">{fields}'
        '<p style="margin:0 0 16px;color:#607188">1 sampai 32 karakter: huruf, angka, spasi, titik, dan strip.</p>'
        + (f'<p role="status" class="vw-ok" style="margin:0 0 16px">{escape(notice)}</p>' if notice else "")
        + (f'<p role="alert" class="vw-alert">{escape(failed)}</p>' if failed else "")
        + '<button class="vw-btn" type="submit">Simpan nama perusahaan</button></form></main>'
    )
    return page("Nama perusahaan", body, nonce, csrf, menu(csrf, me, "companies"))


def _digits(value) -> str:
    return "" if value in (None, "") else f"{int(value):,}".replace(",", ".")


def budget_page(bu: str, names: dict, month: str, month_options: list[tuple[str, str]], rows: list[dict], picker: list[str], weeks: list[tuple], total_text: str, as_of_text: str,
                base_id: str, today, errors: dict, history: list[dict], csrf: str, nonce: str, me: dict, notice: str = "", failed: str = "", rel: dict | None = None) -> str:
    """rows: one dict per campaign {idx, name, budget, month, weeks{key: text}} holding the texts to show in the inputs.
    picker: every campaign name that can be added; the ones already in rows are hidden in the list."""
    from viewer.budget import month_label

    label = names.get(bu, bu)
    company_options = "".join(f'<option value="{escape(b)}"{" selected" if b == bu else ""}>{escape(n)}</option>' for b, n in names.items())
    month_choices = "".join(f'<option value="{k}"{" selected" if k == month else ""}>{escape(t)}</option>' for k, t in month_options)

    def invalid(key: str) -> str:
        return ' aria-invalid="true"' if key in errors else ""

    def money_input(field: str, text: str, aria: str, extra: str = "") -> str:
        return (f'<input id="{escape(field)}" name="{escape(field)}" type="text" inputmode="numeric" placeholder="Rp" aria-label="{escape(aria)}" '
                f'value="{escape(text)}" style="width:100%;height:44px;padding:0 12px;border:1px solid {"#ac3d3d" if field in errors else "#6f8199"};border-radius:6px;background:#fff;color:#17283e;font:14px Inter,Arial,sans-serif"{invalid(field)}{extra}>')

    def week_head(key, monday, sunday):
        span = f"{monday.day} {MONTHS[monday.month - 1]}\u2013{sunday.day} {MONTHS[sunday.month - 1]}" if monday.month != sunday.month else f"{monday.day}\u2013{sunday.day} {MONTHS[sunday.month - 1]}"
        return f'<th scope="col" class="num">{key.split("-")[1]}<br><span style="font-weight:400">{span}</span></th>'

    def name_cell(r, i, hidden=True):
        keep = f'<input type="hidden" name="n_{i}" value="{escape(r["name"])}">' if hidden else ""
        return f'<td data-label="Campaign" data-name>{escape(r["name"])}{keep}</td>'

    def remove_cell(label: str) -> str:
        return f'<td class="num"><button type="button" class="vw-linkbtn" data-remove aria-label="Hapus {escape(label)} dari daftar">Hapus</button></td>'

    budget_rows = "".join(
        f'<tr data-row data-idx="{r["idx"]}">{name_cell(r, r["idx"])}<td data-label="Budget {escape(r["name"])}" class="num cell">{money_input(f"b_{r["idx"]}", r["budget"], f"Budget {r["name"]}")}</td>{remove_cell(r["name"])}</tr>' for r in rows
    )
    week_rows = "".join(
        f'<tr data-row data-idx="{r["idx"]}">{name_cell(r, r["idx"], False)}' + "".join(
            f'<td data-label="Spend {key.split("-")[1]} {escape(r["name"])}" class="num cell">{money_input(f"w_{r["idx"]}_{key}", r["weeks"].get(key, ""), f"Spend {key.split(chr(45))[1]} {r["name"]}", " disabled" if monday > today else "")}</td>'
            for key, monday, _ in weeks) + "</tr>" for r in rows
    )
    month_rows = "".join(
        f'<tr data-row data-idx="{r["idx"]}">{name_cell(r, r["idx"], False)}<td data-label="Spend {escape(month_label(month))} {escape(r["name"])}" class="num cell">{money_input(f"m_{r["idx"]}", r["month"], f"Spend {month_label(month)} {r["name"]}")}</td></tr>' for r in rows
    )

    # templates for a campaign added in the browser; the name is set from JS with textContent, never as markup
    t_budget = (f'<tr data-row data-idx="__I__"><td data-label="Campaign" data-name><input type="hidden" name="n___I__"></td><td data-label="Budget" class="num cell">{money_input("b___I__", "", "Budget campaign baru")}</td>'
                f'{remove_cell("campaign baru")}</tr>')
    t_weeks = '<tr data-row data-idx="__I__"><td data-label="Campaign" data-name></td>' + "".join(
        f'<td data-label="Spend {key.split("-")[1]}" class="num cell">{money_input(f"w___I___{key}", "", f"Spend {key.split(chr(45))[1]} campaign baru", " disabled" if monday > today else "")}</td>' for key, monday, _ in weeks) + "</tr>"
    t_month = f'<tr data-row data-idx="__I__"><td data-label="Campaign" data-name></td><td data-label="Spend" class="num cell">{money_input("m___I__", "", "Spend bulanan campaign baru")}</td></tr>'

    def parent_dd(key: str, title: str) -> str:
        labels = sorted(rel["labels"][key], key=lambda v: (v == EMPTY_LABEL, v.casefold(), v))
        items = "".join(f'<label class="pk-opt" data-opt data-key="{key}" data-label="{escape(v)}"><input type="checkbox" value="{escape(v)}" style="width:20px;height:20px;margin:0"><span>{escape(v)}</span></label>' for v in labels)
        return (f'<details class="pk-dd"><summary><span class="fl">{title}</span><span class="fv">Semua</span></summary><div class="pk-panel">{items}</div></details>')

    parents = (f'<div class="pk-parents" role="group" aria-label="Persempit daftar campaign">{parent_dd("channel", "Channel")}{parent_dd("source", "Source")}{parent_dd("medium", "Medium")}</div>'
               '<div id="pk-drop" class="pk-note" role="status" aria-live="polite" hidden></div>') if rel else ""
    used = {r["name"].casefold() for r in rows}
    picker_rows = "".join(
        f'<label class="pk-opt" data-opt data-key="campaign" data-label="{escape(n)}" data-pick-name="{escape(n)}"{" hidden" if n.casefold() in used else ""}><input type="checkbox" value="{escape(n)}" style="width:20px;height:20px;margin:0"><span>{escape(n)}</span></label>' for n in picker
    )
    table_css = "[hidden]{display:none!important}.pk{border:1px solid #dfe7f0;border-radius:6px;background:#f4f7fb;padding:16px;margin-top:12px}.pk-list{max-height:264px;overflow-y:auto;background:#fff;border:1px solid #dfe7f0;border-radius:6px;padding:0 12px}.pk-opt{display:flex;align-items:center;gap:10px;min-height:44px;color:#17283e;cursor:pointer}.pk-note{margin:6px 0;color:#607188}.pk-parents{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-bottom:12px;align-items:start}.pk-dd summary{display:flex;align-items:center;justify-content:space-between;gap:8px;min-height:44px;box-sizing:border-box;padding:0 12px;border:1px solid #6f8199;border-radius:6px;background:#fff;color:#17283e;cursor:pointer;list-style:none}.pk-dd summary::-webkit-details-marker{display:none}.pk-dd summary::after{content:\"\";width:8px;height:8px;border-right:2px solid #607188;border-bottom:2px solid #607188;transform:rotate(45deg);margin:-4px 0 0 4px;flex:none}.pk-dd[open] summary::after{transform:rotate(-135deg);margin-top:4px}.pk-dd .fl{font-weight:500;flex:1}.pk-dd .fv{color:#607188}.pk-panel{margin-top:6px;border:1px solid #dfe7f0;border-radius:6px;background:#fff;padding:4px 12px;max-height:240px;overflow-y:auto}.vw-linkbtn{display:inline-flex;align-items:center;min-height:44px;padding:0 4px;border:0;background:none;color:#2159a9;font:600 14px Inter,Arial,sans-serif;cursor:pointer}.bd th{white-space:normal}.bd .cell{min-width:120px}.bd input:disabled{background:#f4f7fb;color:#607188;border-color:#dfe7f0}"
    week_ths = "".join(week_head(*w) for w in weeks)
    sections = (
        f'<style nonce="{nonce}">{table_css}</style>'
        '<main class="vw-main"><nav class="vw-crumbs" aria-label="Posisi halaman"><a class="vw-link" href="/">Daftar report</a><span class="sep" aria-hidden="true">/</span><span aria-current="page" style="color:#17283e">Budget</span></nav>'
        '<h1 class="vw-h1">Budget</h1>'
        '<p class="vw-lead" style="max-width:680px">Budget total dan budget per campaign untuk satu bulan, serta spend per campaign. Spend mingguan dan spend bulanan diisi terpisah dan tidak dijumlahkan satu sama lain. Daftar campaign diambil dari kolom Campaign di Campaign Tracker.</p>'
        f'<form method="post" action="/budget" id="budget-form" class="vw-box" style="padding:24px;margin-bottom:32px"><input type="hidden" name="csrf" value="{escape(csrf)}"><input type="hidden" name="base" value="{escape(base_id)}">'
        '<div style="display:flex;flex-wrap:wrap;gap:16px;margin-bottom:24px">'
        f'<div class="vw-field" style="flex:0 1 200px"><label for="bu">Perusahaan</label><select id="bu" name="bu" data-reload>{company_options}</select></div>'
        f'<div class="vw-field" style="flex:0 1 220px"><label for="month">Bulan</label><select id="month" name="month" data-reload>{month_choices}</select></div>'
        f'<div class="vw-field" style="flex:0 1 240px"><label for="total">Total budget (Rp)</label><input id="total" name="total" type="text" inputmode="numeric" placeholder="Angka dalam Rupiah" value="{escape(total_text)}"{invalid("total")}></div></div>'
        '<div style="display:flex;flex-wrap:wrap;align-items:flex-end;justify-content:space-between;gap:12px 16px;margin-bottom:12px"><div><h2 class="vw-h2">Campaign</h2>'
        '<p style="margin:0;max-width:640px;color:#607188">Tambahkan campaign dari Campaign Tracker, lalu isi budget dan spend-nya. Campaign yang sudah punya isian di bulan ini tampil otomatis.</p></div>'
        '<button type="button" id="buka" class="vw-btn alt" aria-expanded="false" aria-controls="picker">Tambah campaign</button></div>'
        '<div id="picker" class="pk" role="group" aria-labelledby="picker-title" hidden>'
        '<h3 id="picker-title" style="margin:0 0 4px;font:600 15px/1.4 Inter,Arial,sans-serif;color:#17283e">Pilih campaign yang mau ditambahkan</h3>'
        '<p style="margin:0 0 12px;color:#394d65">Daftar ini berasal dari kolom Campaign di Google Sheet Campaign Tracker. Persempit dulu dengan Channel, Source, dan Medium bila perlu, lalu centang satu atau beberapa campaign dan tekan tombol biru di bawah.</p>'
        + parents +
        '<div class="vw-field"><label for="cari">Cari nama campaign</label><input id="cari" type="search" autocomplete="off" placeholder="Contoh: brand, gps, search"></div>'
        '<div id="pick-note" class="pk-note" role="status" aria-live="polite"></div>'
        f'<div class="pk-list" id="pick-list">{picker_rows}<p id="pick-empty" hidden style="margin:12px 0;color:#394d65"></p></div>'
        '<div style="display:flex;gap:12px;margin-top:12px"><button type="button" id="tambah" class="vw-btn" disabled>Tambahkan campaign terpilih</button><button type="button" id="batal" class="vw-btn alt">Batal</button></div>'
        '<p id="pick-hint" class="pk-note" style="margin:8px 0 0"></p></div>'
        f'<div id="empty-box" class="vw-box"{" hidden" if rows else ""} style="padding:24px;margin-top:12px"><div style="font-weight:600;color:#17283e;margin-bottom:4px">Belum ada campaign di budget ini</div>'
        '<div>Pilih Tambah campaign untuk memilih dari daftar Tracker. Budget, spend mingguan, dan spend bulanan muncul setelah ada campaign.</div></div>'
        f'<div id="tables"{"" if rows else " hidden"}>'
        '<h3 style="margin:16px 0 8px;font:600 14px/1.4 Inter,Arial,sans-serif;color:#17283e">Budget per campaign</h3>'
        f'<div class="vw-box" style="overflow-x:auto"><table class="vw-table bd" id="t-budget"><caption class="vw-sr">Budget per campaign</caption><thead><tr><th scope="col">Campaign</th><th scope="col" class="num">Budget (Rp)</th><th scope="col" class="num"><span class="vw-sr">Aksi</span></th></tr></thead>'
        f'<tbody>{budget_rows}</tbody><tfoot><tr><td data-label="Campaign">Jumlah per campaign</td><td data-label="Budget (Rp)" class="num" data-sum="b">Rp 0</td><td></td></tr></tfoot></table></div>'
        '<p style="margin:8px 0 0;color:#607188">Hapus mengeluarkan campaign dari budget bulan ini saat disimpan. Lead dan report campaign itu tidak berubah, dan versi lama tetap ada di riwayat.</p>'
        '<h2 class="vw-h2" style="margin-top:32px">Spend per minggu</h2>'
        '<p style="margin:0 0 12px;color:#607188">Isi spend tiap minggu penuh, Senin sampai Minggu, termasuk minggu yang melewati pergantian bulan: W44 adalah 26 Okt sampai 1 Nov dan W45 lanjut dari 2 Nov. Angka ini dipakai kolom Spend Week di report. Minggu yang belum berjalan belum bisa diisi.</p>'
        f'<div class="vw-box" style="overflow-x:auto"><table class="vw-table bd" id="t-weeks" style="min-width:860px"><caption class="vw-sr">Spend per campaign per minggu</caption><thead><tr><th scope="col">Campaign</th>{week_ths}</tr></thead>'
        f'<tbody>{week_rows}</tbody><tfoot><tr><td data-label="Campaign">TOTAL</td>'
        + "".join(f'<td data-label="{key.split("-")[1]}" class="num" data-sum="w_{key}">Rp 0</td>' for key, _, _ in weeks) + '</tr></tfoot></table></div>'
        '<h2 class="vw-h2" style="margin-top:32px">Spend bulanan</h2>'
        '<p style="margin:0 0 12px;color:#607188">Isi total spend bulan berjalan (kumulatif) per campaign, sesuai angka di platform iklan. Ini tidak dihitung dari spend mingguan, jadi bisa berbeda. Report menampilkan angka bulanan terakhir yang diisi sampai tanggal report itu.</p>'
        f'<div class="vw-field" style="flex:0 1 240px;max-width:240px;margin-bottom:12px"><label for="as_of">Spend bulan diisi sampai tanggal</label><input id="as_of" name="as_of" type="date" value="{escape(as_of_text)}"{invalid("as_of")}></div>'
        f'<div class="vw-box" style="overflow-x:auto"><table class="vw-table bd" id="t-month"><caption class="vw-sr">Spend bulanan per campaign</caption><thead><tr><th scope="col">Campaign</th><th scope="col" class="num">Spend {escape(month_label(month))} (Rp)</th></tr></thead>'
        f'<tbody>{month_rows}</tbody><tfoot><tr><td data-label="Campaign">TOTAL</td><td data-label="Spend" class="num" data-sum="m">Rp 0</td></tr></tfoot></table></div></div>'
    )
    messages = "".join(f'<p role="alert" class="vw-alert" style="margin:20px 0 0">{escape(m)}</p>' for k, m in errors.items())
    flash = f'<p role="status" class="vw-ok">{escape(notice)}</p>' if notice else ""
    fail = f'<p role="alert" class="vw-alert" style="margin:20px 0 0">{escape(failed)}</p>' if failed else ""
    if history:
        hrows = "".join(
            f'<tr><td data-label="Bulan">{escape(month_label(h["month"]))}</td><td data-label="Total budget" class="num">{("Rp " + _digits(h["total_budget"])) if h["total_budget"] is not None else "-"}</td>'
            f'<td data-label="Total spend" class="num">{_history_spend(h)}</td><td data-label="Spend bulan sampai">{escape(h["spend_as_of"].strftime("%d-%m-%Y")) if h["spend_as_of"] else "-"}</td>'
            f'<td data-label="Dicatat pada">{escape(dt_text(h["saved_at"]))} oleh {escape(h["saved_by"])}</td></tr>' for h in history
        )
        hist = (f'<div class="vw-box"><table class="vw-table"><caption class="vw-sr">Riwayat budget {escape(label)}</caption><thead><tr><th scope="col">Bulan</th><th scope="col" class="num">Total budget</th><th scope="col" class="num">Total spend</th>'
                f'<th scope="col">Spend bulan sampai</th><th scope="col">Dicatat pada</th></tr></thead><tbody>{hrows}</tbody></table></div>')
    else:
        hist = (f'<div class="vw-box" style="padding:24px"><div style="font-weight:600;color:#17283e;margin-bottom:4px">Belum ada budget tersimpan untuk {escape(label)}</div>'
                '<div>Sampai budget disimpan, report menampilkan "Budget belum diatur".</div></div>')
    tail = (
        f'{messages}{flash}{fail}<div style="margin-top:20px"><button class="vw-btn" type="submit">Simpan budget dan spend</button></div></form>'
        f'<section aria-label="Riwayat budget"><h2 class="vw-h2">Riwayat budget {escape(label)}</h2><p style="margin:0 0 12px;color:#607188">Setiap penyimpanan menambah satu baris. Riwayat lama tidak ditimpa.</p>{hist}</section></main>'
        + "".join(f'<template id="tpl-{name}">{html}</template>' for name, html in (("budget", t_budget), ("weeks", t_weeks), ("month", t_month)))
    )
    script = f'<script nonce="{nonce}">{BUDGET_JS.replace("__CASCADE__", cascade.CASCADE_JS).replace("__REL__", cascade.rel_json(rel) if rel else "null").replace("__WEEKS__", json.dumps([k for k, _, _ in weeks]))}</script>'
    return page("Budget", sections + tail, nonce, csrf, menu(csrf, me, "budget"), script)


def _history_spend(h: dict) -> str:
    values = [c.get("month_spend") for c in (h["data"].get("campaigns") or {}).values() if c.get("month_spend") is not None]
    return "Rp " + _digits(sum(values)) if values else "-"


BUDGET_JS = r"""
(function(){
  var form=document.getElementById('budget-form'),weeks=__WEEKS__;
  form.querySelectorAll('select[data-reload]').forEach(function(s){s.addEventListener('change',function(){
    var u=new URL(location.href);u.searchParams.set('bu',document.getElementById('bu').value);u.searchParams.set('month',document.getElementById('month').value);location.href=u.toString();});});
  function num(el){var d=(el.value||'').replace(/[^0-9]/g,'');return d?parseInt(d,10):0;}
  function fmt(n){return 'Rp '+String(n).replace(/\B(?=(\d{3})+(?!\d))/g,'.');}
  function sums(){
    var all=form.querySelectorAll('[data-sum]');
    all.forEach(function(cell){
      var key=cell.dataset.sum,sel=key==='b'?'#t-budget input[name^=b_]':key==='m'?'#t-month input[name^=m_]':'#t-weeks input[name$="'+key.slice(2)+'"]';
      var t=0;form.querySelectorAll(sel).forEach(function(i){t+=num(i);});cell.textContent=fmt(t);
    });
  }
  form.addEventListener('input',function(e){if(e.target.matches('.cell input'))sums();});
  var opener=document.getElementById('buka'),box=document.getElementById('picker'),q=document.getElementById('cari'),note=document.getElementById('pick-note'),
      empty=document.getElementById('pick-empty'),addBtn=document.getElementById('tambah'),hint=document.getElementById('pick-hint'),tables=document.getElementById('tables'),emptyBox=document.getElementById('empty-box');
  var opts=Array.prototype.slice.call(document.querySelectorAll('#pick-list [data-pick-name]'));
  function norm(t){return t.toLowerCase().replace(/\s+/g,' ').trim();}
  function used(){var u={};form.querySelectorAll('#t-budget [data-name]').forEach(function(c){u[norm(c.textContent)]=1;});return u;}
  function picked(){return opts.filter(function(o){return o.querySelector('input').checked;});}
  __CASCADE__
  var rel=__REL__,casc=rel?makeCascade(rel):null,allOpts=[].slice.call(document.querySelectorAll('#picker [data-opt]')),drop=document.getElementById('pk-drop');
  function refresh(){
    var u=used(),v=norm(q.value),avail=0,shown=0;
    opts.forEach(function(o){var n=o.dataset.pickName;if(u[norm(n)])o.querySelector('input').checked=false;});
    var r=casc?casc(allOpts):{dropped:0};
    opts.forEach(function(o){var n=o.dataset.pickName,free=!u[norm(n)],cut=o.dataset.cut==='1';
      var match=free&&!cut&&(!v||norm(n).indexOf(v)>=0);o.hidden=!match;if(free)avail++;if(match)shown++;});
    allOpts.forEach(function(o){if(o.dataset.key!=='campaign')o.hidden=o.dataset.cut==='1';});
    document.querySelectorAll('#picker .pk-dd').forEach(function(d){var n=d.querySelectorAll('input:checked').length;d.querySelector('.fv').textContent=n?n+' dipilih':'Semua';});
    if(drop){drop.hidden=!r.dropped;drop.textContent=r.dropped?r.dropped+' pilihan dilepas karena tidak cocok dengan Channel, Source, atau Medium yang dipilih.':'';}
    var k=picked().length;
    note.textContent=(v||shown<avail?'Menampilkan '+shown+' dari '+avail+' campaign. ':avail+' campaign tersedia. ')+(k?k+' dipilih.':'Belum ada yang dipilih.');
    empty.hidden=shown>0;empty.textContent=avail===0?'Semua campaign di Tracker sudah ditambahkan.':'Tidak ada campaign yang cocok dengan filter dan kata kunci ini.';
    addBtn.disabled=k===0;addBtn.textContent=k?'Tambahkan '+k+' campaign terpilih':'Tambahkan campaign terpilih';
    hint.textContent=k?'Setelah ditambahkan, isi budget dan spend di tabel di bawah.':'Tombol aktif setelah ada campaign yang dicentang.';
  }
  function resetParents(){allOpts.forEach(function(o){if(o.dataset.key!=='campaign')o.querySelector('input').checked=false;});}
  function show(){var has=form.querySelectorAll('#t-budget tr[data-row]').length>0;tables.hidden=!has;emptyBox.hidden=has;}
  function toggle(open){box.hidden=!open;opener.setAttribute('aria-expanded',open?'true':'false');if(open){refresh();q.focus();}}
  opener.addEventListener('click',function(){toggle(box.hidden);});
  document.getElementById('batal').addEventListener('click',function(){q.value='';opts.forEach(function(o){o.querySelector('input').checked=false;});resetParents();refresh();toggle(false);opener.focus();});
  q.addEventListener('input',refresh);
  q.addEventListener('keydown',function(e){if(e.key==='Enter')e.preventDefault();});
  box.addEventListener('change',refresh);
  var next=0;form.querySelectorAll('#t-budget tr[data-row]').forEach(function(r){next=Math.max(next,parseInt(r.dataset.idx,10)+1);});
  function addRow(name){
    var i=next++;
    [['budget','#t-budget'],['weeks','#t-weeks'],['month','#t-month']].forEach(function(p){
      var html=document.getElementById('tpl-'+p[0]).innerHTML.split('__I__').join(String(i));
      var tb=form.querySelector(p[1]+' tbody');tb.insertAdjacentHTML('beforeend',html);
      var row=tb.lastElementChild,cell=row.querySelector('[data-name]');cell.insertBefore(document.createTextNode(name),cell.firstChild);
      var hidden=row.querySelector('input[type=hidden]');if(hidden)hidden.value=name;
      row.querySelectorAll('input,button').forEach(function(el){var a=el.getAttribute('aria-label');if(a)el.setAttribute('aria-label',a.replace('campaign baru',name));});
    });
  }
  addBtn.addEventListener('click',function(){
    var chosen=picked().map(function(o){return o.dataset.pickName;});if(!chosen.length)return;
    chosen.forEach(addRow);q.value='';resetParents();refresh();toggle(false);show();sums();opener.focus();
  });
  form.addEventListener('click',function(e){
    var b=e.target.closest('[data-remove]');if(!b)return;
    var idx=b.closest('tr').dataset.idx;
    form.querySelectorAll('tr[data-idx="'+idx+'"]').forEach(function(r){r.remove();});
    show();sums();if(!box.hidden)refresh();opener.focus();
  });
  sums();
})();
"""
