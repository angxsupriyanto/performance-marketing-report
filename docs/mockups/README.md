# Mockup

Mockup dibuat sebagai **artifact desain** (berkas `*.dc.html`) di akun pemilik. Artifact itu pribadi, jadi tidak bisa dibuka dari repo. Folder ini menyimpan tangkapan layarnya. Nama perusahaan pelanggan dan kode campaign internal diganti contoh netral (`[kode]`, "PT Contoh") karena repo ini publik. **Angka di mockup hanya ilustrasi.**

| Berkas | Papan | Status | Isi |
|---|---|---|---|
| `11-mode-gelap.png` | 11. Mode gelap | **Sudah diimplementasikan** | Tombol Terang, Gelap, Otomatis; kartu, tabel, notifikasi, pemilih campaign, dan palet gelap (latar `#191919`, permukaan `#1F1F1F`) |
| `12a-pemetaan-iklan-daftar.png` | 12. Pemetaan iklan | Disetujui, **belum dibangun** | Daftar campaign iklan dengan platform, produk, dan ringkasan pemetaan; daftar produk |
| `12b-pemetaan-iklan-atur.png` | 12. Pemetaan iklan | Disetujui, belum dibangun | Panel *Atur*: aturan filter, tambahan manual, pengecualian, hasil |
| `12c-pemetaan-iklan-bentrok.png` | 12. Pemetaan iklan | Disetujui, belum dibangun | Keadaan bentrok: campaign Tracker sudah dipetakan ke campaign iklan lain, tombol Simpan nonaktif |
| `13a-budget-iklan-berbayar-dan-report.png` | 13. Budget dan tampilan report | Disetujui, belum dibangun | Picker tab *Iklan berbayar*, tabel Budget dengan kolom Platform dan Produk, dan tiga tabel baru di report (spend per platform, per produk dengan ROAS, per campaign iklan) |
| `13b-budget-non-iklan.png` | 13. Budget | Disetujui, belum dibangun | Picker tab *Non-iklan* (campaign Tracker dan grup seperti Email Nurturing) |

Keputusan di balik papan 12 dan 13 ada di [`../ROADMAP.md`](../ROADMAP.md) (fase 1) dan [`../DECISIONS.md`](../DECISIONS.md).

Mockup halaman yang sudah ada (Masuk, Daftar report, Performa, report, Target, Budget, Pengguna, Nama perusahaan) tidak disalin ke sini karena sudah diimplementasikan; sumber kebenarannya adalah kode. Bila fase berikutnya mengubah salah satunya, buat mockup baru dulu (D5), lalu simpan tangkapan layarnya di folder ini dengan awalan nomor papan.
