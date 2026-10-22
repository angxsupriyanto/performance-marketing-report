---
name: performance-marketing-report
description: Buat laporan performa marketing mingguan atau bulanan (BU1, BU2 bila profilnya sudah ada) dari tabel NEW Customers List (atau empat CSV Campaign Tracker) memakai generator deterministik di repo performance-marketing-report. Gunakan saat pengguna menyebut laporan marketing, performance report, WoW, MoM, Inbound, MQL, SQL, Deal Won, atau mengunggah CSV campaign.
---

# Performance Marketing Report

> Jalur utama sekarang lewat n8n dan layanan Docker yang dipicu manual (lihat README, bagian *Penerapan*). Skill ini hanya untuk pemakaian ad hoc lewat chat.

Angka dihitung oleh `generate_report.py` di repo `angxsupriyanto/performance-marketing-report`. **Jangan menghitung angka sendiri** (tanpa pandas, tanpa rumus ad hoc di chat). Tugas Anda: menjalankan generator, memverifikasi, lalu menulis analisis.

## Sebelum mulai, tanyakan bila belum jelas
1. **BU**: BU1 atau BU2. Profil tersedia: bu1 dan bu2. Jika `profiles/<bu>.json` tidak ada di repo, berhenti dan katakan profil belum tersedia. Jangan memakai profil BU lain.
2. **Periode**: mingguan `YYYY-Www` atau bulanan `YYYY-MM`. Jangan menebak "minggu terbaru" dari kolom `Inbound Week`; minta periode eksplisit.
3. **Sumber data**: ekspor CSV tab *NEW Customers List* (utama; semua BU dalam satu tabel, difilter menurut kolom `BU`), atau empat CSV stage dari snapshot yang sama.

## Langkah
1. Ambil repo terbaru (`git clone` atau `git pull`). Jika tidak bisa mengakses GitHub, minta pengguna mengunggah isi repo.
2. Taruh CSV di `input/`. **Jangan commit atau push CSV, HTML, audit, maupun analysis.json**; repo bersifat publik.
3. Jalankan: `python generate_report.py --table input/<file>.csv --bu <bu> --period <periode>` (untuk empat CSV: `--input-dir input/<BU>` sebagai pengganti `--table`).
4. Baca `output/*.audit.json`. Tampilkan ringkasan metrik ke pengguna dan minta mereka mencocokkan dengan tracker **sebelum** analisis ditulis. Perhatikan `rows_in_bu`, `rows_without_bu`, dan `duplicate_record_keys` pada audit. Jika header, tanggal, atau Record Key ganda ditolak generator, laporkan pesan error apa adanya; jangan memperbaiki data diam-diam.
5. Setelah angka disetujui, tulis `analysis.json` (kolom mengikuti `analysis.example.json`, BU2: `analysis.bu2.example.json`), isi hanya dari angka di audit dan HTML, lalu jalankan `apply_analysis.py`.
6. Serahkan HTML final. Sebutkan periode, pembanding, dan hash input dari audit.

## Aturan penting
- Definisi ada di `METRIC_RULES.md`: tanggal event, bukan label `Week`. SQL BU1 memakai `Proposal Price Quote Date`; SQL BU2 memakai `SQL Date`.
- Ecosystem hanya ada pada BU2 dan dikenali dari `Campaign Hardware` = `Ecosystem`.
- Rate selalu ditampilkan sebagai persentase, perubahan rate dalam pp. Rupiah memakai titik pemisah ribuan.
- Analisis boleh menyebut perubahan, anomali, dan sumber terkuat atau terlemah, tetapi setiap klaim harus punya angka dari laporan. Jangan menebak penyebab tanpa data.
