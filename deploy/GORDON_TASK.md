# Tugas untuk Gordon: memasang layanan laporan di Docker

Tempel isi bagian **Instruksi** di bawah ini ke Gordon, dari folder hasil clone repo ini (branch yang berisi folder `deploy/`). Bagian lain hanya penjelasan untuk Anda.

## Yang dikerjakan Gordon dan yang tidak

| Gordon | Anda |
|---|---|
| Menemukan nama container n8n, network, dan container PostgreSQL (hanya membaca) | Menyetujui hasil temuan itu |
| Membangun dan menjalankan container `report-service` | Mengimpor tiga workflow ke n8n |
| Menjalankan `install-reports-db.sh` (pemeriksaan dulu, instal hanya setelah Anda setuju) | Membuat credential n8n dan mengisi placeholder |
| Menjalankan `verify-report-service.sh` dan melaporkan hasilnya | Menjalankan uji manual pertama dan membandingkan angkanya |

Gordon sebaiknya tidak membaca isi berkas password atau token. Berkas itu dibuat oleh skrip dan hanya Anda yang menyalinnya ke credential n8n.

## Instruksi

```text
Tugas: pasang layanan laporan (report-service) di Docker saya, di samping n8n yang sudah berjalan, lalu
verifikasi. Kerjakan bertahap sesuai fase di bawah dan HENTIKAN diri di setiap titik "TANYA SAYA".

ATURAN KERAS
- Jangan menghentikan, menghapus, me-restart, atau mengubah container, image, volume, atau network yang sudah ada.
  Jangan jalankan docker system prune, docker compose down, docker volume rm, atau perintah serupa.
- Jangan mem-publish port host untuk report-service. Layanan hanya boleh dijangkau dari network Docker n8n.
- Jangan menampilkan, menyalin ke chat, atau membaca isi berkas rahasia (report_service_token.txt, berkas di
  reports_db_secrets/). Jangan menaruh password atau token di argumen perintah, log, atau chat.
- Jangan commit apa pun ke Git. Jangan menyentuh database inbound_marketing atau skema core, core_v2, staging.
- Perintah yang mengubah sesuatu di luar langkah yang tertulis di sini: minta persetujuan saya dulu.
- Jika ada hal tak terduga (nama berbeda, error, hasil pemeriksaan bukan OK), berhenti dan jelaskan. Jangan
  mengarang perbaikan.

FASE 0 - temukan (hanya membaca)
1. Cari container n8n yang berjalan. Catat nama container dan nama network Docker yang dipakainya.
2. Cari container PostgreSQL yang menjadi server database saya yang sudah ada. Catat nama container, versi
   PostgreSQL, dan nama user admin (superuser) yang dipakai di dalamnya.
3. TANYA SAYA: tampilkan ketiga hal itu dan minta saya mengonfirmasi sebelum lanjut.

FASE 1 - layanan laporan
1. Dari folder repo ini, buat token tanpa menampilkannya. Di bash/WSL:
     cd deploy && openssl rand -hex 32 > report_service_token.txt && chmod 600 report_service_token.txt
   Di PowerShell, JANGAN pakai ">" (PowerShell 5 menulis UTF-16 dengan BOM). Pakai:
     openssl rand -hex 32 | Set-Content -NoNewline -Encoding ascii deploy\report_service_token.txt
   Layanan kini mengenali berkas ber-BOM dan CRLF, tetapi tetap menolak berkas dengan spasi atau karakter non-ASCII.
2. Salin deploy/docker-compose.report-service.example.yml menjadi deploy/docker-compose.report-service.local.yml
   dan ubah HANYA nama network menjadi network n8n dari Fase 0. Jangan ubah pengaturan keamanan di dalamnya.
3. Bangun dan jalankan hanya layanan ini sebagai proyek terpisah:
     docker compose -p report-service -f deploy/docker-compose.report-service.local.yml up -d --build
   Gunakan build arg REPORT_GENERATOR_VERSION berisi 7 karakter pertama git commit saat ini bila git tersedia.
4. Tunggu sampai container berstatus healthy. Jika build gagal, tampilkan error apa adanya.

FASE 2 - database laporan (tahap pemeriksaan dulu)
1. Jalankan, TANPA --yes:
     deploy/install-reports-db.sh --container <container postgres> --admin-user <user admin>
   Jika server meminta password admin, minta saya menjalankan `export PGPASSWORD=...` di terminal saya sendiri;
   jangan minta saya mengetik password di chat.
2. TANYA SAYA: tampilkan hasil pemeriksaan apa adanya. Hanya jika semua baris OK dan saya menjawab "lanjut",
   jalankan perintah yang sama dengan --yes. Jika ada baris PROBLEM atau REVIEW, jangan lanjut.
3. Setelah instal, jangan membuka berkas password. Cukup laporkan path folder reports_db_secrets.

FASE 3 - verifikasi (perintah ini tidak bergantung pada shell, aman dari PowerShell)
1. Layanan, dari dalam container (harus 5 baris PASS dan "ALL CHECKS PASSED"):
     docker exec report-service python -m service.selftest
2. Database, read-only (harus 12 baris PASS; jika repo sudah memuat tabel target dan install-viewer-db.sh belum dijalankan,
   baris 13-16 akan FAIL. Itu wajar, bukan kerusakan; baris 1-12 yang menentukan di fase ini):
     docker cp database/verify_install.sql <container postgres>:/tmp/verify_install.sql
     docker exec <container postgres> psql -U <user admin> -d marketing_reports -f /tmp/verify_install.sql
     docker exec <container postgres> rm /tmp/verify_install.sql
3. Pemeriksaan container: status healthy, tidak ada port ter-publish (docker port report-service kosong), proses
   bukan root (docker exec report-service id -u bukan 0), root filesystem read-only (docker inspect -f
   "{{.HostConfig.ReadonlyRootfs}}" report-service bernilai true), dan n8n menjangkau layanan:
     docker exec <container n8n> wget -qO- -T 5 http://report-service:8080/healthz
   (Di WSL atau Git Bash, langkah 1 dan 3 bisa diganti satu perintah:
    deploy/verify-report-service.sh --container report-service --n8n-container <container n8n>.)
4. Laporkan setiap baris PASS/FAIL apa adanya. Jangan menyebut "PASS (manual)" untuk pemeriksaan yang tidak
   benar-benar dijalankan. Jika ada FAIL, jelaskan penyebab paling mungkin dan perbaiki hanya yang terkait
   container report-service, setelah saya setuju.

LAPORAN AKHIR (ringkas)
- Nama container dan network yang dipakai, hasil pemeriksaan database, hasil verifikasi.
- Daftar semua yang kamu buat atau ubah (berkas, container, network, database, role).
- Pernyataan eksplisit tentang apa yang TIDAK kamu ubah.
- Lokasi berkas token dan password (path saja).
```

