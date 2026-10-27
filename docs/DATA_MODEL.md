# Model data

Database **`marketing_reports`**, skema **`reports`**, di server PostgreSQL yang sudah ada tetapi terpisah dari database lain. Migrasi ada di `database/` dan diterapkan berurutan (aman diulang). `database/verify_install.sql` memeriksa pemasangan: **23 baris harus PASS**.

## Role

| Role | Dipakai oleh | Hak |
|---|---|---|
| `report_owner` | pemilik objek (tanpa login) | memiliki skema dan tabel |
| `report_writer` | n8n | SELECT dan INSERT pada `report_runs`, `report_analyses`, `performance_snapshots`; SELECT pada tabel lain |
| `report_reader` | pembacaan | SELECT |
| `report_viewer` | web viewer | SELECT report dan analisis; INSERT `target_entries`, `analysis_edits`, `budget_snapshots`, `report_actions`; SELECT, INSERT, UPDATE pada `viewer_users` dan `company_names` |

Tidak ada role yang bisa DELETE. Role penulis dan pembaca report tidak bisa membaca `viewer_users`.

## Tabel

| Tabel | Migrasi | Sifat | Isi |
|---|---|---|---|
| `report_runs` | 001, 003 | append-only | Satu run = report angka satu BU dan periode: `metrics`, `audit`, `facts`, `analysis_keys`, `numeric_html`. Kunci idempotensi: (BU, periode, SHA-256 sumber, versi generator) |
| `report_analyses` | 001 | append-only | Satu baris per tekan tombol analisis, terkait ke run: `model`, `prompt_version`, `analysis` (jsonb, termasuk `next_action`) |
| `target_entries` | 002 | append-only | Target: `scope` = `hardware_month` (BU1, Rupiah per produk per bulan) atau `semester` (per semester); nilai terbaru per kunci dibaca lewat view `targets_latest` |
| `viewer_users` | 004 | boleh diubah | Akun: username, hash scrypt, `role` (`admin` atau `user`), akses perusahaan (`all_companies` atau daftar), `active`. Tidak pernah dihapus |
| `company_names` | 004 | boleh diubah | Nama tampil per `bu` (`bu1`, `bu2`) |
| `analysis_edits` | 005 | append-only | Edit manual per panel (`panel_key`, `body`); `body` kosong berarti "kembalikan ke versi AI" |
| `budget_snapshots` | 006 | append-only | Satu versi lengkap per simpan: `month`, `total_budget`, `spend_as_of`, `data.campaigns{nama: {budget, month_spend, weeks{minggu: jumlah}}}` |
| `performance_snapshots` | 007, 008 | append-only | Snapshot halaman Performa. Format v2: satu baris anonim per lead (`leads`) dan daftar nilai filter (`dims`); lihat komentar di `008` |
| `report_actions` | 009 | append-only | Daftar Action per (BU, periode): `items` (jsonb, maksimal 30 butir `{action, campaign, note}`) |

View: `run_index` (run tanpa HTML), `latest_reports` (run terbaru per BU dan periode beserta analisis terbaru), `targets_latest`.

## Aturan yang tertanam di skema atau kode

- **Versi terbaru menang.** Untuk budget, Action, dan target, baris terbaru per kunci adalah yang berlaku; yang lama menjadi riwayat. Menghapus budget campaign berarti menyimpan versi baru tanpa baris itu.
- **Bentrok simpan budget.** Menyimpan budget membawa `base` (id snapshot yang dibuka). Bila snapshot terbaru sudah berbeda, simpan ditolak agar tidak menimpa tanpa sadar.
- **Bulan sebuah minggu** = bulan yang memuat Kamis minggu itu; ini menentukan di halaman bulan mana spend mingguan diisi.
- **Privasi.** Snapshot Performa dan `facts` tidak memuat nama perusahaan lead, kontak, atau Record Key. Nama campaign ikut tersimpan di budget dan bisa terkirim ke analisis; nama perusahaan lead tidak.
- **Report lama tetap utuh.** Perubahan aturan hitung tidak menulis ulang `numeric_html` lama; angka baru muncul setelah Report Generate dijalankan lagi.

## Menambah migrasi

1. Buat `database/0NN_nama.sql` yang aman diulang (`IF NOT EXISTS`) dan memberi hak seminimal mungkin.
2. Tambahkan ke `deploy/install-viewer-db.sh` dan, bila perlu, tambah baris di `database/verify_install.sql` (ubah jumlah PASS di dokumen ini dan di `deploy/VIEWER.md`).
3. Tambahkan tes di `tests/test_database.py` (butuh PostgreSQL sekali pakai).
4. Update dokumen ini dalam commit yang sama.
