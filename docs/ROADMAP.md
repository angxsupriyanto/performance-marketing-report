# Roadmap

Status: **usulan**, kecuali yang ditandai *diputuskan*. Isi ini adalah hasil diskusi dengan pemilik produk pada 2026-10-27. Tujuannya agar sesi berikutnya langsung bekerja tanpa mengulang pembahasan. Baca juga `DECISIONS.md` dan `KNOWN_GAPS.md`.

## Titik awal: MVP terkunci (diputuskan)

MVP = yang sudah dibangun dan terdokumentasi: report mingguan dan bulanan per perusahaan, Performa, Budget bulanan, Target, Action dan analisis AI dengan Next Action, PDF, pengguna dan peran, dan dark mode. Fase di bawah **belum** dibangun.

## Arah jangka panjang (visi pemilik)

Menjadikan produk ini **dashboard digital marketing penuh**: dari perencanaan budget (tahun, semester, bulan) sampai proyeksi hasil terhadap KPI.

Pendapat yang disampaikan kepada pemilik, dan perlu diingat oleh sesi berikutnya:

1. **Proyeksi mudah menyesatkan.** Dengan histori pendek per produk, biaya per SQL dan nilai SQL sangat bergejolak, dan menambah budget jarang menambah hasil secara linear. Tampilkan **rentang** (rendah, dasar, tinggi) dan dasar hitungnya, jangan satu angka yang tampak pasti.
2. **KPI BU1 dan BU2 berbeda** (SQL Value versus jumlah SQL Ecosystem). Rumus proyeksinya berbeda. Deal Won punya jeda waktu dan tidak layak diproyeksikan sederhana.
3. **Fondasi dulu.** Perencanaan dan proyeksi bergantung pada pemetaan spend ke hasil. Kesalahan di dasar tidak terlihat di angka akhir.
4. **Perencanaan butuh keputusan bisnis yang belum dibuat:** alokasi per platform, produk, atau campaign; aturan realokasi saat satu produk tidak efisien.
5. **Keamanan:** setiap halaman admin baru yang menulis data anggaran perlu dicek hak akses, CSRF, dan input.

Pertanyaan yang diajukan kepada pemilik dan **belum dijawab**: keputusan apa yang paling ingin dibantu (membagi budget tahunan, membagi ke platform dan produk, tahu apakah target tercapai, atau menghitung budget yang dibutuhkan), seberapa panjang histori yang bisa dipakai (6 bulan atau lebih membuat proyeksi dasar masuk akal), dan siapa pembaca utamanya (tim harian, manajemen, atau keduanya).

## Urutan yang disarankan

| Fase | Isi | Status |
|---|---|---|
| 1 | **Pemetaan iklan** dan Budget berbasis campaign iklan (di bawah) | Mockup disetujui pemilik; belum dibangun |
| 2 | Rapikan **menu dan penamaan** di semua halaman | Diminta pemilik; belum dibangun; lihat "Penamaan" |
| 3 | **Rencana budget** tahun, semester, dan bulan, bersama target | Usulan |
| 4 | **Proyeksi** sederhana dan transparan, dengan rentang | Usulan; bergantung jawaban pertanyaan di atas |
| 5 | **Tampilan KPI**: capaian, proyeksi, sisa yang harus dikejar | Usulan |
| 6 | Unggah CSV ekspor Meta dan Google | Ditunda; pemilik akan mengunggah contoh bila dibutuhkan |

Kerjakan bertahap dan uji tiap tahap dengan angka nyata sebelum lanjut. Untuk fase yang menyentuh rumus uang (ROAS, biaya per SQL, proyeksi), minta review independen (`/code-review`, dan `/security-review` untuk halaman admin baru) dan cocokkan satu produk dengan hitungan manual dari Sheet.

## Fase 1: Pemetaan iklan (mockup disetujui)

Mockup: lihat `docs/mockups/` (papan 12 dan 13 di artifact desain). Nama campaign di mockup sengaja netral.

### Masalah yang diselesaikan

Pemilik mencatat spend di spreadsheet Excel lama yang rumit: spend per campaign **iklan** (nama di Meta atau Google) per minggu dan bulan, dua tab dengan data sama, pengelompokan produk manual, ROAS per produk, dan rencana penyesuaian budget. Halaman Budget sekarang memakai nama campaign **Tracker**, bukan nama campaign iklan, sehingga spend tidak bisa disambungkan ke hasil lead dan ROAS per produk belum ada.

### Temuan kunci

- Di spreadsheet lama, ROAS dihitung **per produk** (SQL Value produk ÷ spend produk). Karena itu **ROAS per produk tidak butuh pemetaan nama campaign**: cukup tiap baris Budget punya penanda produk dan platform; SQL Value per produk sudah ada dari Campaign Hardware di Tracker.
- Pemetaan nama baru diperlukan untuk tampilan **per campaign iklan** (biaya per SQL dan ROAS per campaign iklan). Satu campaign iklan biasanya mencakup banyak campaign Tracker (satu-ke-banyak). Jangan menebak pemetaannya.

### Keputusan (diputuskan, 2026-10-27)