## Setelah Gordon selesai (langkah Anda)

1. Buat credential di n8n:
   - Header Auth untuk layanan laporan: nama header `Authorization`, nilai `Bearer ` diikuti isi `deploy/report_service_token.txt`.
   - Dua credential Postgres ke database `marketing_reports`: `report_writer` dan `report_reader`, password dari `reports_db_secrets/`.
2. Impor tiga workflow dari `n8n/workflows/`, pilih credential, isi placeholder (lihat `n8n/README.md`).
3. Jalankan `Report_Generate_v1` manual untuk satu periode yang angkanya sudah Anda kenal dan bandingkan.
4. Tambahkan `marketing_reports` ke rutinitas backup.

## Catatan

Pemeriksaan fungsional kini ada di `service/selftest.py` (di dalam image) dan `database/verify_install.sql`, supaya tidak ada kutipan shell yang rapuh. Skrip di folder ini diuji tanpa Docker daemon: skrip database terhadap server PostgreSQL sementara dengan perintah `docker exec` ditiru, dan skrip pemeriksaan terhadap server lokal. Perintah Docker yang sebenarnya (build, healthcheck, network, `docker exec`) belum pernah dijalankan; itulah yang akan diuji Gordon pertama kali. Bila Gordon versi Anda tidak bisa menjalankan perintah, perintah di atas bisa Anda jalankan sendiri dengan urutan yang sama.
