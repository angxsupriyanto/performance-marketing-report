# Viewer report di officehour.pesankopi.com

Halaman web internal untuk melihat report yang sudah disimpan di `marketing_reports`, menekan tombol analisis, dan mengatur target. Setiap orang punya username dan password sendiri. Admin punya akses penuh; pengguna biasa hanya melihat report perusahaan yang diberikan kepadanya.

```text
Browser ──HTTPS──> Cloudflare ──Tunnel──> report-viewer (container, tanpa port host)
                                              ├─ PostgreSQL marketing_reports (role report_viewer)
                                              └─ n8n webhook report-analysis ──> Claude
```

Viewer tidak membaca Google Sheet dan tidak memanggil model AI sendiri. Angka tetap dari generator; target tidak disimpan di report, jadi mengubah target tidak perlu membuat report ulang.

## Keamanan yang sudah dibangun

| Hal | Cara |
|---|---|
| Password | Hanya hash scrypt di tabel `reports.viewer_users`; password asli tidak disimpan. Minimal 12 karakter. Admin yang mengatur password; pengguna tidak bisa mengubahnya sendiri. |
| Peran | `admin`: semua halaman. `user`: hanya daftar report dan report perusahaan yang diberikan (satu, beberapa, atau Semua perusahaan termasuk yang ditambahkan nanti). Tombol analisis, target, Pengguna, dan Nama perusahaan hanya untuk admin, dan dicek di server, bukan hanya disembunyikan. |
| Pengguna | Tidak dihapus, hanya dinonaktifkan. Selalu ada minimal satu admin aktif. Menonaktifkan atau mengganti password seseorang mengakhiri sesinya saat itu juga, karena peran dan status dibaca dari database di setiap permintaan. |
| Percobaan masuk | 5 salah dalam 5 menit mengunci alamat itu 5 menit (dibaca dari `CF-Connecting-IP` di balik tunnel). Username salah dan password salah memberi pesan yang sama. |
| Sesi | Cookie bertanda tangan HMAC berisi username, `HttpOnly`, `Secure`, `SameSite=Strict`, berlaku 12 jam. Mengganti `viewer_session_secret` mengeluarkan semua orang. |
| Formulir | Setiap POST butuh token CSRF dan `Origin` yang cocok dengan host. |
| Isi halaman | CSP ketat dengan nonce, tanpa skrip pihak ketiga, tidak bisa di-frame, `no-store`, `noindex`. |
| Database | Role `report_viewer`: SELECT report, INSERT target, serta SELECT/INSERT/UPDATE pada `viewer_users` dan `company_names`. Tidak bisa DELETE, mengubah report, atau membuat report. Role penulis dan pembaca report tidak bisa membaca `viewer_users`. |
| Log | Hanya metode, segmen pertama path, status, dan durasi. Tidak ada password, isian formulir, atau periode. |

Yang **tidak** dicakup: tidak ada log siapa melakukan apa, dan tidak ada ubah password mandiri. Bila perlu lapisan tambahan, pasang Cloudflare Access (Zero Trust) di depan hostname yang sama; viewer tidak perlu diubah.

## Memasang

1. **Database.** Setelah `marketing_reports` terpasang:
   `deploy/install-viewer-db.sh --container <postgres> --admin-user <superuser>`
   Membuat tabel target, tabel pengguna dan nama perusahaan, serta role `report_viewer`, menulis password-nya ke `reports_db_secrets/reports_db_viewer_password` (mode 600), lalu menjalankan `database/verify_install.sql`; 20 baris harus PASS.
