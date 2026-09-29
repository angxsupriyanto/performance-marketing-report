# BU1 Weekly Performance Dashboard

Template HTML 960 px dan generator laporan mingguan BU1. Proses angka **deterministik**: empat CSV Campaign Tracker masuk, minggu ISO ditentukan secara eksplisit, dan satu HTML mandiri serta berkas audit dihasilkan. Script tidak memakai AI, tidak mencari data di internet, dan tidak menulis analisis deskriptif.

Repo ini hanya berisi **template kosong, kode, aturan, dan contoh JSON analisis kosong**. Repo GitHub saat ini bersifat publik. Jangan commit CSV lead, HTML laporan terisi, audit run, atau JSON analisis berisi informasi internal. `.gitignore` mengecualikan berkas tersebut secara default.

## Isi repo

| File | Fungsi |
|---|---|
| `dashboard_template.html` | Tampilan kosong dengan layout dan panel analisis kosong. Bisa dibuka langsung sebagai preview desain. |
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

## Analisis deskriptif: langkah kedua setelah angka benar

Salin `analysis.example.json` menjadi `analysis.json`, isi hanya setelah HTML numerik dan audit diverifikasi. Boleh dikerjakan manual atau melalui proses review terpisah; generator angka tidak membacanya.

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
