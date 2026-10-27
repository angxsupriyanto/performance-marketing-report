# Runbook: memasang, memperbarui, memperbaiki

Untuk pengguna **Windows PowerShell** dengan Docker Desktop. Jalankan dari folder repo (mis. `...\services\performance-marketing-report`). Detail pemasangan awal: [`deploy/VIEWER.md`](../deploy/VIEWER.md) dan [`n8n/README.md`](../n8n/README.md). Dokumen ini memuat **urutan yang benar dan jebakan yang pernah terjadi**.

## Nama yang dipakai

| Hal | Nilai |
|---|---|
| Proyek compose layanan laporan | `report-service` (file `deploy/docker-compose.report-service.local.yml`) |
| Proyek compose viewer | `report-viewer` (file `deploy/docker-compose.report-viewer.local.yml`) |
| Hostname publik | `officehours.pesankopi.com` lewat Cloudflare Tunnel |
| Database | `marketing_reports` (terpisah dari database n8n) |
| Branch kerja | `claude/vigilant-sagan-e0ttx8` (PR 1 sudah ada; jangan membuat PR baru tanpa diminta) |

File `*.local.yml` ada di `.gitignore`: dibuat sendiri dari berkas `*.example.yml` (ubah nama network, host database, dan alamat n8n).

## Memperbarui setelah ada perubahan kode (urutan umum)

```powershell
git pull origin claude/vigilant-sagan-e0ttx8
```

Lalu bangun ulang hanya yang berubah:

| Yang berubah | Perintah tambahan |
|---|---|
| `generate_report.py`, `report_view.py`, `profiles/`, `service/` | `docker compose -p report-service -f deploy/docker-compose.report-service.local.yml up -d --build` |
| `viewer/`, `database/` (hanya viewer) | `docker compose -p report-viewer -f deploy/docker-compose.report-viewer.local.yml up -d --build` |
| `n8n/code`, `n8n/prompts`, `n8n/sql` | Tempel isi node dari `n8n/workflows/code/` (tanpa impor ulang); lihat `n8n/README.md` |
| Migrasi baru di `database/` | Terapkan **setelah** `git pull` (jebakan di bawah) |

Setelah memperbarui **generator**, jalankan Report Generate dan Performa Generate lagi: report lama tidak berubah dan memakai angka lama (versi kode ikut kunci run).

Periksa: `docker ps --filter name=report-service`, `docker ps --filter name=report-viewer`, dan `https://officehours.pesankopi.com/healthz` (harus `{"status":"ok","database":true}`).

Image `report-service` tidak butuh Chromium: bangun dengan `--build-arg INSTALL_CHROMIUM=false` bila ingin lebih kecil.

## Jebakan yang pernah terjadi

| Gejala | Penyebab dan perbaikan |
|---|---|
| `open ...docker-compose.report-viewer.local.yml: The system cannot find the file specified` | Path tanpa `deploy/`. Pakai `-f deploy/docker-compose.report-viewer.local.yml`. Cari berkasnya: `Get-ChildItem -Recurse -Filter "docker-compose.report-viewer*.yml"`. |
| `Get-Content : Cannot find path ...\009_report_actions.sql` | Migrasi dijalankan **sebelum** `git pull`. Tarik dulu, baru terapkan migrasi. |
| Skrip `.sh` tidak jalan di PowerShell | PowerShell tidak punya `sh`. Terapkan migrasi dengan mengalirkan berkas ke psql di container Postgres: `Get-Content -Raw database\009_report_actions.sql \| docker exec -i <container-postgres> psql -X -v ON_ERROR_STOP=1 -U <admin> -d marketing_reports`. Ganti nama berkas dan `<...>` sesuai lingkungan. |
| Menulis rahasia dengan `>` | PowerShell menulis UTF-16. Pakai fungsi `New-Secret` di `deploy/VIEWER.md`. |
| n8n: *Referenced node doesn't exist* | Node di kanvas diganti nama (mis. `Validate Request1`). Kembalikan nama persis seperti di JSON; pesan galat terbaru menyebut nama yang dicari. |
| Hasil di Telegram atau report tidak berubah setelah aturan hitung berubah | Image `report-service` belum dibangun ulang, atau Report Generate belum dijalankan lagi. Bandingkan `generator_version` di `/healthz`. |
| Instance live membuka port ke luar | Berkas override `localaccess` dipakai. Jangan; pakai file compose dasar dengan proyek `report-viewer`. |
| Login terkunci untuk semua orang | `VIEWER_TRUST_PROXY_HEADERS=true` tetapi permintaan tidak lewat Cloudflare. |
| Cloudflare Access: halaman login muncul lagi setelah login | Belum diselesaikan; sengaja dilewati (D34). |
| Tombol *Simpan sebagai PDF* gagal | Periksa `docker exec report-viewer chromium --version` dan `docker logs --tail 30 report-viewer`. Bila memori kurang, naikkan batas memori container (±300 MB saat mencetak). Belum terkonfirmasi di container nyata (lihat `KNOWN_GAPS.md`). |

## Alur kerja mingguan pemilik

1. Di n8n jalankan **Report Generate** (isi `bu` dan `period` di *Manual Parameters*), dan **Performa Generate** bila halaman Performa perlu data terbaru.
2. Di viewer buka report, periksa angka, lalu admin menekan **Buat analisis** (isi Action periode bila ada).
3. Cek teks analisis; admin boleh mengedit panel.
4. Bila perlu, **Simpan sebagai PDF**.

## Tes

```powershell
python -m unittest discover -s tests          # ±140 detik
```

Tes database memakai PostgreSQL sekali pakai dan menolak berjalan bila database `marketing_reports` atau role `report_*` sudah ada:
`REPORTS_TEST_ADMIN="host=127.0.0.1 port=5432 user=postgres" python -m unittest tests.test_database`

Uji di browser memakai Playwright dengan Chromium bawaan (`--no-sandbox`); skrip uji manual tidak disimpan di repo. Tes yang membutuhkan PostgreSQL dilewati bila `REPORTS_TEST_ADMIN` tidak diisi (16 tes dilewati adalah hal normal pada jalan biasa), dan tes yang memakai Chromium sungguhan dilewati bila Chromium tidak ada.

## Rahasia

Jangan membaca, menempel, atau men-commit: `viewer_session_secret`, `n8n_webhook_token`, `viewer_password_hash`, `report_service_token*.txt`, `reports_db_secrets/`, token tunnel, dan `*.local.yml`. Repo ini publik.