2. **Rahasia lain** (di folder tempat compose dijalankan, jangan di-commit):
   - `viewer_session_secret` dan `n8n_webhook_token` (acak, 64 karakter heks). Linux, macOS, WSL: `openssl rand -hex 32 > viewer_session_secret`. **PowerShell (Windows):**
     ```powershell
     function New-Secret($path) { $b = New-Object byte[] 32; [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b); [IO.File]::WriteAllText("$PWD\$path", (($b | ForEach-Object { $_.ToString('x2') }) -join ''), (New-Object Text.UTF8Encoding $false)) }
     New-Secret viewer_session_secret
     New-Secret n8n_webhook_token
     ```
     Jangan memakai `>` di PowerShell untuk rahasia: ia menulis UTF-16. Layanan tetap membacanya, tetapi cara di atas bersih.
   - `viewer_password_hash`: password **admin pertama** (username `admin`). Dipakai sekali: saat tabel pengguna masih kosong, viewer membuat admin dari hash ini. Setelah itu password admin diatur di halaman Pengguna, dan berkas ini tidak berpengaruh lagi. `python -m viewer.hash_password --output viewer_password_hash` di komputer yang punya Python dan repo ini. Tanpa Python lokal (PowerShell, dari folder tempat berkas akan dibuat): `docker run --rm -it -v "${PWD}:/out" --entrypoint python $(docker inspect -f "{{.Config.Image}}" report-service) -m viewer.hash_password --output /out/viewer_password_hash`. Password diketik dua kali di terminal, tidak lewat argumen.
   - `n8n_webhook_token`: token yang sama dengan nilai credential Header Auth pada node *Webhook Analysis* di n8n. Nilai `Authorization` di n8n boleh `Bearer <token>`; sesuaikan `N8N_WEBHOOK_HEADER_PREFIX` bila credential Anda memakai token polos.
3. **Container.** Salin `deploy/docker-compose.report-viewer.example.yml` menjadi `docker-compose.report-viewer.local.yml` (diabaikan Git), ubah nama network, `VIEWER_DB_HOST`, dan `N8N_ANALYSIS_URL` sesuai stack Anda, lalu:
   `docker compose -p report-viewer -f deploy/docker-compose.report-viewer.local.yml up -d --build`
   Proyek terpisah, jadi stack n8n tidak dibuat ulang. Jangan publikasikan port.
4. **n8n.** Impor ulang `Report_Analysis_Button_v1.json` (sekarang menerima `targets` dari viewer), aktifkan workflow itu supaya URL produksi `/webhook/report-analysis` berlaku, dan pasang credential Header Auth untuk node *Ask Model* (`Authorization` = `Bearer <API key 9router>`). Model dan alamat router sudah terisi di node *Prepare Analysis Request* (`pesankopi-report`).
5. **Cloudflare Tunnel.** Di Zero Trust, pada tunnel yang sudah melayani n8n: *Public hostname* `officehour.pesankopi.com` → *Service* `HTTP` `report-viewer:8090`. Container `cloudflared` harus berada di network Docker yang sama dengan `report-viewer`. Selesai; tidak ada port yang dibuka di server.

## Pengguna dan nama perusahaan

- Masuk pertama kali dengan username `admin` dan password dari `viewer_password_hash`. Segera buka **Pengguna** untuk menambah orang lain (username 3 sampai 32 karakter huruf kecil, angka, titik, garis bawah, strip; tidak bisa diubah setelah dibuat) dan mengganti password admin.
- **Nama perusahaan** mengatur nama tampil untuk `bu1` dan `bu2` (contoh McEasy dan LOL). Identitas internal, tautan, data, dan akses pengguna tidak berubah ketika nama diganti. Sebelum diatur, tampil "Perusahaan 1" dan "Perusahaan 2". Telegram dan prompt analisis tidak memakai nama ini.
- Lupa password admin satu-satunya: jalankan `UPDATE reports.viewer_users SET password_hash = '<hash dari python -m viewer.hash_password>' WHERE username = 'admin'` sebagai superuser.

## Toggle "Hanya yang submission-nya di Week n"

