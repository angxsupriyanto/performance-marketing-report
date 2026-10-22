# Tugas untuk Gordon: memasang viewer report di Docker

Tempel isi bagian **Instruksi** ke Gordon dari folder hasil clone repo ini. Penjelasan lengkap ada di `deploy/VIEWER.md`.

## Yang dikerjakan Gordon dan yang tidak

| Gordon | Anda |
|---|---|
| Menjalankan `install-viewer-db.sh` dan melaporkan 16 baris PASS | Membuat password viewer dan menjalankan `viewer.hash_password` (password diketik di terminal Anda, bukan di chat) |
| Membangun dan menjalankan container `report-viewer` | Mengimpor ulang dan mengaktifkan `Report_Analysis_Button_v1` di n8n |
| Memeriksa `/healthz` dari dalam network Docker | Menambahkan public hostname di Cloudflare Zero Trust |

## Instruksi

```text
Tugas: pasang viewer report (container report-viewer) di Docker saya, di samping n8n yang sudah berjalan.
Kerjakan bertahap dan HENTIKAN diri di setiap titik "TANYA SAYA".

ATURAN KERAS
- Jangan menghentikan, menghapus, me-restart, atau mengubah container, image, volume, atau network yang sudah ada.
  Jangan jalankan docker system prune, docker compose down, docker volume rm, atau perintah serupa.
- Jangan mem-publish port host untuk report-viewer.
- Jangan menampilkan, menyalin ke chat, atau membaca isi berkas rahasia (viewer_password_hash, viewer_session_secret,
  n8n_webhook_token, berkas di reports_db_secrets/). Jangan menaruh password atau token di argumen perintah.
- Jangan commit apa pun ke Git. Jangan menyentuh database selain marketing_reports.
- Perintah di luar langkah yang tertulis: minta persetujuan saya dulu. Jika ada hal tak terduga, berhenti dan jelaskan.

FASE 1 - database
1. Jalankan: deploy/install-viewer-db.sh --container <container PostgreSQL> --admin-user <superuser>
2. Laporkan 16 baris hasil pemeriksaan. Semua harus PASS. TANYA SAYA sebelum lanjut.

FASE 2 - rahasia (saya yang membuat)
1. Beri tahu saya tiga berkas yang harus ada di folder compose: viewer_session_secret, viewer_password_hash,
   n8n_webhook_token. Saya yang membuatnya. TANYA SAYA sampai saya bilang siap. Periksa hanya bahwa berkasnya ada
   dan tidak kosong (jangan membaca isinya).

FASE 3 - container
1. Salin deploy/docker-compose.report-viewer.example.yml menjadi docker-compose.report-viewer.local.yml. Ubah hanya
   nama network, VIEWER_DB_HOST, dan N8N_ANALYSIS_URL agar cocok dengan stack saya. TANYA SAYA: tampilkan perubahannya.
2. Jalankan: docker compose -p report-viewer -f deploy/docker-compose.report-viewer.local.yml up -d --build
3. Dari container lain di network yang sama (mis. curl dari container n8n), periksa http://report-viewer:8090/healthz.
   Harus {"status":"ok","database":true}. Laporkan hasilnya dan log 20 baris terakhir report-viewer.
4. Selesai. Saya yang menambahkan public hostname officehours.pesankopi.com -> http://report-viewer:8090 di Cloudflare.
```
