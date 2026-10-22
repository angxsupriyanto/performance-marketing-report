# n8n workflows untuk laporan weekly/monthly

Tiga workflow siap impor (n8n 2.x). Semuanya **dihasilkan** oleh `n8n/build_workflows.py` dari file di `n8n/code`, `n8n/sql`, dan `n8n/prompts`; ubah sumbernya lalu jalankan ulang skrip. Test gagal bila JSON dan sumbernya berbeda. JSON sudah disanitasi (tanpa credential, ID spreadsheet, chat ID, token, atau data customer) dan semua workflow diimpor dalam keadaan **tidak aktif**.

| Workflow | Fungsi |
|---|---|
| `Report_Generate_v1` | Membaca tab *NEW Customers List*, mengirim hanya kolom yang dibutuhkan ke layanan laporan, menyimpan hasilnya ke PostgreSQL, lalu mengirim ringkasan agregat ke Telegram. |
| `Report_Analysis_Button_v1` | Membaca run terbaru untuk BU dan periode yang dipilih, mengirim **hanya `facts` agregat** ke model (bawaan: combo `pesankopi-report` di 9router), memvalidasi JSON balasan, menyisipkannya ke laporan, dan menyimpan hasilnya. |
| `Performa_Generate_v1` | Membaca tab *NEW Customers List*, meminta `report-service` menghitung agregat per hari dan cohort, dan menyimpannya sebagai snapshot untuk halaman Performa. Manual saja, tanpa webhook dan tanpa Telegram. Lihat `deploy/VIEWER.md`. |

**Tidak ada penjadwalan.** Semua dijalankan manual, dan periode selalu disebut eksplisit (tidak ada tebakan "minggu lalu"). Dua cara memicu `Generate` dan `Analysis`:

- **Dari editor n8n:** buka workflow, ubah nilai di node **Manual Parameters** (`bu` = `all`, `bu1`, atau `bu2`; `period` = `2026-W39` untuk mingguan atau `2026-09` untuk bulanan; khusus Analysis `bu` wajib `bu1` atau `bu2`), lalu klik *Execute workflow*. Nilai bawaan `<PERIOD>` dan `<BU>` sengaja membuat eksekusi gagal dengan pesan jelas sampai Anda mengisinya.
- **Dari luar (tombol):** `POST /webhook/report-generate` atau `/webhook/report-analysis` dengan header token dan body `{"bu":"bu2","period":"2026-W39"}`. Viewer memanggil `/webhook/report-analysis` dengan body yang sama ditambah `targets` (angka progress terhadap target, tanpa nama perusahaan) yang diteruskan ke model.

Urutan pemakaian: jalankan Generate dulu untuk periode itu, lalu Analysis. Analysis menolak bila belum ada laporan numerik untuk BU dan periode tersebut.

## Database

`marketing_reports` adalah database **sendiri** di server PostgreSQL yang sudah ada. Skripnya tidak menyentuh `inbound_marketing`, `core`, `core_v2`, atau `staging`, dan role-nya (`report_owner`, `report_writer`, `report_reader`) tidak punya akses ke sana. Yang tetap dibagi dengan server yang ada: proses server, penyimpanan dan backup, serta daftar role (role bersifat tingkat server). Memasangnya butuh akun yang boleh membuat database dan role.

Setelah dipasang, tambahkan `marketing_reports` ke rutinitas backup yang sudah ada (mis. `pg_dump -d marketing_reports`). Bila `pg_hba.conf` membatasi akses per database atau per user, izinkan `report_writer` dan `report_reader` dari container n8n ke database ini.

## Memasang

Untuk menyerahkan pemasangan Docker kepada Gordon (asisten AI Docker), gunakan `deploy/GORDON_TASK.md`: berisi instruksi siap tempel, aturan pengaman, dan titik persetujuan. Langkah manualnya di bawah ini.

1. **Database.** Jalankan `psql -d postgres -f database/preflight.sql` (read-only; semua baris harus `OK`), lalu `database/000_create_database_and_roles.sql` dan `database/001_reports_schema.sql` (perintah lengkap ada di komentar tiap berkas; kata sandi diberikan lewat `-v`, bukan disimpan di Git). Hasilnya database `marketing_reports` dengan role `report_writer` (SELECT dan INSERT saja) dan `report_reader` (SELECT). Buat dua credential Postgres di n8n yang menunjuk ke database ini.
2. **Layanan laporan.** Salin `deploy/docker-compose.report-service.example.yml` menjadi `docker-compose.report-service.local.yml` (diabaikan Git), ubah hanya nama network menjadi network yang sudah dipakai n8n, buat token dengan `openssl rand -hex 32 > deploy/report_service_token.txt`, lalu `docker compose -p report-service -f deploy/docker-compose.report-service.local.yml up -d --build`. Dijalankan sebagai proyek terpisah, jadi stack n8n tidak dibuat ulang. Jangan publikasikan portnya; n8n memanggilnya sebagai `http://report-service:8080`. Periksa hasilnya dengan `deploy/verify-report-service.sh --container report-service --n8n-container <nama container n8n>`. Bila nama layanan atau portnya berbeda, ubah `SERVICE_URL` di `build_workflows.py` dan jalankan ulang.
3. **Impor** ketiga JSON, lalu buat dan pilih credential (nama bebas):

   | Node | Tipe credential |
   |---|---|
   | Read Tracker | Google Sheets OAuth2, cukup scope read-only |
   | Generate Report, Apply Analysis | Header Auth: `Authorization` = `Bearer <isi report_service_token.txt>` |
   | Ask Model | Header Auth: `Authorization` = `Bearer <API key 9router>` (untuk `PROVIDER = 'openai'`, bawaan). Untuk `PROVIDER = 'anthropic'`: `x-api-key` = kunci API Anthropic |
   | Save Run, Save Analysis, Load Latest Run, Save Snapshot | Postgres sebagai `report_writer` |
   | Webhook Generate, Webhook Analysis | Header Auth (token pemanggil) |
   | Notify, Notify Error | Telegram |