- Satu saklar di tiap bagian berikut: **McEasy** (`hardware_report`): Daftar SQL dan tabel Campaign Hardware. **LOL** (`deal_won_list`): Daftar SQL dan Daftar Deal Won. Mati (bawaan): semua SQL, MQL, atau Deal Won pada periode itu. Menyala: hanya yang **Inbound Date**-nya juga di periode itu (untuk report bulanan, bulan yang sama).
- Pada tabel Campaign Hardware, hanya kolom MQL, SQL, dan SQL Value yang berubah. Submission, Target, dan Progress tetap, begitu pula kartu target, bagian Progress target, dan blok Funnel per hardware.
- Saklar bekerja di browser dari data yang sudah ada di halaman, tanpa permintaan ke server. Report yang disimpan sebelum fitur ini tampil tanpa saklar sampai Report Generate dijalankan lagi.

## Budget dan spend

- Menu **Budget** (admin): pilih perusahaan dan bulan, isi **total budget**, **budget per campaign**, **spend per minggu**, dan **spend bulanan**, lalu *Simpan budget dan spend*. Section **Budget dan spend {bulan}** tampil paling atas di setiap report (kartu Total budget, Spend Week n, Spend bulan, Sisa budget, bar Pemakaian budget, dan tabel per campaign, dengan pembanding bulan lalu atau minggu lalu).
- **Spend mingguan dan bulanan diisi terpisah dan tidak dijumlahkan.** Minggu ISO bisa melewati pergantian bulan (W44 = 26 Okt sampai 1 Nov, W45 lanjut dari 2 Nov), jadi satu bulan bukan 4 atau 5 minggu penuh. Sebuah minggu diisi di halaman bulan yang memuat hari Kamisnya. Minggu yang belum berjalan tidak bisa diisi.
- **Spend bulan di report** = angka bulanan terakhir yang diisi dengan tanggal "sampai" tidak lebih baru dari hari terakhir report itu. Report Week 42 (sampai 18 Okt) tidak memakai angka yang diisi sampai 25 Okt. Bila belum ada, tampil "Belum diisi", bukan nol.
- Daftar campaign berasal dari kolom Campaign di sheet (disimpan di report terbaru), ditambah campaign yang Anda tambahkan sendiri. Nama harus persis sama dengan di Tracker; ejaan berbeda dianggap campaign lain.
- Total budget wajib diisi bila ada budget per campaign, dan jumlah budget per campaign tidak boleh melebihi total. Selisihnya tampil sebagai baris "Belum dialokasikan ke campaign". Budget 0 sama dengan kosong.
- Setiap simpan menambah satu versi lengkap di `reports.budget_snapshots` (tidak ada UPDATE atau DELETE) dan muncul di Riwayat budget. Bila dua admin menyimpan bulan yang sama bergantian, yang membuka halaman lebih dulu ditolak dengan pesan untuk memuat ulang, supaya tidak menimpa tanpa sadar.
- Report lama ikut memakai budget terbaru, seperti target: budget tidak disimpan di report.

## Edit analisis manual

- Setiap panel analisis (Executive Summary, ringkasan hardware, dan satu per produk) punya chip status: **AI · nama model** atau **Edited**, plus baris asal teks ("Dibuat oleh model ... · waktu", "Diedit oleh admin · waktu · model awal: ...", atau "Ditulis manual oleh ... · belum ada analisis AI"). Semua orang dengan akses ke report melihatnya; hanya admin yang melihat tombol Edit, Tulis manual, dan Kembalikan ke versi AI.
- Setiap edit disimpan sebagai baris baru di `reports.analysis_edits` (tidak ada UPDATE atau DELETE), jadi semua versi tersimpan. *Kembalikan ke versi AI* menyimpan penanda, bukan menghapus.
- Aturan teks yang tampil: edit terbaru sebuah panel, **asal lebih baru dari analisis AI terbaru** untuk report itu. Karena itu *Buat analisis* atau *Buat ulang analisis* mengganti semua panel dengan versi AI baru. Bila ada panel yang sedang diedit, muncul konfirmasi "Ada panel yang sudah diedit" sebelum jalan; edit lama tetap ada di riwayat.
- **Model akhir.** Chip menampilkan model yang benar-benar menjawab: workflow *Report Analysis Button* sekarang mengambil kolom `model` dari jawaban router, bukan nama combo (`pesankopi-report`). Impor ulang `n8n/workflows/Report_Analysis_Button_v1.json` agar ini berlaku. Bila router tidak mengirim `model`, yang tersimpan nama combo.
- Teks edit berupa teks biasa (maksimal 4000 karakter); markup tampil apa adanya.

