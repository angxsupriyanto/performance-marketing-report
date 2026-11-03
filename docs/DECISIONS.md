# Keputusan

Daftar keputusan yang diambil **pemilik produk** (pengguna) dan alasannya. Jangan dibatalkan diam-diam: bila ingin mengubah, tanyakan dulu, lalu perbarui entri ini (tanggal, apa yang berubah, siapa yang memutuskan). Tanggal memakai format tahun-bulan-hari.

## Prinsip produk

| # | Keputusan | Alasan | Sumber |
|---|---|---|---|
| D1 | Angka hanya dihitung generator Python. AI menulis narasi dari angka agregat dan tidak melihat nama perusahaan lead. | Angka harus bisa diaudit dan konsisten. | Awal proyek |
| D2 | **Tanpa penjadwalan.** Semua workflow dipicu manual dengan periode eksplisit. | Pemilik ingin kontrol atas kapan data diambil. Tidak ada tebakan "minggu lalu". | Awal proyek |
| D3 | **Deal Won tetap dari Google Sheet Campaign Tracker.** | Sumber kebenaran Deal Won ada di sana. | Pemilik |
| D4 | Database **terpisah** (`marketing_reports`), role terpisah, tabel append-only. | Tidak mengganggu database lain; riwayat tidak hilang. | Awal proyek |
| D5 | Perubahan tampilan: **mockup dulu**, implementasi setelah disetujui. | Menghindari tampilan yang tidak sesuai. | Pemilik, berulang |
| D6 | "BU1" dan "BU2" hanya id internal. Yang tampil adalah nama yang diatur admin; antarmuka memakai istilah "Perusahaan". | Nama perusahaan tidak ditulis di kode. | Pemilik |

## Aturan angka dan KPI

| # | Keputusan | Alasan | Sumber |
|---|---|---|---|
| D10 | **KPI utama BU1 = SQL Value, bukan Deal Won.** **KPI utama BU2 = volume SQL dari Ecosystem.** Keduanya ada di instruksi analisis sebagai pengetahuan internal, tidak ditulis ke hasil analisis atau report. | Cara pemilik menilai kinerja. | Pemilik, 2026-10 |
| D11 | **Aturan umur SQL BU1 (diperluas oleh D38):** SQL hanya dihitung bila tanggal SQL paling lambat **6 bulan kalender** setelah Inbound Date (inklusif; bulan tujuan yang lebih pendek memakai tanggal terakhir bulan itu; tanpa Inbound Date tetap dihitung). SQL yang lewat dikeluarkan dari **semua** angka SQL dan SQL Value, termasuk Same-week, tabel, Top Contributor, Performa, dan progress Target. Submission, MQL, Deal Won, dan BU2 tidak terpengaruh. | SQL yang terlalu lama setelah submission tidak dianggap hasil dari lead itu. Awalnya 1 tahun, diubah menjadi 6 bulan setelah pemilik melihat satu baris minggu 43 yang seharusnya tidak masuk. | Pemilik, 2026-10-26 dan 2026-10-27 |
| D12 | Bulan sebuah minggu = bulan yang memuat hari Kamis minggu itu (aturan ISO), juga untuk semester dan tahun. | Konsisten dengan penomoran minggu ISO. | Awal proyek |
| D13 | Analisis menyebut Rupiah dengan **juta dan miliar**, tidak memakai nama kolom teknis (`same_period`), tidak menambahkan catatan kualitas data atau cohort, dan memuat porsi SQL Value Same-week terhadap total di Executive Summary. | Lebih mudah dibaca; teks tidak boleh bocor istilah kode. | Pemilik, 2026-10 |

## Budget, target, dan Action

| # | Keputusan | Alasan | Sumber |
|---|---|---|---|
| D20 | Target **tidak disimpan di report**; viewer menggabungkannya saat dibuka. | Target bisa berubah tanpa membuat report baru. | Awal proyek |
| D21 | **Spend mingguan dan bulanan diisi terpisah, tidak dijumlahkan.** Minggu diisi di bulan yang memuat Kamisnya. | Minggu ISO bisa melewati pergantian bulan, jadi bulan bukan 4 atau 5 minggu penuh. | Pemilik |
| D22 | Daftar campaign di Budget dimulai kosong; admin memilih dari daftar Tracker (dan snapshot Performa terbaru) dengan filter berjenjang dan kolom cari. Nama tidak bisa diketik bebas. | Daftar penuh terlalu berat; nama harus persis sama dengan Tracker. | Pemilik |
| D23 | **Nurturing:** campaign yang hanya muncul di Source yang mengandung "Nurturing" tetap tampil dengan nama aslinya dan keterangan "Grup: <Medium> Nurturing". Memilihnya menambahkan **baris grup** (mis. Email Nurturing), satu baris per grup. Baris lama tidak diubah. | Campaign Nurturing terlalu banyak untuk dicatat satu per satu. | Pemilik, 2026-10 |
| D24 | Action periode: form muncul saat menekan *Buat analisis*, daftar tersimpan per report (append-only) dan ikut sebagai pertimbangan analisis bersama budget dan spend. Pilihan Campaign di form hanya baris yang dipilih di Budget bulan report. **Next Action** adalah rekomendasi AI yang bisa diedit admin. | Pemilik ingin tindakan nyata masuk ke analisis. | Pemilik, 2026-10 |

## Tampilan dan operasi

