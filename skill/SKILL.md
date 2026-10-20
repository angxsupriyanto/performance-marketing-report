---
name: performance-marketing-report
description: Buat laporan performa marketing mingguan atau bulanan (BU1, BU2 bila profilnya sudah ada) dari empat CSV Campaign Tracker memakai generator deterministik di repo performance-marketing-report. Gunakan saat pengguna menyebut laporan marketing, performance report, WoW, MoM, Inbound, MQL, SQL, Deal Won, atau mengunggah CSV campaign.
---

# Performance Marketing Report

Angka dihitung oleh `generate_report.py` di repo `angxsupriyanto/performance-marketing-report`. **Jangan menghitung angka sendiri** (tanpa pandas, tanpa rumus ad hoc di chat). Tugas Anda: menjalankan generator, memverifikasi, lalu menulis analisis.

## Sebelum mulai, tanyakan bila belum jelas
1. **BU**: BU1 atau BU2. Jika `profiles/<bu>.json` tidak ada di repo, berhenti dan katakan profil belum tersedia. Jangan memakai profil BU lain.
2. **Periode**: mingguan `YYYY-Www` atau bulanan `YYYY-MM`. Jangan menebak "minggu terbaru" dari kolom `Inbound Week`; minta periode eksplisit.
3. **Empat CSV dari snapshot yang sama**: Raw Submission, Raw MQL, Raw SQL, Raw Deal Won, hanya untuk BU yang dipilih.

## Langkah
1. Ambil repo terbaru (`git clone` atau `git pull`). Jika tidak bisa mengakses GitHub, minta pengguna mengunggah isi repo.
2. Taruh empat CSV di `input/<BU>/`. **Jangan commit atau push CSV, HTML, audit, maupun analysis.json**; repo bersifat publik.
3. Jalankan: `python generate_report.py --bu <bu> --input-dir input/<BU> --period <periode>`
4. Baca `output/*.audit.json`. Tampilkan ringkasan metrik ke pengguna dan minta mereka mencocokkan dengan tracker **sebelum** analisis ditulis. Jika header atau tanggal ditolak generator, laporkan pesan error apa adanya; jangan memperbaiki data diam-diam.
5. Setelah angka disetujui, tulis `analysis.json` (kolom mengikuti `analysis.example.json`), isi hanya dari angka di audit dan HTML, lalu jalankan `apply_analysis.py`.
6. Serahkan HTML final. Sebutkan periode, pembanding, dan hash input dari audit.

## Aturan penting
- Definisi ada di `METRIC_RULES.md` (tanggal event, bukan label `Week`; MQL, SQL, dan Deal Won dihitung dari file stage masing-masing, bukan dari satu CSV gabungan).
- Rate selalu ditampilkan sebagai persentase, perubahan rate dalam pp. Rupiah memakai titik pemisah ribuan.
- Analisis boleh menyebut perubahan, anomali, dan sumber terkuat atau terlemah, tetapi setiap klaim harus punya angka dari laporan. Jangan menebak penyebab tanpa data.
