# Performance Marketing Dashboard (weekly & monthly, per BU)

Template HTML 960 px dan generator laporan mingguan atau bulanan per BU. Profil yang tersedia: **BU1** dan **BU2** (lihat `profiles/`). Proses angka **deterministik**: empat CSV Campaign Tracker masuk, minggu ISO ditentukan secara eksplisit, dan satu HTML mandiri serta berkas audit dihasilkan. Script tidak memakai AI, tidak mencari data di internet, dan tidak menulis analisis deskriptif.

Repo ini hanya berisi **template kosong, kode, aturan, dan contoh JSON analisis kosong**. Repo GitHub saat ini bersifat publik. Jangan commit CSV lead, HTML laporan terisi, audit run, atau JSON analisis berisi informasi internal. `.gitignore` mengecualikan berkas tersebut secara default.

## Isi repo

| File | Fungsi |
|---|---|
| `report_view.py` | Tampilan report, persis mengikuti mockup yang disetujui: hanya bagian dan tabel yang ada di mockup. Dipakai generator (report numerik) dan viewer (menambahkan target dan analisis). |
| `profiles/bu1.json`, `profiles/bu2.json` | Profil BU: nama, produk hardware, kolom tanggal SQL, kolom nilai, kolom wajib. |
| `skill/SKILL.md` | Draf skill Claude yang memanggil generator ini (menggantikan skill lama berbasis pandas). |
| `generate_report.py` | Membaca dan memvalidasi empat CSV, menghitung angka, lalu menghasilkan HTML. |
| `METRIC_RULES.md` | Sumber aturan hitung dan pengecualian. Ubah ini bersama kode bila definisi bisnis berubah. |
| `apply_analysis.py` | Langkah opsional terpisah untuk memasukkan teks setelah angka disetujui. |
| `analysis.example.json` | Daftar kolom narasi yang boleh diisi pada langkah kedua. |
| `tests/` | Uji untuk minggu lintas tahun, mata uang, HTML escaping, dan pemisahan analisis. |

## Persiapan sekali di komputer mana pun

Butuh Python 3.11 atau lebih baru. Clone repo ini, lalu jalankan dari folder repo:

```bash
git clone https://github.com/angxsupriyanto/performance-marketing-report.git
cd performance-marketing-report
```

**Windows PowerShell**

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
New-Item -ItemType Directory -Force input, output | Out-Null
```

**macOS / Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
mkdir -p input output
```

Cukup clone sekali; pada minggu berikutnya lakukan `git pull` sebelum menjalankan generator.

## Prosedur tiap minggu: angka lebih dulu

1. Ekspor **empat file CSV BU1 dari snapshot yang sama**: Raw Submission, Raw MQL, Raw SQL, dan Raw Deal Won. Jangan pakai file BU2. Simpan di `input/`; folder ini tidak akan ikut ter-commit.
2. Tentukan minggu laporan **secara eksplisit** dengan ISO week `YYYY-Www`. Misalnya `2026-W39` berarti Senin 21 sampai Minggu 27 September 2026; pembanding otomatis adalah `2026-W38`. Generator memakai **tanggal event**, bukan isi kolom teks `Inbound Week`, `MQL Week`, dan seterusnya.
3. Jalankan perintah di bawah ini. Ganti nama file sesuai hasil ekspor. Empat opsi input harus menunjuk ke file stage yang benar.

**Windows PowerShell**

```powershell
python .\generate_report.py `
  --submission '.\input\BU1 Campaign Tracker - Raw Data - Submission.csv' `
  --mql '.\input\BU1 Campaign Tracker - Raw Data - MQL.csv' `
  --sql '.\input\BU1 Campaign Tracker - Raw Data - SQL.csv' `
  --won '.\input\BU1 Campaign Tracker - Raw Data - Deal Won.csv' `
  --week 2026-W39 `
  --output '.\output\BU1_Week_2026-W39.html'
```

**macOS / Linux**

