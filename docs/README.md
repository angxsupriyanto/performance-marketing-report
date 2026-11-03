# Dokumentasi

Urutan baca yang disarankan untuk orang atau model yang baru masuk:

1. [`../CLAUDE.md`](../CLAUDE.md): orientasi satu halaman dan aturan kerja.
2. [`ARCHITECTURE.md`](ARCHITECTURE.md): bagaimana data mengalir dan apa peran tiap komponen.
3. [`DECISIONS.md`](DECISIONS.md): keputusan pemilik produk beserta alasannya. **Jangan dibatalkan diam-diam.**
4. [`../METRIC_RULES.md`](../METRIC_RULES.md): definisi dan rumus tiap metrik.
5. [`DATA_MODEL.md`](DATA_MODEL.md): tabel database, migrasi, dan hak akses.
6. [`RUNBOOK.md`](RUNBOOK.md): cara memasang, memperbarui, dan memperbaiki masalah (Windows PowerShell dan Docker).
7. [`KNOWN_GAPS.md`](KNOWN_GAPS.md): apa yang belum terbukti atau belum selesai.
8. [`ROADMAP.md`](ROADMAP.md): fase berikutnya, dengan mockup dan keputusan terbuka.

Dokumen lama yang masih berlaku: [`../README.md`](../README.md) (generator dan prosedur CLI), [`../deploy/VIEWER.md`](../deploy/VIEWER.md) (pasang dan fitur viewer), [`../n8n/README.md`](../n8n/README.md) (workflow).

Aturan merawat dokumen: ubah dokumen **dalam commit yang sama** dengan perubahan perilaku. Keputusan baru masuk `DECISIONS.md` dengan tanggal dan siapa yang memutuskan. Hal yang belum terbukti masuk `KNOWN_GAPS.md`, dan dihapus dari sana hanya setelah dibuktikan.
