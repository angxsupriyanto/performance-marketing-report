# Arsitektur

## Gambaran satu halaman

```text
Google Sheet "NEW Customers List"
        │ (dibaca n8n, manual)
        ▼
n8n ── Report Generate ──► service/ (Docker) ── generate_report.py ──► HTML + audit + facts
 │                                                                         │
 │                                                          INSERT (report_writer)
 │                                                                         ▼
 ├── Performa Generate ──► service/ /v1/performa ──► reports.performance_snapshots
 │                                                                         ▼
 └── Report Analysis ◄── webhook ◄── viewer/ (web, Cloudflare Tunnel) ◄── PostgreSQL marketing_reports
        │  facts agregat (tanpa nama)        ▲   SELECT / INSERT terbatas (report_viewer)
        ▼                                    │
   model AI (9router, kompatibel OpenAI) ────┘  teks analisis disimpan sebagai baris baru
```

Tiga prinsip yang membentuk semuanya:

1. **Angka deterministik.** `generate_report.py` menghitung semua angka dari data lead. Model AI tidak pernah menghitung; ia hanya menulis narasi dari `facts` agregat dan tidak melihat nama perusahaan lead.
2. **Report adalah catatan angka; sisanya digabung saat dibuka.** Target, budget, Action, dan edit analisis tidak ada di HTML report. Viewer menggabungkannya saat halaman dibuka, jadi mengubahnya tidak perlu membuat report ulang.
3. **Append-only.** Data yang ditulis pengguna disimpan sebagai baris baru (tanpa UPDATE atau DELETE), sehingga setiap perubahan punya riwayat.

## Komponen

### Generator (`generate_report.py`, `report_view.py`, `profiles/`)
- Masukan: tabel satu baris per lead (`--table`) atau empat CSV per tahap. Profil per BU (`profiles/bu1.json`, `bu2.json`) menentukan kolom tanggal SQL, kolom nilai, produk, dan aturan khusus (mis. `sql_max_age_months` untuk BU1).
- Keluaran: HTML mandiri yang menyematkan `view` (JSON) sebagai sumber tampilan, `.audit.json` (angka, jumlah baris, SHA-256 sumber), `.facts.json` (agregat tanpa nama), `.lists.json`.
- `report_view.py` merender HTML dari `view`. Viewer memakai modul yang sama untuk merender ulang report dengan target, budget, Action, dan analisis. Fungsi `print_document` membuat versi cetak untuk PDF.
- `performance()` di `generate_report.py` membuat baris anonim per lead untuk halaman Performa (tanpa nama, kontak, atau Record Key).
- Aturan hitung: [`METRIC_RULES.md`](../METRIC_RULES.md).

### Layanan (`service/`)
Server HTTP kecil yang membungkus generator. Tanpa status, tanpa log isi request, wajib token Bearer, tanpa port publik. Endpoint: `POST /v1/reports?bu=&period=`, `POST /v1/performa`, `POST /v1/analysis/apply`, `GET /healthz`. `python -m service.selftest` memeriksa layanan yang sedang berjalan.

### n8n (`n8n/`)
Tiga workflow yang **dihasilkan** oleh `n8n/build_workflows.py` (jangan edit JSON langsung; ubah `n8n/code`, `n8n/sql`, `n8n/prompts`, lalu jalankan ulang skrip dan commit hasilnya; tes gagal bila berbeda):

| Workflow | Fungsi |
|---|---|
| `Report_Generate_v1` | Sheet → Build CSV → layanan → simpan run → ringkasan Telegram |
| `Performa_Generate_v1` | Sheet → layanan `/v1/performa` → snapshot Performa |
| `Report_Analysis_Button_v1` | Validate Request → Load Latest Run → Prepare Analysis Request → Ask Model → Parse Analysis → Apply Analysis → Prepare Save → Save Analysis |

Prompt analisis: `n8n/prompts/analysis_v2.md`. Node Code memanggil node lain lewat nama; bila node di kanvas diganti nama, kode melaporkan nama yang hilang (`n8n/code/_ref.js`).

### Database (`database/`, lihat [`DATA_MODEL.md`](DATA_MODEL.md))
`marketing_reports` adalah database **terpisah** di server PostgreSQL yang sudah ada, dengan skema `reports`. Empat role: `report_owner` (pemilik, tanpa login), `report_writer` (n8n), `report_reader`, `report_viewer` (web).