4. **Isi placeholder** (ada di JSON sebagai teks `<...>`): `<SPREADSHEET_ID>` dan `<TELEGRAM_CHAT_ID>` pada node terkait, `<BU>` dan `<PERIOD>` pada node *Manual Parameters* setiap kali menjalankan manual. Model tidak lagi berupa placeholder: node *Prepare Analysis Request* memakai `PROVIDER = 'openai'` ke `https://9router.pesankopi.com/v1/chat/completions` dengan model (combo) `pesankopi-report`. Untuk memakai alamat internal Docker router, ubah `url` di baris `openai`; untuk kembali ke Claude, ubah `PROVIDER` menjadi `'anthropic'` dan pasang credential `x-api-key`.
5. Pasang *Error Workflow* yang sudah ada (H-17/H-18 Production Error Notification) di Settings tiap workflow.
6. Eksekusi sukses tidak disimpan (`saveDataSuccessExecution: none`) karena data mengalir sebagai baris customer. Nyalakan sementara hanya saat debugging.

## Ringkasan di Telegram

Setiap laporan yang tersimpan mengirim satu pesan (atau lebih bila daftarnya panjang; batas Telegram 4096 karakter, jadi dipecah per baris, tidak pernah terpotong):

```text
Laporan BU1 2026-W42 tersimpan

Submission 58
MQL 37
SQL 15
SQL Value Rp 256.295.000
Deal Won 5
Deal Won Value Rp ...

List SQL + Value (15)
1. <perusahaan> - Rp ...

List Deal Won + Value (5)
1. <perusahaan> - Rp ...

Baris di BU: 5974 · tanpa BU (tidak dihitung): 29 · Run: 6106c0e3
```

Daftar SQL dan Deal Won memuat **nama perusahaan** dan nilainya. Dokumen platform inbound mencatat aturan menjaga data customer di luar pesan Telegram, jadi pastikan chat tujuan hanya berisi orang yang memang boleh melihatnya. Untuk mengirim total saja, ubah `const INCLUDE_COMPANY_NAMES = true;` menjadi `false` di node **Compose Message**. Nama perusahaan hanya dikirim ke Telegram; tidak masuk ke database selain di HTML laporan, dan tidak pernah masuk ke `facts` yang dikirim ke Claude.

## Memperbaiki satu node tanpa impor ulang

Impor ulang membuat workflow baru dan membuat Anda memilih ulang credential dan mengisi placeholder lagi. Untuk perbaikan kode, cukup ganti isi satu Code node: buka node, hapus isinya, lalu tempel isi berkas yang sesuai di `n8n/workflows/code/` (mis. `Report_Generate_v1__Build_CSV.js`). Berkas itu sudah terender (daftar kolom dan prompt sudah terisi), dibuat oleh `build_workflows.py`, dan diuji agar selalu sama dengan isi JSON. Bila Anda mengubah `PROVIDER`, URL, atau model di node `Prepare Analysis Request`, ulangi perubahan itu setelah menempel.

Sheets API tidak mengirim sel kosong, jadi `Build CSV` menganggap suatu kolom hilang hanya bila **tidak ada satu baris pun** yang memilikinya. Kolom yang kosong di seluruh sheet tidak bisa dibedakan dari kolom yang tidak ada, dan akan dilaporkan sebagai hilang.

## Hal yang belum diverifikasi terhadap n8n sungguhan

Semua Code node, SQL, layanan, dan alurnya diuji di luar n8n (harness Node, PostgreSQL 16, server HTTP). Yang **belum** bisa dibuktikan tanpa instance n8n Anda:

- Nama parameter dan versi node (Google Sheets, Postgres, HTTP Request, Telegram, Respond to Webhook) pada n8n versi Anda. Setelah impor, buka tiap node sekali; bila ada parameter yang ditandai, betulkan lewat UI dan ekspor ulang.
- Node Postgres menerima `queryReplacement` berupa ekspresi array (`={{ $json.params }}`). Bila versi Anda mensyaratkan string, query tidak akan terikat; periksa dengan satu eksekusi manual dan lihat baris di `reports.report_runs`.
- Node Google Sheets pada ±8.800 baris × 122 kolom: waktu dan memori. Kode mengantisipasi tanggal serial dan angka tak terformat, tetapi bukan bentuk keluaran node yang sebenarnya.
- Panggilan ke API Anthropic (tidak ada kunci di lingkungan pengembangan) dan kualitas teks analisisnya.
- Image Docker belum dibangun di lingkungan ini (tidak ada daemon Docker). Entry point Python diuji langsung; `docker build` pertama sebaiknya Anda jalankan sebagai langkah uji.

## Urutan uji yang disarankan

1. Jalankan `Report_Generate_v1` secara manual untuk satu periode yang angkanya sudah Anda kenal (isi *Manual Parameters*). Cek `reports.run_index` dan pesan Telegram.
2. Bandingkan angka run dengan Metabase atau dashboard BU1 lama untuk periode yang sama. Untuk BU1 mingguan harus identik dengan generator CLI.
3. Jalankan ulang tanpa mengubah Tracker: pesan harus berbunyi "sudah ada (input identik)" dan tidak menambah baris.
4. Panggil webhook analisis (atau tekan *Buat analisis* di viewer), lalu buka report di viewer dan periksa teksnya terhadap angka.