## Setelah memperbarui generator (report lama tidak berubah)

Satu report tersimpan per kombinasi (BU, periode, isi sheet, versi kode generator). Dulu versi kode tidak ikut kunci, jadi setelah generator diperbarui, menjalankan Report Generate pada sheet yang sama tidak menambah apa pun dan HTML lama tetap tampil. Sekarang versi kode (hash isi `generate_report.py`, template, dan profil) ikut kunci. Urutan memperbarui:

1. `git pull`, lalu bangun ulang `report-service` (versi kode baru terbaca di `/healthz` sebagai `generator_version`).
2. Jalankan `deploy/install-viewer-db.sh` lagi (aman diulang; ia menerapkan `003_run_idempotency_includes_generator.sql`, `004_users_and_company_names.sql`, `005_analysis_edits.sql`, dan `006_budget.sql`).
3. Di n8n, perbarui node *Save Run* di `Report_Generate_v1` dengan isi `n8n/sql/insert_run.sql` terbaru (atau impor ulang workflow). **Kedua langkah 2 dan 3 harus dilakukan bersama:** setelah 003 diterapkan, SQL lama gagal karena tidak ada constraint yang cocok.
4. Jalankan Report Generate lagi untuk periode yang dibutuhkan. Run baru muncul sebagai report terbaru; run lama dan analisisnya tetap tersimpan. Analisis dibuat per run, jadi tekan *Buat analisis* lagi pada report baru.

## Memeriksa

1. `https://officehour.pesankopi.com/healthz` menjawab `{"status":"ok","database":true}`.
2. Membuka `/` tanpa masuk mengarah ke `/login`; username atau password salah ditolak; lima kali salah mengunci.
3. Setelah masuk, Daftar report menampilkan report yang sudah dibuat lewat n8n.
4. Buka satu report: bagian atas memuat tombol analisis, tabel Campaign Hardware punya kolom Target dan Progress.
5. Pengaturan target: simpan satu target, buka report lagi, angka Target dan Progress terisi.
6. Tekan *Buat analisis*: status berubah menjadi *Menganalisis*, lalu halaman memuat ulang dengan analisis di panel.

## Mengganti password atau mengeluarkan semua sesi

- Password pengguna mana pun, termasuk admin: halaman **Pengguna**, Ubah, isi password baru. Semua sesi orang itu berakhir saat itu juga.
- Keluarkan semua orang: ganti isi `viewer_session_secret`, lalu restart container.

## Bila ada masalah

| Gejala | Penyebab biasa |
|---|---|
| Container berhenti dengan `..._FILE tidak bisa dipakai` | Berkas rahasia kosong, mengandung spasi atau baris baru di tengah, atau tidak terbaca user container. Buat ulang sebagai teks polos. |
| `/healthz` menjawab `"database": false` | `VIEWER_DB_HOST` salah, container tidak satu network, atau `install-viewer-db.sh` belum dijalankan. |
| Daftar report kosong padahal ada di n8n | Report Generate belum dijalankan untuk periode itu atau tersimpan di database lain. |
| Tombol analisis: "n8n menjawab 401" | Token di `n8n_webhook_token` atau prefix header tidak sama dengan credential Header Auth. |
| Tombol analisis: "n8n menjawab 404" | Workflow belum aktif atau `N8N_ANALYSIS_URL` memakai URL test, bukan produksi. |
| Login: "Database marketing_reports tidak menjawab" padahal `/healthz` true | `004_users_and_company_names.sql` belum diterapkan. Jalankan `deploy/install-viewer-db.sh` lagi. |
| Login selalu "terkunci" untuk semua orang | `VIEWER_TRUST_PROXY_HEADERS=true` tetapi permintaan tidak lewat Cloudflare, sehingga semua berasal dari satu alamat. |
