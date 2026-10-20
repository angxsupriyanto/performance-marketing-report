# n8n workflows untuk laporan weekly/monthly

Tiga workflow siap impor (n8n 2.x). Semuanya **dihasilkan** oleh `n8n/build_workflows.py` dari file di `n8n/code`, `n8n/sql`, dan `n8n/prompts`; ubah sumbernya lalu jalankan ulang skrip. Test gagal bila JSON dan sumbernya berbeda. JSON sudah disanitasi (tanpa credential, ID spreadsheet, chat ID, token, atau data customer) dan semua workflow diimpor dalam keadaan **tidak aktif**.

| Workflow | Fungsi |
|---|---|
| `Report_Generate_v1` | Senin 14:00 WIB laporan minggu lalu, tanggal 1 pukul 14:00 WIB laporan bulan lalu, atau POST `/webhook/report-generate` dengan periode eksplisit. Membaca tab *NEW Customers List*, mengirim hanya kolom yang dibutuhkan ke layanan laporan, menyimpan hasil ke PostgreSQL, lalu mengirim ringkasan agregat ke Telegram. |
| `Report_Analysis_Button_v1` | POST `/webhook/report-analysis` dengan `{"bu":"bu2","period":"2026-W39"}`. Membaca run terbaru, mengirim **hanya `facts` agregat** ke Claude, memvalidasi JSON balasan, menyisipkannya ke laporan, dan menyimpan hasilnya. |
| `Report_View_v1` | GET `/webhook/report?bu=bu2&period=2026-W39` menampilkan laporan terbaru (dengan analisis bila ada). Dilindungi Basic Auth karena HTML memuat nama perusahaan. |

Jadwal 14:00 WIB dipilih agar jatuh setelah rangkaian H-17 → H-18 → H-26 (konfigurasi terbaru di `CURRENT_STATE.md` platform: Senin 12:00 WIB) dan H-20 (13:00 WIB) pada hari yang sama, sehingga snapshot dan Tracker sudah memuat pembaruan terbaru. Dokumen platform masih memuat dua versi jadwal H-17 (Senin saja, dan Senin–Jumat 4×/hari); sesuaikan node *Schedule* dengan jadwal produksi yang berlaku.

## Memasang

1. **Database.** Jalankan `database/000_create_database_and_roles.sql` lalu `database/001_reports_schema.sql` (perintahnya ada di komentar tiap berkas; kata sandi diberikan lewat `-v`, bukan disimpan di Git). Ini membuat database `marketing_reports` dengan role `report_writer` (SELECT dan INSERT saja) dan `report_reader` (SELECT).
2. **Layanan laporan.** Gabungkan `deploy/docker-compose.report-service.example.yml` ke proyek Compose yang menjalankan n8n, buat token dengan `openssl rand -hex 32 > report_service_token.txt`, lalu `docker compose up -d --build report-service`. Jangan publikasikan portnya; n8n memanggilnya sebagai `http://report-service:8080`. Bila nama layanan atau portnya berbeda, ubah `SERVICE_URL` di `build_workflows.py` dan jalankan ulang.
3. **Impor** ketiga JSON, lalu buat dan pilih credential (nama bebas):

   | Node | Tipe credential |
   |---|---|
   | Read Tracker | Google Sheets OAuth2, cukup scope read-only |
   | Generate Report, Apply Analysis | Header Auth: `Authorization` = `Bearer <isi report_service_token.txt>` |
   | Ask Claude | Header Auth: `x-api-key` = kunci API Anthropic |
   | Save Run, Save Analysis, Load Latest Run | Postgres sebagai `report_writer` |
   | Load Report | Postgres sebagai `report_reader` |
   | Webhook Generate, Webhook Analysis | Header Auth (token pemanggil) |
   | Webhook View | Basic Auth |
   | Notify, Notify Error | Telegram |

4. **Isi placeholder** (ada di JSON sebagai teks `<...>`): `<SPREADSHEET_ID>` dan `<TELEGRAM_CHAT_ID>` pada node terkait, dan `<ANTHROPIC_MODEL>` di dalam kode node *Prepare Analysis Request* (isi dengan ID model dari dokumentasi Anthropic; node sengaja error sampai diisi).
5. Pasang *Error Workflow* yang sudah ada (H-17/H-18 Production Error Notification) di Settings tiap workflow.
6. Eksekusi sukses tidak disimpan (`saveDataSuccessExecution: none`) karena data mengalir sebagai baris customer. Nyalakan sementara hanya saat debugging.

## Hal yang belum diverifikasi terhadap n8n sungguhan

Semua Code node, SQL, layanan, dan alurnya diuji di luar n8n (harness Node, PostgreSQL 16, server HTTP). Yang **belum** bisa dibuktikan tanpa instance n8n Anda:

- Nama parameter dan versi node (Google Sheets, Postgres, HTTP Request, Telegram, Respond to Webhook) pada n8n versi Anda. Setelah impor, buka tiap node sekali; bila ada parameter yang ditandai, betulkan lewat UI dan ekspor ulang.
- Node Postgres menerima `queryReplacement` berupa ekspresi array (`={{ $json.params }}`). Bila versi Anda mensyaratkan string, query tidak akan terikat; periksa dengan satu eksekusi manual dan lihat baris di `reports.report_runs`.
- Node Google Sheets pada ±8.800 baris × 122 kolom: waktu dan memori. Kode mengantisipasi tanggal serial dan angka tak terformat, tetapi bukan bentuk keluaran node yang sebenarnya.
- Panggilan ke API Anthropic (tidak ada kunci di lingkungan pengembangan) dan kualitas teks analisisnya.
- Image Docker belum dibangun di lingkungan ini (tidak ada daemon Docker). Entry point Python diuji langsung; `docker build` pertama sebaiknya Anda jalankan sebagai langkah uji.

## Urutan uji yang disarankan

1. Jalankan `Report_Generate_v1` secara manual (Manual Trigger). Cek `reports.run_index` dan pesan Telegram.
2. Bandingkan angka run dengan Metabase atau dashboard BU1 lama untuk periode yang sama. Untuk BU1 mingguan harus identik dengan generator CLI.
3. Jalankan ulang tanpa mengubah Tracker: pesan harus berbunyi "sudah ada (input identik)" dan tidak menambah baris.
4. Panggil webhook analisis, lalu buka `Report_View_v1` dan periksa teksnya terhadap angka.