```bash
python generate_report.py \
  --submission 'input/BU1 Campaign Tracker - Raw Data - Submission.csv' \
  --mql 'input/BU1 Campaign Tracker - Raw Data - MQL.csv' \
  --sql 'input/BU1 Campaign Tracker - Raw Data - SQL.csv' \
  --won 'input/BU1 Campaign Tracker - Raw Data - Deal Won.csv' \
  --week 2026-W39 \
  --output 'output/BU1_Week_2026-W39.html'
```

4. Script menghasilkan `output/BU1_Week_2026-W39.html` dan `output/BU1_Week_2026-W39.audit.json`. Buka HTML langsung di browser. CSS sudah tertanam, jadi HTML tidak memerlukan server, koneksi internet, atau file aset lain. Panel Executive Summary, Funnel Analysis, Pipeline Insight, empat Analysis stage, Cross-stage Insight, dan analisis Campaign Hardware **tetap kosong**.
5. Cocokkan baris `metrics` di audit JSON dengan hitungan CSV menurut tanggal event: Submission = Inbound Date; MQL = MQL Date; SQL = Proposal Price Quote Date; Deal Won = Deal Won Date. Cocokkan SQL Value dengan penjumlahan ARR + OTF tanpa PPN dan Deal Value dengan Total Contract Deal Won. Periksa pula jumlah baris Daftar SQL, footer Cross-stage, footer Campaign Hardware, dan `same_week` pada audit. Bandingkan SHA-256 pada audit bila perlu membuktikan empat file sumber yang dipakai.
6. Jika angka tidak cocok, **perbaiki CSV atau aturan secara eksplisit**, lalu jalankan ulang dari awal. Jangan menambal satu angka di HTML; perubahan manual akan hilang pada run berikutnya.

Generator berhenti dengan pesan kesalahan bila header wajib tidak ada, tanggal atau uang tidak valid, atau minggu terpilih tidak memiliki Submission. Baris `Grand Total` tanpa tanggal event diabaikan; baris data lain tanpa tanggal event wajib akan ditolak.

## Laporan bulanan dan opsi praktis

`--period` menerima `YYYY-Www` (mingguan) atau `YYYY-MM` (bulanan). Bulanan memakai rumus, layout, dan template yang sama: bulan kalender penuh dibanding bulan kalender sebelumnya, tetap berdasarkan **tanggal event**. Label "Week/W" menjadi nama bulan, "Same-week" menjadi "Same-month". `--week` masih diterima sebagai alias lama.

Dua cara memendekkan perintah:

- `--input-dir input/BU1` membaca empat CSV di folder itu. Nama file harus memuat `submission`, `mql`, `sql`, dan `deal won` (tepat satu per kata kunci; kalau ambigu, generator berhenti).
- `--output` boleh dihilangkan; default-nya `output/<BU>_<periode>.html`.

```bash
python generate_report.py --input-dir input/BU1 --period 2026-09   # bulanan
python generate_report.py --input-dir input/BU1 --period 2026-W39  # mingguan
```

Audit JSON kini memuat `bu`, `period`, `period_kind`, dan `comparison_end`. Kunci `same_week` tetap bernama itu untuk kompatibilitas; pada laporan bulanan artinya "inbound dan event dalam bulan yang sama".

## Sumber satu tabel: NEW Customers List (`--table`)

Bila semua data ada di satu tabel dengan satu baris per lead (tab *NEW Customers List*), ekspor tab itu ke CSV dan jalankan:

```bash
python generate_report.py --table input/customers.csv --bu bu2 --period 2026-W39
```

Generator memfilter baris menurut kolom `BU` (nilai harus sama dengan nama profil, mis. `BU2`, spasi dan huruf besar-kecil diabaikan; nilai lain bisa didaftarkan di `bu_values` pada profil), lalu membentuk empat tampilan stage dari kolom tanggal masing-masing. Hasilnya identik dengan memakai empat CSV stage untuk lead yang sama; ini diuji. Aturan tambahan:

