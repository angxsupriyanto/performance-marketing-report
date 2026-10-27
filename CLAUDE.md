# CLAUDE.md: orientasi untuk model dan pengembang yang baru masuk

Baca file ini dulu. Ia sengaja pendek; detailnya ada di `docs/`.

## Apa produk ini

Dashboard laporan **digital marketing** untuk dua perusahaan (id internal `bu1` dan `bu2`; nama tampil diatur admin, mis. McEasy dan LOL). Data lead dibaca dari Google Sheet tab *NEW Customers List*. Angka dihitung **deterministik oleh Python** (tanpa AI), disimpan di PostgreSQL, dan dilihat lewat web internal (`viewer/`). AI hanya menulis narasi analisis dari angka agregat. Status: **MVP terkunci**, lihat `docs/ROADMAP.md` untuk fase berikutnya.

## Peta repo

| Jalur | Isi |
|---|---|
| `generate_report.py`, `report_view.py`, `profiles/` | Generator angka dan tampilan report. Aturan hitung: `METRIC_RULES.md` |
| `service/` | Layanan HTTP kecil (Docker) yang membungkus generator; dipanggil n8n |
| `n8n/` | Tiga workflow, **dihasilkan** oleh `n8n/build_workflows.py` dari `n8n/code`, `n8n/sql`, `n8n/prompts` |
| `database/` | Migrasi SQL `000`–`009`, `verify_install.sql` |
| `viewer/` | Web app: login, report, Performa, Budget, Target, Action, PDF, pengguna, dark mode |
| `deploy/` | Docker compose contoh, skrip pasang, `VIEWER.md` |
| `tests/` | Uji otomatis (±300 tes) |
| `docs/` | Arsitektur, keputusan, data, runbook, roadmap, celah yang diketahui |

## Perintah yang paling sering dipakai

```bash
python3 -m unittest discover -s tests        # ±140 detik; jalankan di latar bila perlu
python3 -m unittest tests.test_budget        # satu berkas
# Tes database butuh PostgreSQL sekali pakai:
REPORTS_TEST_ADMIN="host=127.0.0.1 port=5432 user=postgres" python3 -m unittest tests.test_database
python3 n8n/build_workflows.py               # setelah mengubah n8n/code, sql, atau prompts
```

## Aturan kerja yang berlaku (jangan dilanggar tanpa persetujuan pemilik)

1. **Angka hanya dihitung oleh generator Python.** Model AI tidak pernah menghitung dan tidak melihat nama perusahaan lead. Ubah rumus di `METRIC_RULES.md` dan kode **bersamaan**.
2. **Tanpa penjadwalan.** Semua workflow dipicu manual, periode selalu eksplisit.
3. **Perubahan tampilan: mockup dulu, lalu implementasi setelah disetujui.** Mockup dibuat sebagai artifact desain, lalu pemilik menyetujui.
4. **Keputusan yang sudah diambil ada di `docs/DECISIONS.md`.** Jangan membatalkannya diam-diam; bila perlu diubah, tanyakan dulu dan catat perubahannya.
5. **Jangan membaca atau meminta isi berkas rahasia** (`viewer_*`, token tunnel, `reports_db_secrets/`, `*.local.yml`). Repo ini **publik**: jangan commit data lead, report terisi, nama campaign internal, atau kredensial.
6. **Tabel di database bersifat append-only** (target, budget, edit analisis, action, snapshot). Jangan menambah UPDATE atau DELETE untuk data pengguna.
7. **Jangan menambahkan pernyataan berhasil tanpa bukti.** Laporkan tes yang gagal apa adanya; tandai yang belum diverifikasi di `docs/KNOWN_GAPS.md`.
8. Pengguna bekerja di **Windows PowerShell** dan menjalankan Docker sendiri; berikan perintah PowerShell yang bisa ditempel langsung (lihat `docs/RUNBOOK.md`).
9. Bahasa antarmuka dan dokumen: **Bahasa Indonesia** yang sederhana. Hindari istilah kode (`same_period`) dalam teks yang dilihat pengguna.

## Pola yang dipakai di kode

- **Warna** ditulis sebagai hex terang di kode halaman; `viewer/theme.py` menggantinya dengan variabel CSS saat halaman dikirim (dark mode). Warna baru yang ingin ikut mode gelap harus ada di `PALETTE` atau `FIXED` di sana.
- **Target, budget, Action, dan edit analisis tidak disimpan di report.** Viewer menggabungkannya saat halaman dibuka, jadi mengubahnya tidak perlu membuat report baru.
- **Bulan sebuah minggu** = bulan yang memuat hari Kamis minggu itu (aturan ISO).
- **Hasil uji lebih penting dari keyakinan:** uji perubahan di browser dengan data contoh (Playwright tersedia), bukan hanya tes unit.

## Bila ingin lanjut ke fitur berikutnya

Baca `docs/ROADMAP.md` (pemetaan iklan, rencana budget, proyeksi KPI) dan `docs/KNOWN_GAPS.md` lebih dulu. Roadmap memuat mockup, asumsi, dan kritik yang sudah dibahas dengan pemilik, supaya diskusi tidak diulang.
