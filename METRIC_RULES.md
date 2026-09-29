# Aturan metrik BU1 weekly dashboard

Aturan ini mendeskripsikan generator, bukan instruksi bebas untuk menafsirkan data. Satu baris pada ekspor stage dihitung sebagai satu event stage. Empat file harus berasal dari snapshot tracker yang sama. Semua periode memakai ISO week Senin–Minggu berdasarkan **tanggal event**, meskipun kolom `... Week` dalam CSV berbeda.

| Output | Sumber dan rumus |
|---|---|
| Submission | Jumlah baris Raw Submission dengan `Inbound Date` di minggu tersebut. |
| MQL | Jumlah baris Raw MQL dengan `MQL Date` di minggu tersebut. |
| MQL Rate KPI | MQL event minggu tersebut ÷ Submission event minggu tersebut. |
| SQL | Jumlah baris Raw SQL dengan `Proposal Price Quote Date` di minggu tersebut. |
| SQL Rate KPI | SQL event minggu tersebut ÷ MQL event minggu tersebut. |
| SQL Value | Jumlah `SUM of ARR + OTF (Tanpa PPN)` pada baris Raw SQL tersebut. `Rp -` dan kosong menjadi 0. |
| Deal Won | Jumlah baris Raw Deal Won dengan `Deal Won Date` di minggu tersebut. |
| Deal Won Rate | Deal Won event minggu tersebut ÷ SQL event minggu tersebut. |
| Deal Value | Jumlah `SUM of Total Contract Deal Won` pada baris Deal Won tersebut. |
| Perubahan volume/nilai | `(minggu baru ÷ minggu pembanding − 1) × 100%`. Penyebut 0 menghasilkan N/A, kecuali kedua periode 0 menjadi `→ 0,0%`. |
| Perubahan rate | Selisih rate minggu baru minus rate pembanding dalam **percentage points (pp)**. |
| Same-week MQL | MQL event di minggu laporan dengan `Inbound Date` juga di minggu laporan. |
| Same-week SQL / SQL Value | SQL event di minggu laporan dengan `Inbound Date` juga di minggu laporan; nilai dari baris tersebut. |
| Pipeline backlog | Event minggu laporan dengan Inbound Date sebelum minggu laporan. |
| Top Contributor | Baris SQL atau Deal Won dengan nilai terbesar pada minggu laporan; seri diputuskan secara alfabetis menurut Company. Timing = selisih hari kalender antara Inbound Date dan tanggal event stage. |
| Breakdown per Stage | Dikelompokkan menurut `Source` dalam file stage masing-masing, per tanggal event. Source kosong menjadi Unknown. |
| Cross-stage MQL dan MQL Rate | Dari baris Submission minggu laporan yang memiliki MQL Date **di minggu yang sama**; dibagi Submission source yang sama. Total cohort bisa berbeda dari KPI MQL. SQL dan Deal Won di tabel ini tetap event-week, sehingga kolom bukan perjalanan cohort yang sama. |
| Campaign Hardware | Hanya `Dashcam`, `GPS Tracker` (tag `GPS`), `Fuel`, `MDVR`, `OBD`. Salah ketik `OND` menjadi OBD hanya bila nama campaign mengandung OBD. Kosong, Unknown, dan Others dikecualikan. Tiap stage mengikuti tanggal event stage-nya. |
| Campaign Detail MQL Rate | Baris Submission pada campaign/minggu yang sudah memiliki MQL Date **pada snapshot CSV**, walaupun tanggal MQL jatuh pada minggu sesudahnya, ÷ Submission campaign/minggu. Ini berbeda dari Same-week MQL dan dari Cross-stage MQL Rate. Hanya campaign hardware yang memiliki Submission di minggu terbaru ditampilkan. |
| Highlight | Top SQL Value campaign; campaign dengan Submission terbanyak namun 0 SQL event; campaign dengan jumlah Remark `Junk leads` terbanyak. Seri diputuskan alfabetis. Jika tidak ada kandidat, tampilkan `—`. |

## Header wajib

Header dibaca setelah spasi berulang dan spasi di ujung dinormalisasi. Ejaan inti tetap harus cocok. `SUM of  ARR + OTF (Tanpa PPN) ` dalam ekspor akan menjadi `SUM of ARR + OTF (Tanpa PPN)`; `SUM of  Total Contract Deal Won` akan menjadi `SUM of Total Contract Deal Won`.

| File | Header wajib |
|---|---|
| Raw Submission | `Company`, `Channel`, `Source`, `Campaign`, `Campaign Hardware`, `Industry`, `Remark`, `Inbound Date`, `MQL Date` |
| Raw MQL | `Company`, `Channel`, `Source`, `Campaign`, `Campaign Hardware`, `Industry`, `Inbound Date`, `MQL Date` |
| Raw SQL | `Company`, `Channel`, `Source`, `Campaign`, `Campaign Hardware`, `Industry`, `Inbound Date`, `Proposal Price Quote Date`, `SUM of ARR + OTF (Tanpa PPN)` |
| Raw Deal Won | `Company`, `Channel`, `Source`, `Campaign`, `Campaign Hardware`, `Industry`, `Inbound Date`, `Deal Won Date`, `SUM of Total Contract Deal Won` |

Tanggal diterima dalam `M/D/YYYY` seperti ekspor CSV atau ISO `YYYY-MM-DD`. Nilai uang harus bilangan bulat Rupiah dengan atau tanpa pemisah ribuan; format desimal ditolak agar tidak salah skala. Denominator 0 pada rate ditampilkan N/A. Tidak ada deduplikasi nama perusahaan otomatis dan tidak ada join lintas empat file berdasarkan nama/telepon; perubahan definisi tersebut membutuhkan identifier stabil dan review terpisah.
