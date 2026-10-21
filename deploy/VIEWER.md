# Viewer report di officehour.pesankopi.com

Halaman web internal untuk melihat report yang sudah disimpan di `marketing_reports`, menekan tombol analisis, dan mengatur target. Satu password bersama untuk tim (tanpa akun per orang, jadi riwayat target tidak mencatat siapa yang menyimpan).

```text
Browser ──HTTPS──> Cloudflare ──Tunnel──> report-viewer (container, tanpa port host)
                                              ├─ PostgreSQL marketing_reports (role report_viewer)
                                              └─ n8n webhook report-analysis ──> Claude
```

Viewer tidak membaca Google Sheet dan tidak memanggil model AI sendiri. Angka tetap dari generator; target tidak disimpan di report, jadi mengubah target tidak perlu membuat report ulang.

## Keamanan yang sudah dibangun

| Hal | Cara |
|---|---|
| Password | Hanya hash scrypt di Docker secret; password asli tidak disimpan. Minimal 12 karakter. |
| Percobaan masuk | 5 salah dalam 5 menit mengunci alamat itu 5 menit (dibaca dari `CF-Connecting-IP` di balik tunnel). |
| Sesi | Cookie bertanda tangan HMAC, `HttpOnly`, `Secure`, `SameSite=Strict`, berlaku 12 jam. Mengganti `viewer_session_secret` mengeluarkan semua orang. |
| Formulir | Setiap POST butuh token CSRF dan `Origin` yang cocok dengan host. |
| Isi halaman | CSP ketat dengan nonce, tanpa skrip pihak ketiga, tidak bisa di-frame, `no-store`, `noindex`. |
| Database | Role `report_viewer`: SELECT report dan INSERT target saja. Tidak bisa UPDATE, DELETE, atau membuat report. |
| Log | Hanya metode, segmen pertama path, status, dan durasi. Tidak ada password, isian formulir, atau periode. |

Yang **tidak** dicakup: password bersama bisa bocor dari orang ke orang. Bila itu risiko, tambahkan Cloudflare Access (Zero Trust) di depan hostname yang sama; viewer tidak perlu diubah.

## Memasang

1. **Database.** Setelah `marketing_reports` terpasang:
   `deploy/install-viewer-db.sh --container <postgres> --admin-user <superuser>`
   Membuat tabel target dan role `report_viewer`, menulis password-nya ke `reports_db_secrets/reports_db_viewer_password` (mode 600), lalu menjalankan `database/verify_install.sql`; 16 baris harus PASS.
2. **Rahasia lain** (di folder tempat compose dijalankan, jangan di-commit):
   - `viewer_session_secret` dan `n8n_webhook_token` (acak, 64 karakter heks). Linux, macOS, WSL: `openssl rand -hex 32 > viewer_session_secret`. **PowerShell (Windows):**
     ```powershell
     function New-Secret($path) { $b = New-Object byte[] 32; [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b); [IO.File]::WriteAllText("$PWD\$path", (($b | ForEach-Object { $_.ToString('x2') }) -join ''), (New-Object Text.UTF8Encoding $false)) }
     New-Secret viewer_session_secret
     New-Secret n8n_webhook_token
     ```
     Jangan memakai `>` di PowerShell untuk rahasia: ia menulis UTF-16. Layanan tetap membacanya, tetapi cara di atas bersih.
   - `viewer_password_hash`: `python -m viewer.hash_password --output viewer_password_hash` di komputer yang punya Python dan repo ini. Tanpa Python lokal (PowerShell, dari folder tempat berkas akan dibuat): `docker run --rm -it -v "${PWD}:/out" --entrypoint python $(docker inspect -f "{{.Config.Image}}" report-service) -m viewer.hash_password --output /out/viewer_password_hash`. Password diketik dua kali di terminal, tidak lewat argumen.
   - `n8n_webhook_token`: token yang sama dengan nilai credential Header Auth pada node *Webhook Analysis* di n8n. Nilai `Authorization` di n8n boleh `Bearer <token>`; sesuaikan `N8N_WEBHOOK_HEADER_PREFIX` bila credential Anda memakai token polos.
3. **Container.** Salin `deploy/docker-compose.report-viewer.example.yml` menjadi `docker-compose.report-viewer.local.yml` (diabaikan Git), ubah nama network, `VIEWER_DB_HOST`, dan `N8N_ANALYSIS_URL` sesuai stack Anda, lalu:
   `docker compose -p report-viewer -f deploy/docker-compose.report-viewer.local.yml up -d --build`
   Proyek terpisah, jadi stack n8n tidak dibuat ulang. Jangan publikasikan port.
4. **n8n.** Impor ulang `Report_Analysis_Button_v1.json` (sekarang menerima `targets` dari viewer), aktifkan workflow itu supaya URL produksi `/webhook/report-analysis` berlaku, dan pasang credential Header Auth untuk node *Ask Model* (`Authorization` = `Bearer <API key 9router>`). Model dan alamat router sudah terisi di node *Prepare Analysis Request* (`pesankopi-report`).
5. **Cloudflare Tunnel.** Di Zero Trust, pada tunnel yang sudah melayani n8n: *Public hostname* `officehour.pesankopi.com` → *Service* `HTTP` `report-viewer:8090`. Container `cloudflared` harus berada di network Docker yang sama dengan `report-viewer`. Selesai; tidak ada port yang dibuka di server.

## Memeriksa

1. `https://officehour.pesankopi.com/healthz` menjawab `{"status":"ok","database":true}`.
2. Membuka `/` tanpa masuk mengarah ke `/login`; password salah ditolak; lima kali salah mengunci.
3. Setelah masuk, Daftar report menampilkan report yang sudah dibuat lewat n8n.
4. Buka satu report: bagian atas memuat tombol analisis, tabel Campaign Hardware punya kolom Target dan Progress.
5. Pengaturan target: simpan satu target, buka report lagi, angka Target dan Progress terisi.
6. Tekan *Buat analisis*: status berubah menjadi *Menganalisis*, lalu halaman memuat ulang dengan analisis di panel.

## Mengganti password atau mengeluarkan semua sesi

- Password: buat hash baru ke `viewer_password_hash`, lalu `docker compose ... restart report-viewer`. Sesi lama tetap berlaku sampai habis (12 jam) kecuali Anda juga mengganti secret sesi.
- Keluarkan semua orang: ganti isi `viewer_session_secret`, lalu restart container.

## Bila ada masalah

| Gejala | Penyebab biasa |
|---|---|
| Container berhenti dengan `..._FILE tidak bisa dipakai` | Berkas rahasia kosong, mengandung spasi atau baris baru di tengah, atau tidak terbaca user container. Buat ulang sebagai teks polos. |
| `/healthz` menjawab `"database": false` | `VIEWER_DB_HOST` salah, container tidak satu network, atau `install-viewer-db.sh` belum dijalankan. |
| Daftar report kosong padahal ada di n8n | Report Generate belum dijalankan untuk periode itu atau tersimpan di database lain. |
| Tombol analisis: "n8n menjawab 401" | Token di `n8n_webhook_token` atau prefix header tidak sama dengan credential Header Auth. |
| Tombol analisis: "n8n menjawab 404" | Workflow belum aktif atau `N8N_ANALYSIS_URL` memakai URL test, bukan produksi. |
| Login selalu "terkunci" untuk semua orang | `VIEWER_TRUST_PROXY_HEADERS=true` tetapi permintaan tidak lewat Cloudflare, sehingga semua berasal dari satu alamat. |