| Hal | Keputusan |
|---|---|
| Penamaan | Tab Budget: **Iklan berbayar** dan **Non-iklan**. Menu dan halaman: **Pemetaan iklan**. Kolom: **Hasil lead dari**. Grup tetap berlabel "Grup". |
| Produk | Daftar disimpan di database dan diedit admin (bukan di kode). Daftar awal: Dashcam, GPS, Fuel, MDVR, OBD, Traffic, Sparepart, TMS, Enterprise. Bisa ditambah dan dinonaktifkan (data lama tetap). |
| Platform | Pilihan: Meta, Google, TikTok, LinkedIn, YouTube, Lainnya. Bisa ditambah admin seperti produk. |
| Campaign iklan masuk | Admin **menempel** banyak nama sekaligus (satu per baris); nama yang sudah ada dilewati. Budget memilih dari daftar ini. |
| Pemetaan | **Aturan filter** (Channel, Source, Medium, Campaign Hardware) sebagai dasar, ditambah **tambahan manual** dan **pengecualian manual**. Hasil dan contoh campaign tampil langsung. Dapat diedit. |
| Eksklusivitas | **Satu campaign Tracker hanya boleh masuk satu campaign iklan.** Pemetaan yang bentrok ditolak (tombol Simpan nonaktif dengan penjelasan), bukan dibagi rata. |
| Budget | Dua tab picker: Iklan berbayar (memilih campaign iklan, dengan platform dan produk) dan Non-iklan (campaign Tracker dan grup seperti Email Nurturing). Baris lama atas nama Tracker tetap terbaca. Kolom Platform dan Produk di tabel dibaca dari Pemetaan, tidak diisi di Budget. |
| Report | Tiga tabel baru di bagian Budget dan spend: **spend per platform**, **spend dan hasil per produk** (SQL, SQL Value, biaya per SQL, ROAS), dan **per campaign iklan**. Campaign yang belum dipetakan tetap menghitung spend di total tetapi hasilnya tampil sebagai tanda hubung. |
| Sumber spend | Tetap diinput manual di viewer pada fase ini. Unggah CSV adalah fase 6. |

### Asumsi yang belum dikonfirmasi pemilik

- Nilai **Campaign Hardware** di Tracker bisa dipakai sebagai daftar produk. Bila berbeda, perlu tabel pengganti.
- Pemetaan berlaku mulai dari waktu disimpan dan **tidak mengubah report yang sudah dibuat**.
- Warna ROAS di tabel produk membandingkan dengan bulan lalu (hijau naik, merah turun, abu-abu tetap). Spend tetap netral.
- Satu webinar atau konten yang diiklankan di platform dicatat sebagai campaign iklan; "Non-iklan" berarti tidak punya campaign iklan di platform yang dipetakan, bukan "tanpa biaya".

### Sketsa data (usulan, bukan skema final)

Tabel baru, semuanya append-only atau dinonaktifkan (jangan DELETE): produk, platform, campaign iklan (nama, platform, produk, aktif), dan versi pemetaan per campaign iklan (aturan filter dalam jsonb, daftar tambahan, daftar pengecualian). Baris `budget_snapshots.data.campaigns` perlu membawa jenis (`iklan` atau `tracker`) dan rujukan ke campaign iklan. Pertahankan kompatibilitas dengan baris lama. Tambahkan migrasi `010+`, role `report_viewer` dengan hak minimum, tes di `tests/test_database.py`, dan perbarui `docs/DATA_MODEL.md`.

### Tahap implementasi yang disarankan

1. Database dan halaman Pemetaan iklan (diuji sendiri).
2. Budget: picker dua tab dan kolom Platform dan Produk.
3. Report: tiga tabel baru; cocokkan satu produk dengan hitungan manual dari Sheet sebelum dipakai.

## Fase 2: Penamaan dan menu (diusulkan)

Pengelompokan menu menurut siklus kerja, supaya setiap halaman menjawab satu pertanyaan:

| Grup | Halaman | Menjawab |
|---|---|---|
| Laporan | Daftar report, Performa | Apa yang terjadi? |
| Perencanaan | Target, Rencana budget (fase 3) | Berapa yang direncanakan dan targetnya? |
| Data iklan | Budget dan spend, Pemetaan iklan | Berapa yang dibelanjakan dan untuk apa? |
| Pengaturan | Pengguna, Nama perusahaan | Siapa yang punya akses? |

Istilah yang dipakai konsisten di semua halaman: campaign iklan, non-iklan, produk, platform. Perubahan ini adalah teks dan tata letak; buat mockup dulu (D5).

## Hal yang sebaiknya **tidak** dilakukan

- Jangan menampilkan proyeksi sebagai satu angka pasti.
- Jangan membagi spend secara otomatis ke campaign Tracker bila pemetaannya bentrok.
- Jangan menyalin nama campaign iklan atau angka dari spreadsheet pemilik ke repo (repo publik).
- Jangan menambah penjadwalan otomatis (D2) tanpa persetujuan.
- Jangan mengubah aturan umur SQL (D11) atau KPI (D10) tanpa persetujuan.
