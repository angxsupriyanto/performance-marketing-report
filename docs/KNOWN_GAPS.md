# Celah yang diketahui

Daftar hal yang **belum terbukti, belum selesai, atau diketahui rapuh** pada MVP. Dihapus dari sini hanya setelah dibuktikan. Tanggal terakhir ditinjau: 2026-10-27.

## Belum diverifikasi di lingkungan nyata

| # | Hal | Keterangan |
|---|---|---|
| G1 | **PDF di container viewer sebenarnya** | Dibuat dan diuji dengan Chromium lokal dan tes. Belum terkonfirmasi di container Docker pemilik (filesystem hanya-baca, `cap_drop` semua). Diagnostik: `docker exec report-viewer chromium --version`, `docker logs --tail 30 report-viewer`. |
| G2 | **Keluaran model setelah prompt v2** | Belum dikonfirmasi bahwa teks nyata mengikuti semua aturan (juta dan miliar, tanpa `same_period`, tanpa catatan kualitas data, porsi Same-week, Next Action terisi). Pemilik perlu menjalankan *Buat ulang analisis* dan menilai. |
| G3 | **Aturan umur SQL BU1 terhadap data asli** | Diuji dengan data contoh. Hasil W43 setelah perubahan ke 6 bulan belum dilihat; periksa `sql_expired` di audit run dan progress Target SQL Value. |
| G4 | **Dark mode pada data nyata** | Diperiksa dengan data contoh di Daftar report, Report, Performa, dan Budget. Sel heatmap cohort berwarna belum terlihat dengan data berisi; halaman Target, Pengguna, dan Nama perusahaan hanya diuji lewat tes markup. |
| G5 | **Nama grup Nurturing** | Nama grup mengikuti nilai Medium di Tracker. Variasi huruf besar-kecil ("Whatsapp" dan "WhatsApp") menjadi dua grup. Pemilik belum memutuskan menyatukan otomatis. |
| G6 | **n8n versi nyata** | Workflow sudah dijalankan pemilik dan berfungsi, tetapi versi node dan parameternya belum diaudit satu per satu (lihat bagian terkait di `n8n/README.md`). |

## Batasan yang disengaja atau diterima

| # | Hal | Keterangan |
|---|---|---|
| G10 | Cloudflare Access belum terpasang | *Redirect loop* sengaja dilewati (D34). Perlindungan hanya login viewer. Rekomendasi tetap: pasang Access bila ada waktu. |
| G11 | Tidak ada log siapa melakukan apa, dan pengguna tidak bisa mengganti password sendiri | Admin yang mengatur password. |
| G12 | Format tanggal Tracker harus `M/D/YYYY` atau `YYYY-MM-DD` | Sheet berformat D/M/YYYY akan terbaca salah tanpa galat. |
| G13 | Aturan umur SQL hanya untuk BU1 | BU2 tidak punya aturan serupa (belum diminta). |
| G14 | Budget hanya per bulan | Belum ada rencana tahun atau semester; tidak ada hubungan budget ke target. Lihat `ROADMAP.md`. |
| G15 | Budget memakai nama campaign Tracker, bukan nama campaign iklan di Meta atau Google | Belum ada pemetaan, sehingga ROAS per produk dan biaya per SQL belum tersedia. Lihat `ROADMAP.md`. |
| G16 | Repo ini **publik** | Jangan commit data lead, report terisi, atau nama campaign internal. Mockup fase berikutnya memakai contoh netral. |
| G17 | Mockup berada di artifact desain pribadi, bukan di repo | Tautan hanya terbuka bagi pemilik. Ringkasan dan tangkapan layar netral ada di `docs/mockups/`. |

## Utang teknis

- `viewer/app.py` dan `viewer/pages.py` besar; perubahan tampilan sering menyentuh keduanya. Pertimbangkan memecah bila fitur bertambah.
- Skrip uji browser (Playwright) tidak ikut repo; tes otomatis berbasis markup dan `FakeStore`. Uji visual dilakukan manual.
- Tes memakai tanggal tetap, tetapi beberapa data uji bergantung pada aturan umur SQL (batas 6 bulan): bila data uji dengan SQL jauh setelah inbound ditambahkan, ia akan terbuang.
- Dark mode mengganti hex lewat `viewer/theme.py`; warna baru yang ditulis langsung di kode halaman tidak ikut gelap kecuali didaftarkan.