- `Record Key` ganda dalam satu BU **ditolak**, karena akan menghitung lead dua kali. Pakai `--allow-duplicate-keys` hanya bila ganda itu disengaja.
- Bila tidak ada baris untuk BU yang diminta, pesan error menampilkan nilai kolom `BU` yang ditemukan.
- Header `ARR + OTF (Tanpa PPN)` dan `Total Contract Deal Won` (tanpa awalan "SUM of") dikenali lewat `value_column_aliases` di profil.
- Tanggal harus `M/D/YYYY` atau `YYYY-MM-DD`. Jika sheet berformat D/M/YYYY, tanggal seperti `3/4/2026` akan terbaca salah tanpa error; pastikan format ekspor sebelum dipakai.
- Audit mencatat `rows_total`, `rows_in_bu`, `rows_without_bu`, jumlah baris per stage, dan SHA-256 file.

## Perbedaan BU1 dan BU2

| | BU1 | BU2 |
|---|---|---|
| Tanggal SQL | `Proposal Price Quote Date` | `SQL Date` |
| SQL Value | `ARR + OTF (Tanpa PPN)` | `Total Contract SQL` |
| Produk | Dashcam, GPS Tracker, Fuel, MDVR, OBD | sama, ditambah **Ecosystem** |

Ecosystem diambil dari nilai `Ecosystem` pada kolom `Campaign Hardware` (diisi manual). Slot analisis produk dan tombol filter dibentuk dari daftar produk profil; untuk BU2 salin `analysis.bu2.example.json` yang memiliki kunci `hardware_ecosystem`. Kunci JSON yang tidak ada di laporan ditolak.

## Menambah BU baru

1. Ambil **hanya baris header** tabel dan bandingkan dengan `profiles/bu1.json`.
2. Salin profil terdekat menjadi `profiles/<bu>.json`, lalu ubah nama, produk, `stage_date_columns`, kolom nilai, dan alias.
3. Jika definisi stage atau rumus berbeda lebih dari kolom dan label, ubah `METRIC_RULES.md` **dulu**, baru kode. Profil mengatur nama kolom dan label, bukan rumus.
4. Tambahkan uji untuk profil tersebut di `tests/test_table_mode.py` dan jalankan dengan `--bu <bu>`.

## Penerapan: Docker, n8n, dan PostgreSQL (dipicu manual)

Jalur tanpa mengekspor CSV sendiri, **tanpa penjadwalan** (Anda yang memicu, dengan periode eksplisit): n8n membaca tab *NEW Customers List*, mengirim **hanya kolom yang dibutuhkan** ke `service/` (layanan HTTP kecil di Docker yang membungkus generator ini), lalu menyimpan HTML, audit, dan `facts` ke database `marketing_reports`. Tombol analisis mengirim `facts` agregat (tanpa nama customer) ke Claude dan menyimpan hasilnya sebagai baris baru. Angka tetap hanya dihitung oleh generator Python; Claude tidak pernah menghitung angka.

- `service/server.py`: `POST /v1/reports?bu=&period=` (isi: CSV), `POST /v1/analysis/apply`, `GET /healthz`. Wajib token Bearer; tidak mau start tanpa token; isi request tidak pernah masuk log.
- `Dockerfile`, `deploy/docker-compose.report-service.example.yml`: pengemasan, tanpa port publik, filesystem read-only, tanpa root.
- `database/`: skrip pembuatan database, role (writer hanya INSERT, reader hanya SELECT), dan tabel append-only. Input identik tidak menambah baris.
- `n8n/`: tiga workflow siap impor dan panduan pemasangannya, termasuk daftar hal yang belum terverifikasi terhadap n8n sungguhan.
- Keluaran generator kini juga `<output>.facts.json` (agregat per stage, source, produk, campaign; tanpa nama perusahaan).

Pengujian: `python -m unittest discover -s tests`. Test database membutuhkan server PostgreSQL sekali pakai: `REPORTS_TEST_ADMIN="host=127.0.0.1 port=5432 user=postgres" python -m unittest tests.test_database` (dengan `pip install -r requirements-dev.txt`). Test itu menolak berjalan bila database `marketing_reports` atau role `report_*` sudah ada.