| # | Keputusan | Alasan | Sumber |
|---|---|---|---|
| D30 | Kartu report menampilkan chip warna naik (hijau), turun (merah), tetap (abu-abu) dengan selisih angka dan persen. Spend dan Budget netral. Tanpa keterangan rumus. | Lebih mudah dipahami. | Pemilik |
| D31 | Menu dikelompokkan menurut fungsi dengan pemisah tipis: (Daftar report, Performa), (Budget, Pengaturan target), (Pengguna, Nama perusahaan). Tanpa garis bawah kecuali menu aktif. | Lebih rapi. | Pemilik |
| D32 | PDF dibuat **di server** dengan Chromium tanpa tampilan, hanya halaman report, dan **selalu terang**. | Hasil identik untuk semua pengguna; PDF untuk dicetak dan dibagikan. | Pemilik |
| D33 | **Dark mode:** Terang, Gelap, Otomatis (ikut perangkat); pilihan disimpan di browser. Latar `#191919`, permukaan `#1F1F1F`, warna lain abu netral dengan kontras diperiksa. | Pilihan pengguna. | Pemilik, 2026-10-27 |
| D34 | Aplikasi dibuka lewat **Cloudflare Tunnel** di `officehours.pesankopi.com`. Masalah *redirect loop* Cloudflare Access **sengaja dilewati**; viewer memakai login sendiri. | Pemilik memilih tidak melanjutkan. | Pemilik, 2026-10 |
| D35 | Instance live memakai proyek compose `report-viewer` dan file compose dasar. **Jangan memakai berkas override `localaccess`** untuk instance live. | Override itu hanya untuk uji lokal dan membuka port. | Pemilik |
| D36 | Pengguna bekerja di Windows PowerShell dan menjalankan Docker sendiri. Perintah harus bisa ditempel apa adanya. | Lingkungan kerja pemilik. | Pemilik |
| D37 | Model tidak diminta membaca isi berkas rahasia (`viewer_*`, token tunnel); asisten Docker (Gordon) juga tidak. | Kebersihan rahasia. | Pemilik |
| D38 | **Masa berlaku lead untuk MQL, SQL, dan Deal Won**, diatur per perusahaan di halaman admin *Masa berlaku lead*, acuan selalu Inbound Date (bukan Submission Date). Tiap tahap punya batas umum dan boleh punya aturan khusus per Remark (Remark dipilih dari nilai di Sheet). Tahap yang expired keluar dari angka tahap itu saja. Tanpa pengaturan tersimpan dipakai batas profil (BU1 SQL 6 bulan, seperti D11). **Ini mengubah keputusan lama bahwa Deal Won tidak terpengaruh aturan umur**: sekarang bisa, dengan batas bawaan "tanpa batas" agar angka lama tidak berubah. | Masa efektif lead berbeda per perusahaan dan per jenis lead (mis. Trial 1 tahun). | Pemilik, 2026-11 |
| D39 | **Pencapaian manual:** admin bisa menimpa angka pencapaian di report (SQL Value per produk bulan itu, serta progress semester dan 1 tahun; untuk BU2 hanya semester dan tahun dalam jumlah SQL) bila Sheet belum lengkap. Disimpan per report (BU + periode), append-only, alasan wajib bila ada angka manual. **Angka manual tampil tanpa penanda** di report dan PDF, dan dipakai analisis; angka sistem dan alasan hanya terlihat di form admin. Edit semester atau tahun menggantikan angka sistem langsung, tidak diturunkan dari koreksi per produk. | Sheet kadang terlambat diperbarui. Pemilik memilih tanpa penanda; risikonya pembaca tidak bisa membedakan data asli dan koreksi (dicatat di `KNOWN_GAPS.md`). | Pemilik, 2026-11 |
| D40 | **Informasi tambahan analisis:** satu kotak teks bebas (maksimal 1000 karakter) di form *Buat analisis*, dikirim ke model sebagai `team_note` (data, bukan instruksi), disimpan per permintaan di `analysis_notes` (append-only), **tidak tampil di report**. | Konteks yang tidak ada di angka (promo, libur, gangguan tracking). | Pemilik, 2026-11 |
| D41 | **Perbarui data dari aplikasi:** halaman admin *Perbarui data* menjalankan Report Generate (perusahaan, mingguan atau bulanan, periode) dan Update data Performa lewat webhook n8n; pilihan perusahaan termasuk **Semua**. Hanya admin; satu proses per jenis dalam satu waktu (dikunci dari database, bukan hanya tombol). Tiap proses dan hasil per perusahaan dicatat (`process_requests` oleh viewer, `process_results` oleh n8n); tanpa laporan dari n8n dalam **5 menit** proses ditandai tidak dijawab dan tombol terbuka lagi. Tidak ada jadwal otomatis (D2 tetap berlaku). | Pemilik ingin menjalankan generate dari aplikasi tanpa membuka n8n. | Pemilik, 2026-11 |

## Keputusan untuk fase berikutnya (belum diimplementasikan)

Lihat `ROADMAP.md` untuk rinciannya. Ringkasnya, pemilik telah memutuskan (2026-10-27): MVP report **dikunci dulu**; pemetaan iklan dan perencanaan budget dikerjakan di sesi lain; istilah **Iklan berbayar / Non-iklan** dan **Pemetaan iklan**; produk dan platform bisa ditambah admin; satu campaign Tracker hanya masuk satu campaign iklan; pemetaan memakai aturan filter ditambah pengecualian manual; unggah CSV dari platform ditunda sampai dibutuhkan.