### Viewer (`viewer/`)
Server HTTP Python tanpa framework. `app.py` memuat rute dan logika halaman; modul lain:

| Modul | Fungsi |
|---|---|
| `auth.py`, `access.py` | Login (scrypt, cookie HMAC), pembatas percobaan, akses per perusahaan, nama tampil |
| `store.py` | Semua akses database (satu koneksi pendek per permintaan, query berparameter) |
| `pages.py` | Kerangka halaman, menu, Daftar report, Budget, form Action, skrip sisi browser |
| `performance.py`, `performance_pages.py` | Perhitungan dan tampilan Performa dari baris lead anonim |
| `cascade.py` | Filter berjenjang Channel → Source → Medium → Campaign (dipakai Performa dan Budget) |
| `targets.py` | Aturan target dan penggabungan target ke report |
| `budget.py` | Kalender, bentuk budget di report, validasi form, konteks budget untuk analisis |
| `actions.py` | Daftar Action periode: validasi dan batas |
| `analysis_edits.py` | Teks panel mana yang tampil (edit manual terbaru atau AI terbaru) |
| `pdf.py` | PDF lewat Chromium tanpa tampilan |
| `theme.py` | Dark mode: mengganti warna hex menjadi variabel CSS, palet gelap, tombol pilihan |

Rute utama: `/` (daftar), `/report/<bu>/<periode>` dan `/report/<bu>/<periode>/pdf`, `/performa`, `/budget`, `/targets`, `/users`, `/companies`, `/login`, `/healthz`, serta `/api/analysis`, `/api/analysis/edit`, `/api/analysis/status`, `/api/actions`. Semua POST butuh token CSRF dan `Origin` yang cocok.

## Alur yang paling sering membingungkan

**Membuat report.** Pemicu manual di n8n dengan `bu` dan `period` eksplisit. Satu report tersimpan per kombinasi (BU, periode, isi sheet, versi kode generator); menjalankan ulang dengan input yang sama tidak menambah baris. Karena versi kode ikut kunci, setelah generator diperbarui, menjalankan ulang menghasilkan report baru.

**Membuat analisis.** Admin menekan *Buat analisis* di viewer → form Action periode (boleh kosong) → viewer menyimpan Action, menyusun konteks budget, lalu memanggil webhook n8n → n8n mengirim `facts`, `targets`, `actions`, dan `budget` ke model → hasilnya disisipkan lewat layanan dan disimpan sebagai baris baru di `report_analyses`. Panel **Next Action** ikut dihasilkan dan disimpan bersama analisis; viewer menampilkannya walau halaman tersimpan belum punya slotnya.

**Menampilkan report.** Viewer membaca HTML run terbaru, mengambil `view` yang tersemat, lalu merender ulang dengan: target terbaru (`target_entries`), budget terbaru bulan itu (`budget_snapshots`), Action terbaru periode (`report_actions`), dan teks analisis (edit manual terbaru yang lebih baru dari analisis AI terbaru, selain itu AI). Hasilnya dibungkus kerangka (menu, tombol) dan dikirim lewat `send()`, yang di titik terakhir menerapkan `theme.apply` untuk dark mode.

**PDF.** `GET /report/<bu>/<periode>/pdf` membuat `print_document` dari HTML mentah (tanpa tema), menulisnya ke folder sementara, dan mencetaknya dengan Chromium tanpa jaringan. Satu PDF pada satu waktu. PDF selalu terang karena tidak pernah melewati `theme.apply`.

**Performa.** Snapshot berisi satu baris per lead. Seluruh penghitungan (per hari, minggu, bulan, filter, matriks cohort) dilakukan di viewer saat halaman dibuka; report tidak terpengaruh filter.

## Keamanan (ringkas; rincian di `deploy/VIEWER.md`)

Akun per orang dengan peran admin atau pengguna; peran dibaca dari database di setiap permintaan. Cookie `HttpOnly`, `Secure`, `SameSite=Strict`. CSP ketat dengan nonce dan tanpa skrip pihak ketiga. Role database membatasi apa yang bisa ditulis web. Aplikasi terbuka lewat Cloudflare Tunnel di `officehours.pesankopi.com`; lapisan Cloudflare Access belum terpasang (lihat `KNOWN_GAPS.md`).