## Viewer web dan target

`viewer/` adalah web internal (password bersama) untuk melihat report dari database, menekan tombol analisis, dan mengatur target. Pasang dengan `deploy/VIEWER.md`; keputusan desainnya:

- **Target tidak ada di report.** Generator hanya menulis angka aktual dan slot kosong (`Target`, `Progress`, kartu progress). Viewer mengisinya saat report dibuka dari tabel `target_entries`, jadi target bisa diubah kapan saja tanpa membuat report baru.
- **Tabel target append-only.** Menyimpan target menambah baris; tidak ada UPDATE atau DELETE. Mengosongkan target berarti menyimpan 0. Target bulanan per hardware (BU1, Rupiah) berlaku mulai bulan yang dipilih dan seterusnya sampai ada baris baru. Target semester berlaku per semester; target 1 tahun adalah jumlah dua semester. BU2 hanya memakai target semester dan tahun, dalam jumlah SQL campaign Ecosystem.
- **Bulan sebuah minggu = bulan yang memuat hari Kamis minggu itu** (juga untuk semester dan tahun), aturan yang sama dengan penomoran minggu ISO. Progress bulan berjalan menjumlahkan minggu-minggu ISO utuh milik bulan itu sampai minggu report, jadi minggu yang melewati pergantian bulan tidak terbelah.
- **BU1** menampilkan tabel Campaign Hardware (Submission, MQL, SQL, SQL Value, Target, Progress), funnel per hardware dengan bar progress target, dan panel analisis per hardware. **BU2** tidak punya panel hardware; ia menampilkan progress SQL Ecosystem terhadap target semester dan tahun, daftar SQL Ecosystem periode itu (kosong bila tidak ada), dan daftar Deal Won.
- Analisis menerima `targets` (angka progress hasil hitung viewer) di samping `facts`. Model tetap tidak melihat nama perusahaan.

## Analisis deskriptif: langkah kedua setelah angka benar

Salin `analysis.example.json` (BU2: `analysis.bu2.example.json`) menjadi `analysis.json`, isi hanya setelah HTML numerik dan audit diverifikasi. Boleh dikerjakan manual atau melalui proses review terpisah; generator angka tidak membacanya.

**PowerShell**

```powershell
Copy-Item .\analysis.example.json .\analysis.json
python .\apply_analysis.py --report '.\output\BU1_Week_2026-W39.html' --analysis '.\analysis.json' --output '.\output\BU1_Week_2026-W39_Final.html'
```

**macOS / Linux**

```bash
cp analysis.example.json analysis.json
python apply_analysis.py --report output/BU1_Week_2026-W39.html --analysis analysis.json --output output/BU1_Week_2026-W39_Final.html
```

Berkas numerik asli tetap utuh. Script kedua hanya memasukkan teks yang telah disediakan dan meng-escape HTML; ia tidak menghitung ulang angka. Bila ingin mengulang analisis, ubah JSON lalu jalankan langkah kedua lagi.

## Aturan perubahan agar tidak ada keputusan tersembunyi

- Ubah rumus di `METRIC_RULES.md` dan `generate_report.py` **bersamaan**; lakukan review kode sebelum merge.
- Jangan mengubah angka atau interpretasi week berdasarkan label `Week` di CSV jika tanggal event tidak cocok.
- Saat kategori hardware atau nama kolom berubah, perbarui daftar mapping dan uji sebelum memakai data baru.
- Jalankan `python -m unittest discover -s tests -v` setelah mengubah generator.
- Commit hanya template, kode, panduan, dan uji. Laporan terisi serta data mentah tetap di luar GitHub.

## Pemakaian dari GitHub

Repo ini adalah sumber template dan aturan. Dari komputer lain, clone URL di atas, lakukan persiapan sekali, dan gunakan empat CSV lokal tiap minggu. Perubahan kode di GitHub diambil dengan `git pull`. **Jangan mengunggah file CSV ke GitHub untuk menjalankan laporan.**
